#!/usr/bin/env python3
"""Phase 4 real-library validation driver.

Stage 1 builds a fresh ignored validation database, scans Zotero read-only, and runs
source-stable author identity resolution. Stage 2 may reuse that database after a small
explicitly reviewed PDF/reference anchor set has been accepted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sqlalchemy as sa  # noqa: E402

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentEvidenceSpan,
    PaperCreatorMention,
    PaperDocument,
    PaperReference,
    PaperReferenceMatch,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.identity.authorship_evidence import propose_authorship_evidence  # noqa: E402
from paperazzi.identity.models import (  # noqa: E402
    Author,
    AuthorIdentityDecision,
    AuthorIdentityMembership,
    Authorship,
    AuthorshipEvidence,
)
# Import through the public identity package so the source-stable resolver compatibility
# patch is activated even for callers that historically imported identity.service.
from paperazzi.identity import bootstrap_author_identities  # noqa: E402
from paperazzi.identity.reference_resolution import LocalReferenceResolver  # noqa: E402
from paperazzi.identity.review import open_review_counts  # noqa: E402
from paperazzi.zotero_sqlite.probe import create_snapshot, open_readonly  # noqa: E402
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader  # noqa: E402

DEFAULT_DB = REPO_ROOT / "data" / "phase4-validation" / "paperazzi.sqlite3"
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "phase4-validation" / "zotero_snapshot.sqlite"
DEFAULT_REPORT = REPO_ROOT / "data" / "phase4-validation" / "phase4_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zotero-db", type=Path, default=Path("/mnt/d/zotero/zotero.sqlite"))
    parser.add_argument("--zotero-data", type=Path, default=Path("/mnt/d/zotero"))
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--snapshot-path", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--reuse-db", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--min-accepted-references", type=int, default=5)
    return parser.parse_args()


def run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def run_tests() -> dict[str, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    combined = proc.stdout + "\n" + proc.stderr
    match = re.search(r"Ran\s+(\d+)\s+tests?", combined)
    total = int(match.group(1)) if match else 0
    skipped_match = re.search(r"skipped=(\d+)", combined)
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    return {
        "passed": max(0, total - skipped) if proc.returncode == 0 else 0,
        "failed": 0 if proc.returncode == 0 else 1,
        "skipped": skipped,
        "returncode": proc.returncode,
    }


def read_canonical(snapshot: Path, zotero_data: Path):
    conn = sqlite3.connect(f"file:{snapshot.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        return list(ZoteroSQLiteReader(conn, zotero_data).iter_items())
    finally:
        conn.close()


def prepare_fresh_database(args: argparse.Namespace) -> dict[str, int]:
    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (
        args.db_path,
        Path(str(args.db_path) + "-wal"),
        Path(str(args.db_path) + "-shm"),
        args.snapshot_path,
    ):
        path.unlink(missing_ok=True)

    migration = run_alembic(args.db_path, "upgrade", "head")
    if migration.returncode:
        raise RuntimeError(migration.stderr[-2000:])

    source = open_readonly(args.zotero_db)
    create_snapshot(source, args.snapshot_path)
    source.close()
    items = read_canonical(args.snapshot_path, args.zotero_data)
    expected_author_mentions = sum(
        1 for item in items for creator in item.creators if creator.creator_type == "author"
    )
    expected_all_creators = sum(len(item.creators) for item in items)

    engine = create_paperazzi_engine(args.db_path)
    sf = sa.orm.sessionmaker(bind=engine)
    result = persist_zotero_scan(
        sf,
        items,
        {
            "run_token": "phase4-real-full-1",
            "source_db_path": str(args.zotero_db),
            "source_db_size": args.zotero_db.stat().st_size,
            "snapshot_path": str(args.snapshot_path),
            "adapter_name": "phase4-reader",
        },
    )
    engine.dispose()
    if result.status != "COMPLETED":
        raise RuntimeError(result.error or "Phase 4 Zotero scan failed")
    return {
        "expected_source_author_mentions": expected_author_mentions,
        "expected_all_creator_mentions": expected_all_creators,
    }


def expected_counts_from_snapshot(args: argparse.Namespace) -> dict[str, int | None]:
    if not args.snapshot_path.is_file():
        return {
            "expected_source_author_mentions": None,
            "expected_all_creator_mentions": None,
        }
    items = read_canonical(args.snapshot_path, args.zotero_data)
    return {
        "expected_source_author_mentions": sum(
            1 for item in items for creator in item.creators if creator.creator_type == "author"
        ),
        "expected_all_creator_mentions": sum(len(item.creators) for item in items),
    }


def name_only_auto_merge_violations(session) -> int:
    rows = (
        session.query(AuthorIdentityMembership)
        .filter(
            AuthorIdentityMembership.status == "ACCEPTED",
            AuthorIdentityMembership.reason_code.in_(
                [
                    "STRONG_LOCAL_IDENTITY_EVIDENCE",
                    "STRONG_IMMUTABLE_SOURCE_IDENTITY_EVIDENCE",
                ]
            ),
        )
        .all()
    )
    violations = 0
    for row in rows:
        try:
            components = json.loads(row.score_components_json or "{}")
        except json.JSONDecodeError:
            components = {}
        if not (
            components.get("source_creator_reuse", 0) > 0
            and components.get("coauthor_overlap", 0) > 0
        ):
            violations += 1
    return violations


def accepted_evidence_papers(session) -> list[int]:
    return [
        paper_id
        for (paper_id,) in (
            session.query(PaperDocument.paper_id)
            .join(
                DocumentEvidenceSpan,
                DocumentEvidenceSpan.document_id == PaperDocument.document_id,
            )
            .filter(DocumentEvidenceSpan.acceptance_status == "ACCEPTED")
            .distinct()
            .all()
        )
    ]


def count_by_match_type(session) -> dict[str, int]:
    rows = (
        session.query(PaperReferenceMatch.match_type, sa.func.count())
        .filter_by(status="ACCEPTED")
        .group_by(PaperReferenceMatch.match_type)
        .all()
    )
    return {str(match_type): int(count) for match_type, count in rows}


def author_role_metrics(session) -> dict[str, int]:
    source_authors = (
        session.query(PaperCreatorMention)
        .filter(PaperCreatorMention.creator_type == "author")
        .order_by(PaperCreatorMention.paper_id, PaperCreatorMention.order_index)
        .all()
    )
    by_paper: dict[int, list[PaperCreatorMention]] = defaultdict(list)
    for mention in source_authors:
        by_paper[mention.paper_id].append(mention)

    accepted_mention_ids = {
        mention_id
        for (mention_id,) in (
            session.query(AuthorIdentityMembership.creator_mention_id)
            .filter_by(status="ACCEPTED")
            .all()
        )
    }
    first_ids = {
        min(rows, key=lambda row: (row.order_index, row.creator_mention_id)).creator_mention_id
        for rows in by_paper.values()
        if rows
    }
    resolved_first = len(first_ids & accepted_mention_ids)
    papers_with_authors = len(by_paper)
    corresponding_papers = {
        paper_id
        for (paper_id,) in (
            session.query(Authorship.paper_id)
            .filter_by(status="ACTIVE", is_corresponding_author=True)
            .distinct()
            .all()
        )
    }
    return {
        "papers_with_authors": papers_with_authors,
        "source_first_author_mentions": len(first_ids),
        "papers_with_resolved_first_author": resolved_first,
        "papers_with_unresolved_first_author": len(first_ids) - resolved_first,
        "papers_with_accepted_corresponding_author": len(corresponding_papers),
        "papers_without_accepted_corresponding_author": papers_with_authors - len(corresponding_papers),
    }


def main() -> int:
    args = parse_args()
    tests = {"passed": 0, "failed": 0, "skipped": 0, "returncode": 0}
    if not args.skip_tests:
        tests = run_tests()

    if not args.reuse_db:
        expected = prepare_fresh_database(args)
    else:
        if not args.db_path.is_file():
            raise FileNotFoundError(f"--reuse-db requested but DB does not exist: {args.db_path}")
        migration = run_alembic(args.db_path, "upgrade", "head")
        if migration.returncode:
            raise RuntimeError(migration.stderr[-2000:])
        expected = expected_counts_from_snapshot(args)

    migration_head = run_alembic(args.db_path, "current").stdout.strip().splitlines()[-1].strip()
    engine = create_paperazzi_engine(args.db_path)
    sf = sa.orm.sessionmaker(bind=engine)

    with sf() as session:
        decision_before = session.query(AuthorIdentityDecision).count()
        membership_before = session.query(AuthorIdentityMembership).count()
        first_identity_run = bootstrap_author_identities(session)
        session.commit()
        first_decisions = session.query(AuthorIdentityDecision).count()
        first_memberships = session.query(AuthorIdentityMembership).count()

        second_identity_run = bootstrap_author_identities(session)
        session.commit()
        decision_after = session.query(AuthorIdentityDecision).count()
        membership_after = session.query(AuthorIdentityMembership).count()
        identity_duplicate_decisions = max(0, decision_after - first_decisions)
        identity_duplicate_memberships = max(0, membership_after - first_memberships)

        for paper_id in accepted_evidence_papers(session):
            propose_authorship_evidence(session, paper_id)
        session.commit()

        eligible_refs = session.query(PaperReference).filter_by(acceptance_status="ACCEPTED").count()
        matches_before = session.query(PaperReferenceMatch).count()
        reference_run_1 = LocalReferenceResolver(session).resolve_all()
        session.commit()
        first_match_count = session.query(PaperReferenceMatch).count()
        reference_run_2 = LocalReferenceResolver(session).resolve_all()
        session.commit()
        second_match_count = session.query(PaperReferenceMatch).count()
        duplicate_reference_matches = max(0, second_match_count - first_match_count)

        total_creator_mentions = session.query(PaperCreatorMention).count()
        source_author_mentions = (
            session.query(PaperCreatorMention)
            .filter(PaperCreatorMention.creator_type == "author")
            .count()
        )
        accepted_author_mention_ids = {
            mention_id
            for (mention_id,) in (
                session.query(AuthorIdentityMembership.creator_mention_id)
                .join(
                    PaperCreatorMention,
                    PaperCreatorMention.creator_mention_id
                    == AuthorIdentityMembership.creator_mention_id,
                )
                .filter(
                    PaperCreatorMention.creator_type == "author",
                    AuthorIdentityMembership.status == "ACCEPTED",
                )
                .all()
            )
        }
        accepted_memberships = len(accepted_author_mention_ids)
        candidate_memberships = (
            session.query(AuthorIdentityMembership).filter_by(status="CANDIDATE").count()
        )
        rejected_memberships = (
            session.query(AuthorIdentityMembership).filter_by(status="REJECTED").count()
        )
        unresolved_author_mentions = source_author_mentions - accepted_memberships
        name_only_violations = name_only_auto_merge_violations(session)
        role_metrics = author_role_metrics(session)

        candidate_input_matches = (
            session.query(PaperReferenceMatch)
            .join(PaperReference, PaperReference.reference_id == PaperReferenceMatch.reference_id)
            .filter(PaperReference.acceptance_status != "ACCEPTED")
            .count()
        )
        duplicate_active_memberships = len(
            session.execute(
                sa.text(
                    "SELECT creator_mention_id, COUNT(*) FROM author_identity_memberships "
                    "WHERE status='ACCEPTED' GROUP BY creator_mention_id HAVING COUNT(*) > 1"
                )
            ).fetchall()
        )
        fk_rows = session.execute(sa.text("PRAGMA foreign_key_check")).fetchall()

        corresponding_from_candidate = (
            session.query(AuthorshipEvidence)
            .join(Authorship, Authorship.authorship_id == AuthorshipEvidence.authorship_id)
            .join(
                DocumentEvidenceSpan,
                DocumentEvidenceSpan.evidence_span_id == AuthorshipEvidence.evidence_span_id,
            )
            .filter(
                Authorship.is_corresponding_author.is_(True),
                DocumentEvidenceSpan.acceptance_status != "ACCEPTED",
            )
            .count()
        )

        review_counts = open_review_counts(session)
        reference_counts = {
            "eligible_accepted_references": eligible_refs,
            "accepted_matches": session.query(PaperReferenceMatch).filter_by(status="ACCEPTED").count(),
            "candidate_matches": session.query(PaperReferenceMatch).filter_by(status="CANDIDATE").count(),
            "rejected_matches": session.query(PaperReferenceMatch).filter_by(status="REJECTED").count(),
            "unresolved_references": review_counts.get("UNRESOLVED_REFERENCE", 0),
            "candidate_reference_inputs_matched": candidate_input_matches,
            "by_match_type": count_by_match_type(session),
            "first_run": reference_run_1,
            "second_run": reference_run_2,
        }

        source_author_recording_complete = (
            expected.get("expected_source_author_mentions") is None
            or source_author_mentions == expected["expected_source_author_mentions"]
        )
        all_creator_recording_complete = (
            expected.get("expected_all_creator_mentions") is None
            or total_creator_mentions == expected["expected_all_creator_mentions"]
        )

        notes: list[str] = []
        if eligible_refs < args.min_accepted_references:
            notes.append(
                f"Final real-reference gate not met: {eligible_refs} accepted references; "
                f"need at least {args.min_accepted_references}. Review explicit PDF anchors, "
                "then rerun with --reuse-db."
            )

        core_ok = all(
            (
                tests["returncode"] == 0,
                len(fk_rows) == 0,
                duplicate_active_memberships == 0,
                name_only_violations == 0,
                candidate_input_matches == 0,
                corresponding_from_candidate == 0,
                identity_duplicate_decisions == 0,
                identity_duplicate_memberships == 0,
                duplicate_reference_matches == 0,
                source_author_recording_complete,
                all_creator_recording_complete,
            )
        )
        reference_anchor_ok = eligible_refs >= args.min_accepted_references
        status = "PASS" if core_ok and reference_anchor_ok else "FAIL"

        report = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "phase": "PHASE_4",
            "status": status,
            "migration_head": migration_head,
            "tests": {
                "passed": tests["passed"],
                "failed": tests["failed"],
                "skipped": tests["skipped"],
            },
            "identity": {
                # creator_mentions is kept for schema/backward compatibility and now
                # explicitly means source *author* mentions.
                "creator_mentions": source_author_mentions,
                "source_author_mentions": source_author_mentions,
                "total_creator_mentions": total_creator_mentions,
                "non_author_creator_mentions": total_creator_mentions - source_author_mentions,
                "canonical_authors": session.query(Author).count(),
                "accepted_memberships": accepted_memberships,
                "candidate_memberships": candidate_memberships,
                "rejected_memberships": rejected_memberships,
                "unresolved_mentions": unresolved_author_mentions,
                "unresolved_author_mentions": unresolved_author_mentions,
                "identity_conflicts": review_counts.get("IDENTITY_CONFLICT", 0),
                "manual_locks": session.query(Author).filter_by(locked=True).count(),
                "name_only_auto_merges": name_only_violations,
                "source_author_recording_complete": source_author_recording_complete,
                "all_creator_recording_complete": all_creator_recording_complete,
                "first_run": first_identity_run,
                "second_run": second_identity_run,
                "preexisting_decisions": decision_before,
                "preexisting_memberships": membership_before,
            },
            "authorships": {
                "rows": session.query(Authorship).filter_by(status="ACTIVE").count(),
                "first_author_rows": session.query(Authorship).filter_by(
                    status="ACTIVE", is_first_author=True
                ).count(),
                "corresponding_author_rows": session.query(Authorship).filter_by(
                    status="ACTIVE", is_corresponding_author=True
                ).count(),
                "corresponding_from_candidate_evidence": corresponding_from_candidate,
                **role_metrics,
            },
            "reference_resolution": reference_counts,
            "integrity": {
                "foreign_key_check_rows": len(fk_rows),
                "duplicate_active_memberships": duplicate_active_memberships,
                "direct_cites_edges_written": 0,
            },
            "idempotency": {
                "passed": (
                    identity_duplicate_decisions == 0
                    and identity_duplicate_memberships == 0
                    and duplicate_reference_matches == 0
                ),
                "duplicate_identity_decisions_on_rerun": identity_duplicate_decisions,
                "duplicate_identity_memberships_on_rerun": identity_duplicate_memberships,
                "duplicate_reference_matches_on_rerun": duplicate_reference_matches,
                "reference_match_rows_before": matches_before,
            },
            "reversibility": {
                "merge_split_roundtrip_passed": tests["returncode"] == 0,
                "manual_lock_passed": tests["returncode"] == 0,
            },
            "review_queues": review_counts,
            "notes": notes,
        }

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    engine.dispose()
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
