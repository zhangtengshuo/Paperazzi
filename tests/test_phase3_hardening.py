"""Phase 3.1 regression tests for persistence-hardening bugs."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentExtractionAttempt,
    DocumentExtractionReview,
    DocumentExtractionRun,
    PaperCreatorMention,
    PaperDocument,
    ZoteroAttachment,
)
from paperazzi.database.persistence import CHANGE_UNCHANGED, persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    PROMPT_HASH,
    PROMPT_PATH,
    decide_extraction_trigger,
)
from paperazzi.ingest.models import (  # noqa: E402
    CanonicalAttachment,
    CanonicalCreator,
    CanonicalTag,
    CanonicalZoteroItem,
)


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


def make_item(
    *,
    attachment: CanonicalAttachment | None = None,
    tag: str = "t1",
    creator_last: str = "Author",
) -> CanonicalZoteroItem:
    attachments = () if attachment is None else (attachment,)
    return CanonicalZoteroItem(
        library_id=1,
        item_id=1,
        item_key="ITEM1",
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": "Paper A"},
        creators=(
            CanonicalCreator(
                creator_id=10,
                creator_type="author",
                order_index=0,
                first_name="A.",
                last_name=creator_last,
            ),
        ),
        collections=(),
        tags=(CanonicalTag(tag_id=1, name=tag, tag_type=0),),
        attachments=attachments,
    )


def attachment(
    path: Path,
    *,
    content_type: str = "application/pdf",
    local_exists: bool = True,
    resolution: str = "zotero-storage",
    storage_hash: str | None = "h1",
) -> CanonicalAttachment:
    stored_path = "storage:ATT1/a.pdf" if resolution == "zotero-storage" else str(path)
    return CanonicalAttachment(
        library_id=1,
        item_id=2,
        item_key="ATT1",
        parent_item_id=1,
        link_mode=0 if resolution == "zotero-storage" else 2,
        link_mode_name="imported_file" if resolution == "zotero-storage" else "linked_file",
        content_type=content_type,
        path=stored_path,
        resolved_path=str(path),
        local_exists=local_exists,
        resolution=resolution,
        storage_hash=storage_hash,
    )


class Phase31HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "hardening.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def scan(self, item: CanonicalZoteroItem | None, token: str):
        return persist_zotero_scan(
            self.sf,
            [] if item is None else [item],
            {"run_token": token, "source_db_path": "/tmp/fake"},
        )

    def test_non_pdf_attachment_never_becomes_paper_document(self) -> None:
        html = self.root / "snapshot.html"
        html.write_text("<html></html>")
        result = self.scan(
            make_item(attachment=attachment(html, content_type="text/html")), "s1"
        )
        self.assertEqual(result.status, "COMPLETED")
        with self.sf() as s:
            self.assertEqual(s.query(ZoteroAttachment).count(), 1)
            self.assertEqual(s.query(PaperDocument).count(), 0)

    def test_unchanged_item_refreshes_pdf_runtime_availability(self) -> None:
        pdf = self.root / "a.pdf"
        missing = attachment(pdf, local_exists=False, storage_hash="same")
        self.scan(make_item(attachment=missing), "s1")
        with self.sf() as s:
            doc = s.query(PaperDocument).one()
            self.assertEqual(doc.availability_status, "PDF_RECORD_ONLY")

        pdf.write_bytes(b"%PDF-1.4\nlocal")
        present = attachment(pdf, local_exists=True, storage_hash="same")
        result = self.scan(make_item(attachment=present), "s2")
        self.assertEqual(result.counts[CHANGE_UNCHANGED], 1)
        with self.sf() as s:
            doc = s.query(PaperDocument).one()
            self.assertEqual(doc.availability_status, "PDF_AVAILABLE")
            self.assertEqual(doc.file_size, pdf.stat().st_size)
            self.assertEqual(doc.file_mtime_ns, pdf.stat().st_mtime_ns)
            self.assertEqual(
                decide_extraction_trigger(doc, doc.document_change_key, "deterministic-v3", PROMPT_HASH),
                "FIRST_AVAILABLE",
            )

    def test_linked_absolute_pdf_uses_filesystem_change_key(self) -> None:
        pdf = self.root / "linked.pdf"
        pdf.write_bytes(b"linked-pdf")
        linked = attachment(
            pdf,
            resolution="linked-absolute-path",
            storage_hash=None,
            local_exists=True,
        )
        self.scan(make_item(attachment=linked), "s1")
        with self.sf() as s:
            doc = s.query(PaperDocument).one()
            self.assertEqual(doc.availability_status, "PDF_AVAILABLE")
            self.assertEqual(doc.local_path, str(pdf))
            self.assertEqual(
                doc.document_change_key,
                f"fs:{pdf.stat().st_size}:{pdf.stat().st_mtime_ns}",
            )

    def test_parent_and_child_removal_propagate_to_document(self) -> None:
        pdf = self.root / "a.pdf"
        pdf.write_bytes(b"pdf")
        item = make_item(attachment=attachment(pdf))
        self.scan(item, "s1")
        self.scan(None, "s2")
        with self.sf() as s:
            self.assertFalse(s.query(ZoteroAttachment).one().present_in_last_scan)
            self.assertFalse(s.query(PaperDocument).one().present_in_last_scan)
        self.scan(item, "s3")
        with self.sf() as s:
            self.assertTrue(s.query(ZoteroAttachment).one().present_in_last_scan)
            self.assertTrue(s.query(PaperDocument).one().present_in_last_scan)
        # Parent remains but child attachment disappears.
        self.scan(make_item(attachment=None), "s4")
        with self.sf() as s:
            self.assertFalse(s.query(ZoteroAttachment).one().present_in_last_scan)
            self.assertFalse(s.query(PaperDocument).one().present_in_last_scan)

    def test_creator_mention_id_survives_nonbibliographic_changes(self) -> None:
        pdf = self.root / "a.pdf"
        pdf.write_bytes(b"pdf")
        item = make_item(attachment=attachment(pdf), tag="t1")
        self.scan(item, "s1")
        with self.sf() as s:
            original_id = s.query(PaperCreatorMention).one().creator_mention_id
        self.scan(replace(item, tags=(CanonicalTag(tag_id=2, name="t2", tag_type=0),)), "s2")
        with self.sf() as s:
            self.assertEqual(s.query(PaperCreatorMention).one().creator_mention_id, original_id)
        changed_att = replace(item.attachments[0], storage_hash="h2")
        self.scan(replace(item, attachments=(changed_att,)), "s3")
        with self.sf() as s:
            self.assertEqual(s.query(PaperCreatorMention).one().creator_mention_id, original_id)

    def test_prompt_hash_is_hash_of_prompt_bytes(self) -> None:
        expected = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
        self.assertEqual(PROMPT_HASH, expected)
        self.assertEqual(len(PROMPT_HASH), 64)

    def test_schema_has_review_table_and_pointer_foreign_keys(self) -> None:
        with self.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertIn("document_extraction_reviews", tables)
            run_fks = sa.inspect(conn).get_foreign_keys("document_extraction_runs")
            doc_fks = sa.inspect(conn).get_foreign_keys("paper_documents")
            self.assertTrue(any(
                fk.get("referred_table") == "document_extraction_attempts"
                and "accepted_attempt_id" in fk.get("constrained_columns", [])
                for fk in run_fks
            ))
            self.assertTrue(any(
                fk.get("referred_table") == "document_extraction_runs"
                and "current_extraction_run_id" in fk.get("constrained_columns", [])
                for fk in doc_fks
            ))
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
