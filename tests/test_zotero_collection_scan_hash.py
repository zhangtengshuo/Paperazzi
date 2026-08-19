from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sqlalchemy as sa

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine

from test_phase3_scan import alembic
from test_zotero_collection_navigation import ZoteroCollectionPersistenceAndQueryTests as Fixture


class ZoteroCollectionScanHashTests(unittest.TestCase):
    def test_catalog_only_change_has_own_hash_without_touching_bibliographic_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "catalog-hash.sqlite3"
            proc = alembic("upgrade", "head", db_path=db)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            engine = create_paperazzi_engine(db)
            self.addCleanup(engine.dispose)
            Session = sa.orm.sessionmaker(bind=engine)
            items = [Fixture.item_a(), Fixture.item_b()]

            first = persist_zotero_scan_with_collection_catalog(
                Session,
                items,
                Fixture.catalog(),
                {"run_token": "catalog-hash-1", "source_db_path": "/tmp/zotero.sqlite"},
            )
            second = persist_zotero_scan_with_collection_catalog(
                Session,
                items,
                Fixture.catalog(renamed_parent=True),
                {"run_token": "catalog-hash-2", "source_db_path": "/tmp/zotero.sqlite"},
            )
            self.assertEqual(first.status, "COMPLETED")
            self.assertEqual(second.status, "COMPLETED")
            self.assertEqual(second.counts["UNCHANGED"], 2)

            with engine.connect() as con:
                rows = con.execute(
                    sa.text(
                        """SELECT scan_run_id,item_count,collection_count,
                                  bibliographic_corpus_hash,canonical_corpus_hash,
                                  collection_catalog_hash
                           FROM zotero_scan_runs
                           WHERE scan_run_id IN (:a,:b)
                           ORDER BY scan_run_id"""
                    ),
                    {"a": first.scan_run_id, "b": second.scan_run_id},
                ).mappings().all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["collection_count"], 4)
            self.assertEqual(rows[1]["collection_count"], 4)
            self.assertEqual(
                rows[0]["bibliographic_corpus_hash"],
                rows[1]["bibliographic_corpus_hash"],
            )
            # Empty/global catalog navigation state has its own provenance hash.
            self.assertNotEqual(
                rows[0]["collection_catalog_hash"],
                rows[1]["collection_catalog_hash"],
            )


if __name__ == "__main__":
    unittest.main()
