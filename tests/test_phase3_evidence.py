"""Phase 3C gate tests — extraction runs/attempts/evidence/references persistence."""

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
    DocumentExtractionRun,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
    Paper,
    ZoteroItemState,
    ZoteroAttachment,
    ZoteroScanRun,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    ExtractionError,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    decide_extraction_trigger,
    persist_evidence_spans,
    persist_reference_section,
)
from paperazzi.ingest.models import CanonicalAttachment, CanonicalZoteroItem  # noqa: E402
from paperazzi.local_evidence.pdf import ReferenceEntry, ReferenceSection  # noqa: E402


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
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
                library_id=1, item_id=2, item_key=f"ATT_{key}", parent_item_id=1,
                link_mode=0, link_mode_name="imported_file",
                content_type="application/pdf", path=f"storage:ATT_{key}/a.pdf",
                resolved_path=f"/mnt/x/ATT_{key}/a.pdf", local_exists=True,
                resolution="zotero-storage", storage_hash=storage_hash,
            ),
        ),
    )


class Phase3EvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ev.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        self.engine = create_paperazzi_engine(self.db)
        self.session_factory = sa.orm.sessionmaker(bind=self.engine)
        persist_zotero_scan(
            self.session_factory,
            [make_item()],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _document(self):
        with self.session_factory() as s:
            return s.query(PaperDocument).one()

    def test_run_lifecycle_with_attempt_limits(self) -> None:
        doc = self._document()
        doc_id = doc.document_id
        with self.session_factory() as s:
            doc = s.get(PaperDocument, doc_id)
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            a1 = add_extraction_attempt(s, run, attempt_number=1, actor="DETERMINISTIC",
                                        strategy="deterministic-v3", text_source="PDF_NATIVE",
                                        decision="PASS", text_channel="PYMUPDF_SORTED",
                                        channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
                                        section_confidence="HIGH",
                                        segmentation_confidence="HIGH",
                                        entry_text_quality="GOOD")
            self.assertEqual(a1.attempt_number, 1)
            accept_attempt(s, run, a1, "PASS")
            s.commit()
        # 同一 run 尝试 4 -> 拒绝
        with self.session_factory() as s:
            run = s.query(DocumentExtractionRun).one()
            with self.assertRaises(ExtractionError):
                add_extraction_attempt(s, run, attempt_number=4, actor="DETERMINISTIC",
                                       strategy="x", text_source="PDF_NATIVE", decision="PASS")
        # 新 run 可以从 attempt 1 重新开始
        with self.session_factory() as s:
            doc = s.get(PaperDocument, doc_id)
            run2 = create_extraction_run(s, doc.document_id, "FILE_CHANGED", "zotero:h2")
            a1b = add_extraction_attempt(s, run2, attempt_number=1, actor="DETERMINISTIC",
                                         strategy="deterministic-v3", text_source="PDF_NATIVE",
                                         decision="PASS")
            self.assertEqual(a1b.attempt_number, 1)  # UNIQUE(run_id, attempt_number) 允许
            s.commit()

    def test_accept_supersedes_without_deleting(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self._document().document_id)
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            a1 = add_extraction_attempt(s, run, attempt_number=1, actor="DETERMINISTIC",
                                        strategy="deterministic-v3", text_source="PDF_NATIVE",
                                        decision="RETRY", problem_codes=["reference-section-not-found"])
            a2 = add_extraction_attempt(s, run, attempt_number=2, actor="LOCAL_AI_CONTROLLED",
                                        strategy="TAIL_REFERENCE_RECOVERY", text_source="PDF_NATIVE",
                                        decision="PASS")
            persist_evidence_spans(s, doc.document_id, a1,
                                   [{"kind": "affiliation", "page_index": 0, "text": "Candidate A"}])
            persist_evidence_spans(s, doc.document_id, a2,
                                   [{"kind": "affiliation", "page_index": 0, "text": "Accepted A"}])
            sec = ReferenceSection(heading="References", start_page=9, end_page=10,
                                   method="implicit-numbered-punctuated", confidence="HIGH",
                                   raw_text="raw...", entries=(
                                       ReferenceEntry(ordinal=1, raw_text="A. Author, J. Chem. 1 (2000)",
                                                      dois=("10.1/x",), years=("2000",)),
                                   ), text_channel="PYMUPDF_SORTED")
            paper_id = s.query(Paper).one().paper_id
            persist_reference_section(s, paper_id, doc.document_id, a2, sec)
            accept_attempt(s, run, a2, "PASS")
            s.commit()
        with self.session_factory() as s:
            # attempt 1 保留, 其证据 SUPERSEDED
            self.assertEqual(s.query(DocumentExtractionAttempt).count(), 2)
            self.assertEqual(
                s.query(DocumentEvidenceSpan).filter_by(acceptance_status="SUPERSEDED").count(), 1)
            self.assertEqual(
                s.query(DocumentEvidenceSpan).filter_by(acceptance_status="ACCEPTED").count(), 1)
            sec_row = s.query(PaperReferenceSection).one()
            self.assertEqual(sec_row.acceptance_status, "ACCEPTED")
            self.assertEqual(sec_row.text_channel, "PYMUPDF_SORTED")
            ref = s.query(PaperReference).one()
            self.assertEqual(ref.ordinal, 1)
            self.assertEqual(
                {i.identifier_type for i in s.query(PaperReferenceIdentifier).all()},
                {"DOI", "YEAR"})

    def test_raw_section_zero_entries_persists(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self._document().document_id)
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            a1 = add_extraction_attempt(s, run, attempt_number=1, actor="DETERMINISTIC",
                                        strategy="deterministic-v3", text_source="PDF_NATIVE",
                                        decision="ACCEPT_PARTIAL",
                                        section_confidence="MEDIUM",
                                        segmentation_confidence="MEDIUM",
                                        entry_text_quality="PARTIAL")
            sec = ReferenceSection(heading="References", start_page=26, end_page=28,
                                   method="raw-author-year-or-unsegmented", confidence="MEDIUM",
                                   raw_text="AUSLANDER, L...\nBELL, E. T...", entries=(),
                                   text_channel="PYMUPDF_CONTENT_STREAM")
            paper_id = s.query(Paper).one().paper_id
            persist_reference_section(s, paper_id, doc.document_id, a1, sec)
            accept_attempt(s, run, a1, "ACCEPT_PARTIAL")
            s.commit()
        with self.session_factory() as s:
            sec_row = s.query(PaperReferenceSection).one()
            self.assertEqual(sec_row.entry_text_quality, "PARTIAL")
            self.assertEqual(sec_row.section_confidence, "MEDIUM")
            self.assertEqual(s.query(PaperReference).count(), 0)
            self.assertEqual(sec_row.raw_text_hash, __import__("hashlib").sha256(
                "AUSLANDER, L...\nBELL, E. T...".encode()).hexdigest())

    def test_trigger_rules(self) -> None:
        with self.session_factory() as s:
            doc = s.get(PaperDocument, self._document().document_id)
            # 未提取且可用 -> FIRST_AVAILABLE
            self.assertEqual(
                decide_extraction_trigger(doc, doc.document_change_key, "deterministic-v3", "ph"),
                "FIRST_AVAILABLE")
            run = create_extraction_run(s, doc.document_id, "FIRST_AVAILABLE", doc.document_change_key)
            a1 = add_extraction_attempt(s, run, attempt_number=1, actor="DETERMINISTIC",
                                        strategy="deterministic-v3", text_source="PDF_NATIVE",
                                        decision="PASS")
            accept_attempt(s, run, a1, "PASS")
            s.commit()
            doc2 = s.get(PaperDocument, doc.document_id)
            run_hash = run.prompt_hash
            # 无变化 -> None
            self.assertIsNone(decide_extraction_trigger(doc2, doc2.document_change_key, "deterministic-v3", run_hash))
            # 文件变化 -> FILE_CHANGED
            self.assertEqual(decide_extraction_trigger(doc2, "zotero:h9", "deterministic-v3", run_hash),
                             "FILE_CHANGED")
            # 提取器变化 -> EXTRACTOR_CHANGED
            self.assertEqual(decide_extraction_trigger(doc2, doc2.document_change_key, "deterministic-v4", run_hash),
                             "EXTRACTOR_CHANGED")
            # prompt 变化 -> PROMPT_CHANGED
            self.assertEqual(decide_extraction_trigger(doc2, doc2.document_change_key, "deterministic-v3", "newph"),
                             "PROMPT_CHANGED")
            # 不可用文档 -> None
            doc2.availability_status = "PDF_RECORD_ONLY"
            self.assertIsNone(decide_extraction_trigger(doc2, None, "deterministic-v3", "ph"))

    def test_foreign_key_integrity(self) -> None:
        with self.session_factory() as s:
            self.assertEqual(s.execute(sa.text("PRAGMA foreign_key_check")).fetchall(), [])
        # 尝试引用不存在 run -> IntegrityError
        with self.session_factory() as s:
            with self.assertRaises(sa.exc.IntegrityError):
                add_extraction_attempt(s, run := create_extraction_run(
                    s, self._document().document_id, "FIRST_AVAILABLE", None), attempt_number=1,
                    actor="DETERMINISTIC", strategy="x", text_source="PDF_NATIVE", decision="PASS")
                s.flush()
                s.query(DocumentExtractionAttempt).filter_by(extraction_run_id=run.extraction_run_id).update(
                    {"extraction_run_id": 999})
                s.commit()


if __name__ == "__main__":
    unittest.main()
