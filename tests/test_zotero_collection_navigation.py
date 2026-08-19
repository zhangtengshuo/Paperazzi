from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
import unittest

import sqlalchemy as sa

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.ingest.models import CanonicalCollection, CanonicalZoteroCollection
from paperazzi.web.collections import ZoteroCollectionQueryService
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader

from test_phase3_scan import alembic, make_item
from test_zotero_reader import ZoteroReaderTests


class ZoteroCollectionReaderTests(unittest.TestCase):
    def test_reader_returns_complete_catalog_and_allows_same_key_in_other_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn, data_dir = ZoteroReaderTests().make_fixture(Path(tmp))
            conn.execute(
                "INSERT INTO collections VALUES (12, 'Empty Root', NULL, 1, 'EMPTY001')"
            )
            conn.execute(
                "INSERT INTO collections VALUES (13, 'Other Library Parent', NULL, 2, 'COLLPAR1')"
            )
            conn.commit()
            try:
                catalog = ZoteroSQLiteReader(conn, data_dir).read_collection_catalog()
            finally:
                conn.close()

        self.assertEqual(len(catalog), 4)
        empty = next(c for c in catalog if c.collection_key == "EMPTY001")
        self.assertEqual(empty.library_id, 1)
        self.assertEqual(empty.name, "Empty Root")
        same_key = [c for c in catalog if c.collection_key == "COLLPAR1"]
        self.assertEqual({c.library_id for c in same_key}, {1, 2})
        child = next(c for c in catalog if c.collection_key == "COLLCHD1")
        self.assertEqual(child.parent_collection_key, "COLLPAR1")
        self.assertEqual(child.parent_name, "Parent")


class ZoteroCollectionPersistenceAndQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "collections.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.engine = create_paperazzi_engine(self.db)
        self.session_factory = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def catalog(*, renamed_parent: bool = False, include_empty: bool = True):
        rows = [
            CanonicalZoteroCollection(1, 10, "ROOT0001", "Programming" if not renamed_parent else "Programming & Tools", None, None),
            CanonicalZoteroCollection(1, 11, "CHILD001", "Julia", 10, "ROOT0001", "Programming" if not renamed_parent else "Programming & Tools"),
            CanonicalZoteroCollection(1, 12, "DEEP0001", "Makie", 11, "CHILD001", "Julia"),
        ]
        if include_empty:
            rows.append(CanonicalZoteroCollection(1, 13, "EMPTY001", "0A_Fundation", None, None))
        return rows

    @staticmethod
    def item_a():
        return replace(
            make_item(key="PAPER001", title="Paper in multiple collections", attachment_key="ATT001"),
            collections=(
                CanonicalCollection(11, "CHILD001", "Julia", 10, "ROOT0001", 4),
                CanonicalCollection(12, "DEEP0001", "Makie", 11, "CHILD001", 1),
            ),
        )

    @staticmethod
    def item_b():
        return replace(
            make_item(key="PAPER002", title="Unfiled paper", doi="10.1000/b", attachment_key="ATT002"),
            collections=(),
        )

    def scan(self, token: str, catalog, items=None):
        if items is None:
            items = [self.item_a(), self.item_b()]
        return persist_zotero_scan_with_collection_catalog(
            self.session_factory,
            items,
            catalog,
            {"run_token": token, "source_db_path": "/tmp/read-only-zotero.sqlite"},
        )

    def test_catalog_lifecycle_tree_empty_nodes_multimembership_unfiled_and_paths(self) -> None:
        first = self.scan("collections-1", self.catalog())
        self.assertEqual(first.status, "COMPLETED")
        self.assertEqual(first.counts["COLLECTION_NEW"], 4)

        with self.session_factory() as session:
            service = ZoteroCollectionQueryService(session)
            tree = service.tree(1)
            self.assertEqual(tree["summary"]["collection_nodes"], 4)
            self.assertEqual(tree["summary"]["active_papers"], 2)
            self.assertEqual(tree["summary"]["papers_with_collection"], 1)
            self.assertEqual(tree["summary"]["unfiled_papers"], 1)
            self.assertEqual(tree["summary"]["active_collection_memberships"], 2)

            roots = {node["collection_key"]: node for node in tree["roots"]}
            self.assertIn("EMPTY001", roots)
            self.assertEqual(roots["EMPTY001"]["active_paper_count"], 0)
            programming = roots["ROOT0001"]
            julia = programming["children"][0]
            makie = julia["children"][0]
            self.assertEqual([p["name"] for p in makie["path"]], ["Programming", "Julia", "Makie"])
            self.assertEqual(programming["active_paper_count"], 0)
            self.assertEqual(programming["subtree_active_paper_count"], 1)
            self.assertEqual(julia["active_paper_count"], 1)
            self.assertEqual(makie["active_paper_count"], 1)

            julia_papers = service.papers(1, "CHILD001")
            self.assertEqual(julia_papers["total"], 1)
            self.assertEqual(julia_papers["items"][0]["collection_order_index"], 4)
            subtree = service.papers(1, "ROOT0001", include_descendants=True)
            self.assertEqual(subtree["total"], 1)  # no duplicate despite two memberships
            self.assertEqual(service.unfiled_papers(1)["total"], 1)

            paper_id = julia_papers["items"][0]["paper_id"]
            org = service.paper_organization(paper_id)
            self.assertEqual(len(org["collections"]), 2)
            self.assertIn(["Programming", "Julia", "Makie"], [[x["name"] for x in p] for p in org["collection_paths"]])

        # A catalog-only rename updates catalog history but leaves item bibliography unchanged.
        second = self.scan("collections-2", self.catalog(renamed_parent=True))
        self.assertEqual(second.status, "COMPLETED")
        self.assertEqual(second.counts["COLLECTION_UPDATED"], 2)  # parent + cached parent_name on child
        self.assertEqual(second.counts["UNCHANGED"], 2)

        # Removing an empty catalog node does not hard-delete it; it leaves current tree.
        third = self.scan("collections-3", self.catalog(renamed_parent=True, include_empty=False))
        self.assertEqual(third.counts["COLLECTION_REMOVED"], 1)
        with self.session_factory() as session:
            row = session.execute(
                sa.text("SELECT present_in_last_scan FROM zotero_collections WHERE library_id=1 AND collection_key='EMPTY001'")
            ).scalar_one()
            self.assertFalse(bool(row))
            tree = ZoteroCollectionQueryService(session).tree(1)
            self.assertNotIn("EMPTY001", {n["collection_key"] for n in tree["roots"]})

        # Restoration reuses the stable (library,key) row.
        fourth = self.scan("collections-4", self.catalog(renamed_parent=True))
        self.assertEqual(fourth.counts["COLLECTION_RESTORED"], 1)
        with self.session_factory() as session:
            count = session.execute(
                sa.text("SELECT COUNT(*) FROM zotero_collections WHERE library_id=1 AND collection_key='EMPTY001'")
            ).scalar_one()
            self.assertEqual(int(count), 1)

    def test_missing_parent_goes_to_orphan_bucket(self) -> None:
        catalog = [
            CanonicalZoteroCollection(
                library_id=1,
                collection_id=20,
                collection_key="ORPHAN01",
                name="孤立目录",
                parent_collection_id=999,
                parent_collection_key=None,
                parent_name=None,
            )
        ]
        result = self.scan("orphan-1", catalog, items=[self.item_b()])
        self.assertEqual(result.status, "COMPLETED")
        with self.session_factory() as session:
            tree = ZoteroCollectionQueryService(session).tree(1)
            self.assertEqual(len(tree["orphaned"]), 1)
            self.assertEqual(tree["orphaned"][0]["collection_key"], "ORPHAN01")
            self.assertEqual(tree["orphaned"][0]["missing_parent_collection_id"], 999)


if __name__ == "__main__":
    unittest.main()
