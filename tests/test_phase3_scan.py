"""Phase 3B gate tests — split hashes, diff engine, scan persistence."""

from __future__ import annotations

import sqlite3
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
from paperazzi.database.persistence import (  # noqa: E402
    CHANGE_MODIFIED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_RESTORED,
    CHANGE_UNCHANGED,
    DIM_ATTACHMENT,
    DIM_BIBLIOGRAPHIC,
    DIM_ORGANIZATION,
    ItemChange,
    persist_zotero_scan,
)
from paperazzi.database.models import (  # noqa: E402
    Paper,
    ZoteroAttachment,
    ZoteroItemState,
    ZoteroItemVersion,
)
from paperazzi.ingest.models import CanonicalAttachment, CanonicalZoteroItem  # noqa: E402


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )


from paperazzi.ingest.models import CanonicalTag, CanonicalCollection  # noqa: E402


def make_item(
    key: str = "AAAAAA",
    title: str = "Paper A",
    doi: str = "10.1000/a",
    tag: str | None = "t1",
    attachment_key: str | None = None,
    attachment_storage_hash: str | None = None,
) -> CanonicalZoteroItem:
    if attachment_key is None:
        attachment_key = f"ATT_{key}"
    attachments = ()
    if attachment_key:
        attachments = (
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key=attachment_key,
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path=f"storage:{attachment_key}/a.pdf",
                resolved_path=f"/mnt/x/{attachment_key}/a.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash=attachment_storage_hash,
            ),
        )
    tags = (CanonicalTag(tag_id=1, name=tag, tag_type=0),) if tag else ()
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
        fields={"title": title, "DOI": doi},
        creators=(),
        collections=(),
        tags=tags,
        attachments=attachments,
    )


