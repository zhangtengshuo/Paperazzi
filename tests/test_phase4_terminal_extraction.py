"""Regression tests for terminal extraction states introduced in Phase 4 preflight."""

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
    DocumentExtractionRun,
    PaperDocument,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    ExtractionError,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    finalize_unaccepted_attempt,
    persist_evidence_spans,
    record_extraction_review,
)
from paperazzi.ingest.models import CanonicalAttachment, CanonicalZoteroItem  # noqa: E402


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


def make_item() -> CanonicalZoteroItem:
    return CanonicalZoteroItem(
        library_id=1,
        item_id=1,
        item_key="TERM",
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": "Terminal Extraction"},
        creators=(),
        collections=(),
        tags=(),
        attachments=(
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key="ATTTERM",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path="storage:ATTTERM/paper.pdf",
                resolved_path="/tmp/terminal.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash="terminal-hash",
            ),
        ),
    )


class Phase4TerminalExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "terminal.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.sf,
            [make_item()],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED")

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def start(self, session):
        document = session.query(PaperDocument).one()
        run = create_extraction_run(
            session, document.document_id, "FIRST_AVAILABLE", document.document_change_key
        )
        a1 = add_extraction_attempt(
            session,
            run,
            attempt_number=1,
            actor="DETERMINISTIC",
            strategy="deterministic-v3",
            text_source="PDF_NATIVE",
        )
        return document, run, a1

    def test_needs_ocr_completes_without_accepting_evidence(self) -> None:
        with self.sf() as session:
            document, run, a1 = self.start(session)
            persist_evidence_spans(
                session,
                document.document_id,
                a1,
                [{"kind": "affiliation", "page_index": 0, "text": "unreliable text"}],
            )
            record_extraction_review(
                session, a1, reviewer_type="LOCAL_AI", decision="NEEDS_OCR"
            )
            with self.assertRaises(ExtractionError):
                accept_attempt(session, run, a1)
            finalize_unaccepted_attempt(session, run, a1)
            session.commit()

            stored = session.get(DocumentExtractionRun, run.extraction_run_id)
            self.assertEqual(stored.status, "COMPLETED")
            self.assertEqual(stored.final_status, "NEEDS_OCR")
            self.assertIsNone(stored.accepted_attempt_id)
            self.assertEqual(
                session.query(DocumentEvidenceSpan).filter_by(acceptance_status="ACCEPTED").count(),
                0,
            )
            self.assertEqual(
                session.query(DocumentEvidenceSpan).filter_by(acceptance_status="REJECTED").count(),
                1,
            )

    def test_attempt3_cannot_request_attempt4(self) -> None:
        with self.sf() as session:
            _document, run, a1 = self.start(session)
            record_extraction_review(session, a1, reviewer_type="LOCAL_AI", decision="RETRY")
            a2 = add_extraction_attempt(
                session,
                run,
                attempt_number=2,
                actor="LOCAL_AI_CONTROLLED",
                strategy="TAIL_REFERENCE_RECOVERY",
                text_source="PDF_NATIVE",
            )
            record_extraction_review(session, a2, reviewer_type="LOCAL_AI", decision="RETRY")
            a3 = add_extraction_attempt(
                session,
                run,
                attempt_number=3,
                actor="LOCAL_AI_CONTROLLED",
                strategy="BLOCK_COLUMN_RECONSTRUCTION",
                text_source="PDF_NATIVE",
            )
            with self.assertRaises(ExtractionError):
                record_extraction_review(
                    session, a3, reviewer_type="LOCAL_AI", decision="RETRY"
                )

    def test_accept_partial_is_an_accepted_terminal_state(self) -> None:
        with self.sf() as session:
            document, run, a1 = self.start(session)
            persist_evidence_spans(
                session,
                document.document_id,
                a1,
                [{"kind": "affiliation", "page_index": 0, "text": "usable evidence"}],
            )
            record_extraction_review(
                session,
                a1,
                reviewer_type="LOCAL_AI",
                decision="ACCEPT_PARTIAL",
                entry_text_quality="PARTIAL",
            )
            accept_attempt(session, run, a1)
            session.commit()
            stored = session.get(DocumentExtractionRun, run.extraction_run_id)
            self.assertEqual(stored.final_status, "ACCEPT_PARTIAL")
            self.assertEqual(stored.accepted_attempt_id, a1.attempt_id)
            self.assertEqual(
                session.query(DocumentEvidenceSpan).filter_by(acceptance_status="ACCEPTED").count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
