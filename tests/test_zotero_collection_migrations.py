from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sqlalchemy as sa

from paperazzi.database.engine import create_paperazzi_engine
from test_phase3_scan import alembic


class ZoteroCollectionMigrationTests(unittest.TestCase):
    def test_head_has_catalog_and_scan_summary_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "migration.sqlite3"
            proc = alembic("upgrade", "head", db_path=db)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            engine = create_paperazzi_engine(db)
            self.addCleanup(engine.dispose)
            inspector = sa.inspect(engine)
            self.assertIn("zotero_collections", inspector.get_table_names())
            scan_columns = {row["name"] for row in inspector.get_columns("zotero_scan_runs")}
            self.assertTrue({"collection_count", "collection_catalog_hash"}.issubset(scan_columns))
            unique_constraints = inspector.get_unique_constraints("zotero_collections")
            unique_sets = {tuple(row.get("column_names") or []) for row in unique_constraints}
            self.assertIn(("library_id", "collection_key"), unique_sets)


if __name__ == "__main__":
    unittest.main()