class Phase3ScanGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "scan.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        self.engine = create_paperazzi_engine(self.db)
        self.session_factory = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def scan(self, items: list[CanonicalZoteroItem], token: str):
        return persist_zotero_scan(
            self.session_factory,
            items,
            {"run_token": token, "source_db_path": "/tmp/fake.sqlite"},
        )

    def _counts(self, session, table: type) -> int:
        return session.query(table).count()

    def test_scan_lifecycle(self) -> None:
        a = make_item()
        # scan1 NEW
        r1 = self.scan([a], "s1")
        self.assertEqual(r1.counts, {CHANGE_NEW: 1, CHANGE_MODIFIED: 0, CHANGE_UNCHANGED: 0,
                                     CHANGE_REMOVED: 0, CHANGE_RESTORED: 0})
        self.assertEqual(r1.status, "COMPLETED")
        # scan2 identical UNCHANGED
        r2 = self.scan([a], "s2")
        self.assertEqual(r2.counts[CHANGE_UNCHANGED], 1)
        self.assertEqual(r2.counts[CHANGE_NEW], 0)
        with self.session_factory() as s:
            self.assertEqual(self._counts(s, Paper), 1)
            self.assertEqual(self._counts(s, ZoteroItemVersion), 1)  # 仅 NEW 版本
        # scan3 title change -> MODIFIED[BIBLIOGRAPHIC]
        r3 = self.scan([make_item(title="Paper A v2")], "s3")
        self.assertEqual(r3.counts[CHANGE_MODIFIED], 1)
        self.assertIn(DIM_BIBLIOGRAPHIC, r3.changes[0].changed_dimensions)
        # scan4 tag change -> MODIFIED[ORGANIZATION] only
        r4 = self.scan([make_item(title="Paper A v2", tag="t2")], "s4")
        self.assertEqual(r4.counts[CHANGE_MODIFIED], 1)
        dims = r4.changes[0].changed_dimensions
        self.assertIn(DIM_ORGANIZATION, dims)
        self.assertNotIn(DIM_BIBLIOGRAPHIC, dims)
        # scan5 attachment change -> MODIFIED[ATTACHMENT]
        r5 = self.scan([make_item(title="Paper A v2", tag="t2",
                                  attachment_key="ATTACH2",
                                  attachment_storage_hash="h2")], "s5")
        self.assertEqual(r5.counts[CHANGE_MODIFIED], 1)
        self.assertIn(DIM_ATTACHMENT, r5.changes[0].changed_dimensions)
        # scan6 absent -> REMOVED
        r6 = self.scan([], "s6")
        self.assertEqual(r6.counts[CHANGE_REMOVED], 1)
        with self.session_factory() as s:
            state = s.query(ZoteroItemState).one()
            self.assertFalse(state.present_in_last_scan)
            paper = s.get(Paper, state.paper_id)
            self.assertFalse(paper.active_in_zotero)
        # scan7 reappears -> RESTORED (same paper_id)
        r7 = self.scan([make_item(title="Paper A v2", tag="t2", attachment_key="ATTACH2")], "s7")
        self.assertEqual(r7.counts[CHANGE_RESTORED], 1)
        with self.session_factory() as s:
            self.assertEqual(self._counts(s, Paper), 1)  # 同一 paper 行
            state = s.query(ZoteroItemState).one()
            self.assertTrue(state.present_in_last_scan)
            self.assertTrue(s.get(Paper, state.paper_id).active_in_zotero)

    def test_no_duplicate_papers_and_versions_across_scans(self) -> None:
        a = make_item()
        for i in range(3):
            r = self.scan([a], f"s{i}")
            self.assertEqual(r.counts[CHANGE_NEW], 1 if i == 0 else 0)
            self.assertEqual(r.counts[CHANGE_UNCHANGED], 1 if i else 0)
        with self.session_factory() as s:
            self.assertEqual(self._counts(s, Paper), 1)
            self.assertEqual(self._counts(s, ZoteroItemVersion), 1)
            self.assertEqual(self._counts(s, ZoteroItemState), 1)

    def test_no_doi_title_deduplication(self) -> None:
        # 两个 Zotero 条目, 相同 DOI, 必须两个 paper 行
        r = self.scan([make_item(key="AAAAAA", title="T1", doi="10.1/same"),
                       make_item(key="BBBBBB", title="T2", doi="10.1/same")], "s1")
        self.assertEqual(r.counts[CHANGE_NEW], 2)
        with self.session_factory() as s:
            self.assertEqual(self._counts(s, Paper), 2)

    def test_duplicate_identity_rejected(self) -> None:
        r = self.scan([make_item(key="AAAAAA"), make_item(key="AAAAAA")], "s1")
        self.assertEqual(r.status, "FAILED")

    def test_rollback_preserves_previous_state(self) -> None:
        a = make_item(title="V1")
        self.scan([a], "s1")
        # 注入失败: 第二个 item 重复身份 -> ScanPersistenceError -> run FAILED, 投影回滚
        r = self.scan([make_item(title="V1"), make_item(title="V2")], "s2")  # 重复身份 AAAAAA
        self.assertEqual(r.status, "FAILED")
        with self.session_factory() as s:
            # 全部回滚: V2 的 paper 不应存在
            self.assertEqual(self._counts(s, Paper), 1)
            self.assertEqual(self._counts(s, ZoteroItemState), 1)
            run = s.query(ZoteroScanRun).filter_by(run_token="s2").one()
            self.assertEqual(run.status, "FAILED")

    def test_split_hash_dimension_isolation(self) -> None:
        a = make_item()
        org_only = replace(a, tags=(__import__("paperazzi.ingest.models", fromlist=["CanonicalTag"]).CanonicalTag(tag_id=9, name="zz", tag_type=0),))
        self.assertEqual(a.bibliographic_hash(), org_only.bibliographic_hash())
        self.assertNotEqual(a.organization_hash(), org_only.organization_hash())
        self.assertEqual(a.attachment_hash(), org_only.attachment_hash())
        # local_exists 变化不影响任何语义哈希
        att = a.attachments[0]
        local_only = replace(a, attachments=(replace(att, local_exists=False),))
        self.assertEqual(a.bibliographic_hash(), local_only.bibliographic_hash())
        self.assertEqual(a.organization_hash(), local_only.organization_hash())
        self.assertEqual(a.attachment_hash(), local_only.attachment_hash())
        # bookkeeping 不影响
        book = replace(a, zotero_version=99, date_modified="2030-01-01")
        self.assertEqual(a.canonical_hash(), book.canonical_hash())


from paperazzi.database.models import ZoteroScanRun  # noqa: E402

if __name__ == "__main__":
    unittest.main()
