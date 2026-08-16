"""Phase 3C/3.1 gate tests — extraction, mandatory review and evidence persistence."""

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
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionReview,
    DocumentExtractionRun,
    Paper,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    ExtractionError,
    PROMPT_HASH,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    decide_extraction_trigger,
    persist_evidence_spans,
    persist_reference_section,
    record_extraction_review,
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


def make_item(key: str = "AAAAAA", storage_hash: str | None = "h1") -> CanonicalZoteroItem:
    return CanonicalZoteroItem(
        library_id=1,
        item_id=1,
        item_key=key,
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": f"Paper {key}"},
        creators=(),
        collections=(),
        tags=(),
        attachments=(
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key=f"ATT_{key}",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path=f"storage:ATT_{key}/a.pdf",
                resolved_path=f"/mnt/x/ATT_{key}/a.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash=storage_hash,
            ),
        ),
    )


class Phase3EvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ev.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.engine = create_paperazzi_engine(self.db)
        self.session_factory = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.session_factory,
            [make_item()],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED")

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def document_id(self) -> int:
        with self.session_factory() as s:
            return s.query(PaperDocument).one().document_id

    def test_unreviewed_attempt_cannot_be_accepted(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self.document_id())
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            attempt = add_extraction_attempt(
                s,
                run,
                attempt_number=1,
                actor="DETERMINISTIC",
                strategy="deterministic-v3",
                text_source="PDF_NATIVE",
            )
            self.assertEqual(attempt.decision, "REVIEW_PENDING")
            with self.assertRaises(ExtractionError):
                accept_attempt(s, run, attempt, "PASS")

    def test_review_acceptance_and_foreign_keys(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self.document_id())
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            attempt = add_extraction_attempt(
                s,
                run,
                attempt_number=1,
                actor="DETERMINISTIC",
                strategy="deterministic-v3",
                text_source="PDF_NATIVE",
                text_channel="PYMUPDF_SORTED",
                channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
                section_confidence="HIGH",
                segmentation_confidence="HIGH",
            )
            review = record_extraction_review(
                s,
                attempt,
                reviewer_type="LOCAL_AI",
                decision="PASS",
                section_confidence="HIGH",
                segmentation_confidence="HIGH",
                entry_text_quality="GOOD",
            )
            self.assertEqual(review.prompt_hash, PROMPT_HASH)
            accept_attempt(s, run, attempt, "PASS")
            s.commit()

        with self.session_factory() as s:
            run = s.query(DocumentExtractionRun).one()
            attempt = s.query(DocumentExtractionAttempt).one()
            self.assertEqual(run.accepted_attempt_id, attempt.attempt_id)
            self.assertEqual(s.query(DocumentExtractionReview).count(), 1)
            self.assertEqual(
                s.get(PaperDocument, self.document_id()).current_extraction_run_id,
                run.extraction_run_id,
            )
            self.assertEqual(s.execute(sa.text("PRAGMA foreign_key_check")).fetchall(), [])

    def test_pending_run_blocks_duplicate_trigger(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self.document_id())
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            add_extraction_attempt(
                s,
                run,
                attempt_number=1,
                actor="DETERMINISTIC",
                strategy="deterministic-v3",
                text_source="PDF_NATIVE",
            )
            s.flush()
            self.assertIsNone(
                decide_extraction_trigger(doc, doc.document_change_key, "deterministic-v3", PROMPT_HASH)
            )
            with self.assertRaises(ExtractionError):
                create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)

    def test_accept_supersedes_without_deleting(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self.document_id())
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            a1 = add_extraction_attempt(
                s, run, attempt_number=1, actor="DETERMINISTIC",
                strategy="deterministic-v3", text_source="PDF_NATIVE"
            )
            record_extraction_review(
                s, a1, reviewer_type="LOCAL_AI", decision="RETRY",
                problem_codes=["reference-section-not-found"]
            )
            a2 = add_extraction_attempt(
                s, run, attempt_number=2, actor="LOCAL_AI_CONTROLLED",
                strategy="TAIL_REFERENCE_RECOVERY", text_source="PDF_NATIVE"
            )
            persist_evidence_spans(
                s, doc.document_id, a1,
                [{"kind": "affiliation", "page_index": 0, "text": "Candidate A"}],
            )
            persist_evidence_spans(
                s, doc.document_id, a2,
                [{"kind": "affiliation", "page_index": 0, "text": "Accepted A"}],
            )
            sec = ReferenceSection(
                heading="References",
                start_page=9,
                end_page=10,
                method="numbered-punctuated",
                confidence="HIGH",
                raw_text="raw...",
                entries=(
                    ReferenceEntry(
                        ordinal=1,
                        raw_text="A. Author, J. Chem. 1 (2000)",
                        dois=("10.1/x",),
                        years=("2000",),
                    ),
                ),
                text_channel="PYMUPDF_SORTED",
            )
            persist_reference_section(s, s.query(Paper).one().paper_id, doc.document_id, a2, sec)
            record_extraction_review(
                s,
                a2,
                reviewer_type="LOCAL_AI",
                decision="PASS",
                section_confidence="HIGH",
                segmentation_confidence="HIGH",
                entry_text_quality="GOOD",
            )
            accept_attempt(s, run, a2, "PASS")
            s.commit()

        with self.session_factory() as s:
            self.assertEqual(s.query(DocumentExtractionAttempt).count(), 2)
            self.assertEqual(
                s.query(DocumentEvidenceSpan).filter_by(acceptance_status="SUPERSEDED").count(), 1
            )
            self.assertEqual(
                s.query(DocumentEvidenceSpan).filter_by(acceptance_status="ACCEPTED").count(), 1
            )
            section = s.query(PaperReferenceSection).one()
            self.assertEqual(section.acceptance_status, "ACCEPTED")
            self.assertEqual(section.entry_text_quality, "GOOD")
            self.assertEqual(s.query(PaperReference).one().ordinal, 1)
            self.assertEqual(
                {row.identifier_type for row in s.query(PaperReferenceIdentifier).all()},
                {"DOI", "YEAR"},
            )

    def test_raw_section_has_high_section_but_no_segmentation_confidence(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self.document_id())
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            attempt = add_extraction_attempt(
                s, run, attempt_number=1, actor="DETERMINISTIC",
                strategy="deterministic-v3", text_source="PDF_NATIVE"
            )
            sec = ReferenceSection(
                heading="References",
                start_page=26,
                end_page=28,
                method="raw-author-year-or-unsegmented",
                confidence="MEDIUM",
                raw_text="AUSLANDER, L...\nBELL, E. T...",
                entries=(),
                text_channel="PYMUPDF_SORTED",
            )
            persist_reference_section(s, s.query(Paper).one().paper_id, doc.document_id, attempt, sec)
            s.flush()
            section = s.query(PaperReferenceSection).one()
            self.assertEqual(section.section_confidence, "HIGH")
            self.assertIsNone(section.segmentation_confidence)
            self.assertEqual(section.entry_text_quality, "UNREVIEWED")
            self.assertEqual(section.acceptance_status, "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
