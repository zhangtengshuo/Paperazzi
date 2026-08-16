"""Phase 4 preflight regression tests for extraction review state-machine guards."""

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
from paperazzi.database.models import DocumentExtractionRun, PaperDocument  # noqa: E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    ExtractionError,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
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
        item_key="ITEM",
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": "Paper"},
        creators=(),
        collections=(),
        tags=(),
        attachments=(
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key="ATT",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path="storage:ATT/paper.pdf",
                resolved_path="/tmp/paper.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash="h1",
            ),
        ),
    )


class Phase4PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "preflight.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
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

    def _start(self, session):
        doc = session.query(PaperDocument).one()
        run = create_extraction_run(
            session, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key
        )
        a1 = add_extraction_attempt(
            session,
            run,
            attempt_number=1,
            actor="DETERMINISTIC",
            strategy="deterministic-v3",
            text_source="PDF_NATIVE",
        )
        return run, a1

    def test_attempt2_requires_attempt1_retry_review(self) -> None:
        with self.sf() as session:
            run, a1 = self._start(session)
            with self.assertRaises(ExtractionError):
                add_extraction_attempt(
                    session,
                    run,
                    attempt_number=2,
                    actor="LOCAL_AI_CONTROLLED",
                    strategy="TAIL_REFERENCE_RECOVERY",
                    text_source="PDF_NATIVE",
                )
            record_extraction_review(
                session, a1, reviewer_type="LOCAL_AI", decision="PASS"
            )
            with self.assertRaises(ExtractionError):
                add_extraction_attempt(
                    session,
                    run,
                    attempt_number=2,
                    actor="LOCAL_AI_CONTROLLED",
                    strategy="TAIL_REFERENCE_RECOVERY",
                    text_source="PDF_NATIVE",
                )

    def test_attempt2_and_attempt3_require_consecutive_retry(self) -> None:
        with self.sf() as session:
            run, a1 = self._start(session)
            record_extraction_review(
                session, a1, reviewer_type="LOCAL_AI", decision="RETRY"
            )
            a2 = add_extraction_attempt(
                session,
                run,
                attempt_number=2,
                actor="LOCAL_AI_CONTROLLED",
                strategy="TAIL_REFERENCE_RECOVERY",
                text_source="PDF_NATIVE",
            )
            with self.assertRaises(ExtractionError):
                add_extraction_attempt(
                    session,
                    run,
                    attempt_number=3,
                    actor="LOCAL_AI_CONTROLLED",
                    strategy="BLOCK_COLUMN_RECONSTRUCTION",
                    text_source="PDF_NATIVE",
                )
            record_extraction_review(
                session, a2, reviewer_type="LOCAL_AI", decision="RETRY"
            )
            a3 = add_extraction_attempt(
                session,
                run,
                attempt_number=3,
                actor="LOCAL_AI_CONTROLLED",
                strategy="BLOCK_COLUMN_RECONSTRUCTION",
                text_source="PDF_NATIVE",
            )
            self.assertEqual(a3.attempt_number, 3)

    def test_final_status_is_owned_by_latest_review(self) -> None:
        with self.sf() as session:
            run, a1 = self._start(session)
            record_extraction_review(
                session, a1, reviewer_type="LOCAL_AI", decision="PASS"
            )
            with self.assertRaises(ExtractionError):
                accept_attempt(session, run, a1, "ACCEPT_PARTIAL")
            accept_attempt(session, run, a1)
            session.commit()
            stored = session.get(DocumentExtractionRun, run.extraction_run_id)
            self.assertEqual(stored.final_status, "PASS")
            self.assertEqual(stored.status, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
