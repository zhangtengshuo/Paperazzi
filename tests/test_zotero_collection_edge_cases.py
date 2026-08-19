from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import sqlalchemy as sa

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.ingest.models import CanonicalCollection, CanonicalZoteroCollection
from paperazzi.web.collections import ZoteroCollectionQueryService

from test_phase3_scan import alembic, make_item


class ZoteroCollectionEdgeCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "edge.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.engine = create_paperazzi_engine(self.db)
        self.session_factory = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def catalog(*, makie_parent_key: str = "JULIA001", makie_parent_id: int = 12):
        return [
            CanonicalZoteroCollection(1, 10, "FOUND001", "0A_Fundation", None, None),
            CanonicalZoteroCollection(1, 11, "YQ202400", "0A_2024青基", 10, "FOUND001", "0A_Fundation"),
            CanonicalZoteroCollection(1, 20, "PROG0001", "Programming", None, None),
            CanonicalZoteroCollection(1, 12, "JULIA001", "Julia", 20, "PROG0001", "Programming"),
            CanonicalZoteroCollection(
                1,
                13,
                "MAKIE001",
                "Makie",
                makie_parent_id,
                makie_parent_key,
                "Julia" if makie_parent_key == "JULIA001" else "0A_2024青基",
            ),
            # A source catalog node can legitimately have zero active bibliographic
            # memberships because its Zotero contents are deleted/non-bibliographic.
            CanonicalZoteroCollection(1, 30, "NONBIB01", "Only notes and attachments", None, None),
        ]

    @staticmethod
    def item(*, makie_parent_key: str = "JULIA001", makie_parent_id: int = 12):
        return replace(
            make_item(
                key="CN000001",
                title="单线态裂变中的非绝热动力学",
                doi="10.1000/nonascii",
                attachment_key="CNATT001",
            ),
            collections=(
                CanonicalCollection(11, "YQ202400", "0A_2024青基", 10, "FOUND001", 2),
                CanonicalCollection(
                    13,
                    "MAKIE001",
                    "Makie",
                    makie_parent_id,
                    makie_parent_key,
                    7,
                ),
            ),
        )

    def scan(self, token: str, catalog, *, item=None):
        return persist_zotero_scan_with_collection_catalog(
            self.session_factory,
            [item or self.item()],
            catalog,
            {"run_token": token, "source_db_path": "/tmp/zotero.sqlite"},
        )

    def test_non_ascii_nested_paths_and_zero_active_source_node(self) -> None:
        result = self.scan("edge-1", self.catalog())
        self.assertEqual(result.status, "COMPLETED")
        with self.session_factory() as session:
            service = ZoteroCollectionQueryService(session)
            tree = service.tree(1)
            roots = {node["collection_key"]: node for node in tree["roots"]}
            foundation = roots["FOUND001"]
            child = next(node for node in foundation["children"] if node["collection_key"] == "YQ202400")
            self.assertEqual([p["name"] for p in child["path"]], ["0A_Fundation", "0A_2024青基"])
            nonbib = roots["NONBIB01"]
            self.assertEqual(nonbib["active_paper_count"], 0)
            self.assertFalse(nonbib["has_active_papers"])

            papers = service.papers(1, "YQ202400")
            self.assertEqual(papers["total"], 1)
            self.assertEqual(papers["items"][0]["title"], "单线态裂变中的非绝热动力学")
            self.assertEqual(papers["items"][0]["collection_order_index"], 2)

    def test_reparent_updates_organization_but_not_bibliographic_state(self) -> None:
        first = self.scan("edge-reparent-1", self.catalog())
        self.assertEqual(first.status, "COMPLETED")
        moved = self.catalog(makie_parent_key="YQ202400", makie_parent_id=11)
        moved_item = self.item(makie_parent_key="YQ202400", makie_parent_id=11)
        second = self.scan("edge-reparent-2", moved, item=moved_item)
        self.assertEqual(second.status, "COMPLETED")
        # The per-item organization projection legitimately changes because the
        # membership row carries the collection's current parent key. Bibliographic
        # content must remain stable.
        self.assertEqual(second.counts["MODIFIED"], 1)
        self.assertGreaterEqual(second.counts["COLLECTION_UPDATED"], 1)

        with self.session_factory() as session:
            makie = ZoteroCollectionQueryService(session).collection(1, "MAKIE001")
            self.assertEqual(makie["parent_collection_key"], "YQ202400")
            self.assertEqual(
                [p["name"] for p in makie["path"]],
                ["0A_Fundation", "0A_2024青基", "Makie"],
            )

        with self.engine.connect() as con:
            hashes = con.execute(
                sa.text(
                    """SELECT scan_run_id,bibliographic_corpus_hash,collection_catalog_hash
                       FROM zotero_scan_runs WHERE scan_run_id IN (:a,:b) ORDER BY scan_run_id"""
                ),
                {"a": first.scan_run_id, "b": second.scan_run_id},
            ).mappings().all()
        self.assertEqual(hashes[0]["bibliographic_corpus_hash"], hashes[1]["bibliographic_corpus_hash"])
        self.assertNotEqual(hashes[0]["collection_catalog_hash"], hashes[1]["collection_catalog_hash"])


if __name__ == "__main__":
    unittest.main()
