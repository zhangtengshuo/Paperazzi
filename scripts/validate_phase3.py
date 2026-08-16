#!/usr/bin/env python3
"""Phase 3.1 — real-library persistence-hardening validation.

Creates a fresh ignored Paperazzi DB, performs two identical full Zotero scans,
persists the frozen-v3 200-PDF sample as *candidate* Attempt-1 evidence, and verifies
that unreviewed deterministic output never becomes accepted state.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sqlalchemy as sa  # noqa: E402

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionReview,
    DocumentExtractionRun,
    Paper,
    PaperCreatorMention,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
    ZoteroAttachment,
    ZoteroItemState,
    ZoteroItemVersion,
    ZoteroScanRun,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    EXTRACTOR_VERSION,
    PROMPT_HASH,
    add_extraction_attempt,
    create_extraction_run,
    decide_extraction_trigger,
    deterministic_reference_quality,
    persist_evidence_spans,
    persist_reference_section,
)
from paperazzi.ingest.models import CanonicalZoteroItem  # noqa: E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa: E402
from paperazzi.zotero_sqlite.probe import create_snapshot, open_readonly  # noqa: E402
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader  # noqa: E402

ZOTERO_DB = Path("/mnt/d/zotero/zotero.sqlite")
ZOTERO_DATA = Path("/mnt/d/zotero")
RUN_DIR = REPO_ROOT / "data" / "phase3-validation"
DB_PATH = RUN_DIR / "paperazzi.sqlite3"
SNAPSHOT = RUN_DIR / "zotero_snapshot.sqlite"
V3_REPORT = REPO_ROOT / "pdf-evidence-output/20260817-022324-pdf-evidence-v3/pdf_evidence_report.json"
ANCHOR_KEYS = {"I97Q72KK", "MD8N7CDD", "QRV8DDP9", "J99X9MWN", "87JCS8EY"}


def read_canonical(snapshot: Path) -> list[CanonicalZoteroItem]:
    conn = sqlite3.connect(f"file:{snapshot.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        reader = ZoteroSQLiteReader(conn, ZOTERO_DATA)
        return list(reader.iter_items())
    finally:
        conn.close()


def report_scan(session_factory, items: list[CanonicalZoteroItem], token: str):
    result = persist_zotero_scan(
        session_factory,
        items,
        {
            "run_token": token,
            "source_db_path": str(ZOTERO_DB),
            "source_db_size": ZOTERO_DB.stat().st_size,
            "snapshot_path": str(SNAPSHOT),
            "adapter_name": "userdata125-global42",
            "userdata_version": 125,
            "global_schema_version": 42,
        },
    )
    assert result.status == "COMPLETED", result.error
    return result.counts


def expected_pdf_counts(items: list[CanonicalZoteroItem]) -> tuple[int, int]:
    records = 0
    available = 0
    for item in items:
        for att in item.attachments:
            if (att.content_type or "").lower() != "application/pdf":
                continue
            records += 1
            if att.local_exists is True and att.resolved_path and Path(att.resolved_path).is_file():
                available += 1
    return records, available


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for path in (DB_PATH, Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm"), SNAPSHOT):
        path.unlink(missing_ok=True)

    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{DB_PATH}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    migration_head = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().splitlines()[-1].strip()

    engine = create_paperazzi_engine(DB_PATH)
    session_factory = sa.orm.sessionmaker(bind=engine)

    source = open_readonly(ZOTERO_DB)
    create_snapshot(source, SNAPSHOT)
    source.close()

    items1 = read_canonical(SNAPSHOT)
    expected_pdf_records, expected_available_pdfs = expected_pdf_counts(items1)
    first = report_scan(session_factory, items1, "real-full-1")
    items2 = read_canonical(SNAPSHOT)
    assert len(items2) == len(items1)
    second = report_scan(session_factory, items2, "real-full-2")

    with session_factory() as session:
        fk_rows = session.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        counts = {
            "full_zotero_item_count": session.query(ZoteroItemState).count(),
            "paper_count": session.query(Paper).count(),
            "creator_mention_count": session.query(PaperCreatorMention).count(),
            "attachment_count": session.query(ZoteroAttachment).count(),
            "pdf_document_count": session.query(PaperDocument).count(),
            "local_pdf_available_count": session.query(PaperDocument).filter_by(
                availability_status="PDF_AVAILABLE"
            ).count(),
            "item_version_rows": session.query(ZoteroItemVersion).count(),
        }
        non_pdf_documents = session.query(PaperDocument).filter(
            sa.func.lower(PaperDocument.content_type) != "application/pdf"
        ).count()
        duplicate_identities = session.execute(
            sa.text(
                "SELECT library_id, item_key, COUNT(*) FROM zotero_item_state "
                "GROUP BY library_id, item_key HAVING COUNT(*) > 1"
            )
        ).fetchall()

    assert counts["pdf_document_count"] == expected_pdf_records, (
        counts["pdf_document_count"], expected_pdf_records
    )
    assert counts["local_pdf_available_count"] == expected_available_pdfs, (
        counts["local_pdf_available_count"], expected_available_pdfs
    )
    assert non_pdf_documents == 0

    v3 = json.load(open(V3_REPORT, encoding="utf-8"))
    sample_keys = [sample["attachment_key"] for sample in v3["samples"]][:200]
    runs_created = attempts = spans = sections = refs = identifiers = 0
    anchor_state: dict[str, dict[str, object]] = {}

    with session_factory() as session:
        for index, attachment_key in enumerate(sample_keys):
            att = session.query(ZoteroAttachment).filter_by(
                library_id=1, item_key=attachment_key
            ).one_or_none()
            if att is None:
                continue
            document = session.query(PaperDocument).filter_by(
                zotero_attachment_id=att.zotero_attachment_id
            ).one_or_none()
            if document is None or document.availability_status != "PDF_AVAILABLE":
                continue
            path = document.local_path
            if not path or not Path(path).is_file():
                continue

            trigger = decide_extraction_trigger(
                document,
                document.document_change_key,
                EXTRACTOR_VERSION,
                PROMPT_HASH,
            )
            if trigger is None:
                continue
            run = create_extraction_run(
                session,
                document.document_id,
                trigger,
                document.document_change_key,
            )
            runs_created += 1
            evidence = extract_pdf_evidence(path)
            section_confidence, segmentation_confidence, entry_text_quality = (
                deterministic_reference_quality(evidence.references)
            )
            attempt = add_extraction_attempt(
                session,
                run,
                attempt_number=1,
                actor="DETERMINISTIC",
                strategy="deterministic-v3",
                text_source="PDF_NATIVE",
                backend="PyMuPDF",
                backend_version=evidence.backend_version,
                text_channel=evidence.references.text_channel if evidence.references else None,
                channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
                section_confidence=section_confidence,
                segmentation_confidence=segmentation_confidence,
                entry_text_quality=entry_text_quality,
                reference_status=(
                    "SEGMENTED"
                    if evidence.references and evidence.references.entries
                    else (
                        "RAW_SECTION_ONLY"
                        if evidence.references
                        else "NO_REFERENCE_SECTION_FOUND"
                    )
                ),
            )
            attempts += 1
            spans += persist_evidence_spans(
                session,
                document.document_id,
                attempt,
                [
                    {"kind": "affiliation", "page_index": span.page_index, "text": span.text}
                    for span in evidence.affiliation_candidates[:4]
                ]
                + [
                    {"kind": "correspondence", "page_index": span.page_index, "text": span.text}
                    for span in evidence.correspondence_candidates[:2]
                ],
                text_source="PDF_NATIVE",
                text_channel="PYMUPDF_SORTED",
            )
            if evidence.references is not None:
                persist_reference_section(
                    session,
                    document.paper_id,
                    document.document_id,
                    attempt,
                    evidence.references,
                )
                sections += 1
                refs += len(evidence.references.entries)
                identifiers += sum(
                    len(entry.dois) + len(entry.years)
                    for entry in evidence.references.entries
                )

            if attachment_key in ANCHOR_KEYS:
                anchor_state[attachment_key] = {
                    "method": evidence.references.method if evidence.references else None,
                    "entries": len(evidence.references.entries) if evidence.references else 0,
                    "text_channel": evidence.references.text_channel if evidence.references else None,
                    "section_confidence": section_confidence,
                    "segmentation_confidence": segmentation_confidence,
                    "entry_text_quality": entry_text_quality,
                }
            if index % 50 == 0:
                session.commit()
        session.commit()

    # Candidate state must be review-gated: no deterministic Attempt 1 may already be accepted.
    with session_factory() as session:
        candidate_state = {
            "started_runs": session.query(DocumentExtractionRun).filter_by(status="STARTED").count(),
            "pending_attempts": session.query(DocumentExtractionAttempt).filter_by(
                decision="REVIEW_PENDING"
            ).count(),
            "review_rows": session.query(DocumentExtractionReview).count(),
            "accepted_evidence": session.query(DocumentEvidenceSpan).filter_by(
                acceptance_status="ACCEPTED"
            ).count(),
            "accepted_sections": session.query(PaperReferenceSection).filter_by(
                acceptance_status="ACCEPTED"
            ).count(),
            "accepted_references": session.query(PaperReference).filter_by(
                acceptance_status="ACCEPTED"
            ).count(),
            "documents_with_current_run": session.query(PaperDocument).filter(
                PaperDocument.current_extraction_run_id.is_not(None)
            ).count(),
        }
        rerun = 0
        for attachment_key in sample_keys[:20]:
            att = session.query(ZoteroAttachment).filter_by(
                library_id=1, item_key=attachment_key
            ).one_or_none()
            if att is None:
                continue
            document = session.query(PaperDocument).filter_by(
                zotero_attachment_id=att.zotero_attachment_id
            ).one_or_none()
            if document is None:
                continue
            if decide_extraction_trigger(
                document,
                document.document_change_key,
                EXTRACTOR_VERSION,
                PROMPT_HASH,
            ) is not None:
                rerun += 1

    assert candidate_state["review_rows"] == 0
    assert candidate_state["accepted_evidence"] == 0
    assert candidate_state["accepted_sections"] == 0
    assert candidate_state["accepted_references"] == 0
    assert candidate_state["documents_with_current_run"] == 0
    assert rerun == 0

    tmp_db = RUN_DIR / "injection.sqlite3"
    for path in (tmp_db, Path(str(tmp_db) + "-wal"), Path(str(tmp_db) + "-shm")):
        path.unlink(missing_ok=True)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{tmp_db}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    tmp_engine = create_paperazzi_engine(tmp_db)
    tmp_sf = sa.orm.sessionmaker(bind=tmp_engine)
    injected = persist_zotero_scan(
        tmp_sf,
        [items1[0], items1[0]],
        {"run_token": "inject-1", "source_db_path": str(ZOTERO_DB)},
    )
    with tmp_sf() as session:
        run_row = session.query(ZoteroScanRun).filter_by(run_token="inject-1").one()
        rollback_injection = {
            "scan_status": injected.status,
            "run_row_status": run_row.status,
            "papers_rows": session.query(Paper).count(),
        }
    tmp_engine.dispose()

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "phase": "PHASE_3_1_HARDENING",
        "migration_head": migration_head,
        "first_scan": first,
        "second_scan": second,
        "counts": counts,
        "expected_pdf_document_count": expected_pdf_records,
        "expected_local_pdf_available_count": expected_available_pdfs,
        "non_pdf_document_count": non_pdf_documents,
        "duplicate_identity_count": len(duplicate_identities),
        "fk_check_rows": len(fk_rows),
        "pdf_sample": {
            "sample_size": len(sample_keys),
            "extraction_runs_created": runs_created,
            "attempt_count": attempts,
            "evidence_span_count": spans,
            "reference_section_count": sections,
            "reference_entry_count": refs,
            "reference_identifier_count": identifiers,
            "anchors": anchor_state,
        },
        "review_gate": candidate_state,
        "pending_run_idempotency_reruns": rerun,
        "rollback_injection_result": rollback_injection,
    }
    report_path = RUN_DIR / "phase3_hardening_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
