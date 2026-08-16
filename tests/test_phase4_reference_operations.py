"""Tests for Phase 4 AI/manual reference decision operations."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    Paper,
    PaperDocument,
    PaperReference,
    PaperReferenceMatch,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    persist_reference_section,
    record_extraction_review,
)
from paperazzi.identity.models import ReferenceMatchEvidence  # noqa: E402
from paperazzi.identity.reference_operations import (  # noqa: E402
    ReferenceResolutionError,
    accept_reviewed_reference_match,
)
from paperazzi.ingest.models import CanonicalAttachment, CanonicalZoteroItem  # noqa: E402
from paperazzi.local_evidence.pdf import ReferenceEntry, ReferenceSection  # noqa: E402


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def item(key: str, item_id: int, title: str, pdf: bool = False) -> CanonicalZoteroItem:
    attachments = ()
    if pdf:
        attachments = (
            CanonicalAttachment(
                library_id=1,
                item_id=item_id + 100,
                item_key=f"ATT{key}",
                parent_item_id=item_id,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path=f"storage:ATT{key}/paper.pdf",
                resolved_path=f"/tmp/{key}.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash=f"hash-{key}",
            ),
        )
    return CanonicalZoteroItem(
        library_id=1,
        item_id=item_id,
        item_key=key,
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": title, "date": "2020"},
        creators=(),
        collections=(),
        tags=(),
        attachments=attachments,
    )


class Phase4ReferenceOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "refops.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.sf,
            [
                item("C", 1, "Citing", pdf=True),
                item("A", 2, "Candidate A"),
                item("B", 3, "Candidate B"),
            ],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED")

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def make_reference(self, session, accepted: bool = True) -> PaperReference:
        citing = session.query(Paper).filter_by(title="Citing").one()
        document = session.query(PaperDocument).filter_by(paper_id=citing.paper_id).one()
        run = create_extraction_run(
            session, document.document_id, "FIRST_AVAILABLE", document.document_change_key
        )
        attempt = add_extraction_attempt(
            session,
            run,
            attempt_number=1,
            actor="DETERMINISTIC",
            strategy="test",
            text_source="PDF_NATIVE",
        )
        section = ReferenceSection(
            heading="References",
            start_page=1,
            end_page=1,
            method="numbered-punctuated",
            confidence="HIGH",
            raw_text="Ambiguous local reference 2020",
            entries=(
                ReferenceEntry(
                    ordinal=1,
                    raw_text="Ambiguous local reference 2020",
                    dois=(),
                    years=("2020",),
                ),
            ),
            text_channel="PYMUPDF_SORTED",
        )
        persist_reference_section(
            session, citing.paper_id, document.document_id, attempt, section
        )
        if accepted:
            record_extraction_review(
                session, attempt, reviewer_type="MANUAL", decision="PASS"
            )
            accept_attempt(session, run, attempt)
        session.flush()
        return session.query(PaperReference).filter_by(citing_paper_id=citing.paper_id).one()

    def test_unaccepted_reference_cannot_be_review_resolved(self) -> None:
        with self.sf() as session:
            reference = self.make_reference(session, accepted=False)
            target = session.query(Paper).filter_by(title="Candidate A").one()
            with self.assertRaises(ReferenceResolutionError):
                accept_reviewed_reference_match(
                    session,
                    reference.reference_id,
                    target.paper_id,
                    actor="LOCAL_AI",
                    resolver_version="test-model",
                )

    def test_self_match_is_forbidden_for_reviewed_decision(self) -> None:
        with self.sf() as session:
            reference = self.make_reference(session, accepted=True)
            with self.assertRaises(ReferenceResolutionError):
                accept_reviewed_reference_match(
                    session,
                    reference.reference_id,
                    reference.citing_paper_id,
                    actor="MANUAL",
                    resolver_version="manual-v1",
                )

    def test_reviewed_acceptance_rejects_competing_candidate_history(self) -> None:
        with self.sf() as session:
            reference = self.make_reference(session, accepted=True)
            a = session.query(Paper).filter_by(title="Candidate A").one()
            b = session.query(Paper).filter_by(title="Candidate B").one()
            session.add_all(
                [
                    PaperReferenceMatch(
                        reference_id=reference.reference_id,
                        cited_paper_id=a.paper_id,
                        match_type="BIBLIOGRAPHIC_COMPOSITE",
                        match_score=0.70,
                        status="CANDIDATE",
                        resolver="deterministic",
                    ),
                    PaperReferenceMatch(
                        reference_id=reference.reference_id,
                        cited_paper_id=b.paper_id,
                        match_type="BIBLIOGRAPHIC_COMPOSITE",
                        match_score=0.68,
                        status="CANDIDATE",
                        resolver="deterministic",
                    ),
                ]
            )
            session.flush()
            accepted = accept_reviewed_reference_match(
                session,
                reference.reference_id,
                a.paper_id,
                actor="LOCAL_AI",
                resolver_version="model-v1",
                notes="PDF/reference context reviewed",
                score=0.95,
            )
            session.commit()
            self.assertEqual(accepted.status, "ACCEPTED")
            self.assertEqual(accepted.match_type, "AI_RESOLVED")
            self.assertTrue(accepted.resolver.startswith("LOCAL_AI:"))
            competing = (
                session.query(PaperReferenceMatch)
                .filter_by(reference_id=reference.reference_id, cited_paper_id=b.paper_id)
                .one()
            )
            self.assertEqual(competing.status, "REJECTED")
            self.assertEqual(
                session.query(ReferenceMatchEvidence)
                .filter_by(reference_match_id=accepted.reference_match_id)
                .count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
