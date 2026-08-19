from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sqlalchemy as sa

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.ingest.models import CanonicalZoteroCollection
from paperazzi.web.collections import ZoteroCollectionQueryService

from test_phase3_scan import alembic
from test_zotero_collection_navigation import ZoteroCollectionPersistenceAndQueryTests as Fixture


class ZoteroCollectionCycleTests(unittest.TestCase):
    def test_closed_parent_cycle_is_visible_in_diagnostic_bucket_without_recursive_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cycle.sqlite3"
            proc = alembic("upgrade", "head", db_path=db)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            engine = create_paperazzi_engine(db)
            self.addCleanup(engine.dispose)
            Session = sa.orm.sessionmaker(bind=engine)
            catalog = [
                CanonicalZoteroCollection(1, 30, "CYCLE001", "Cycle A", 31, "CYCLE002", "Cycle B"),
                CanonicalZoteroCollection(1, 31, "CYCLE002", "Cycle B", 30, "CYCLE001", "Cycle A"),
            ]
            result = persist_zotero_scan_with_collection_catalog(
                Session,
                [Fixture.item_b()],
                catalog,
                {"run_token": "cycle", "source_db_path": "/tmp/zotero.sqlite"},
            )
            self.assertEqual(result.status, "COMPLETED")
            with Session() as session:
                tree = ZoteroCollectionQueryService(session).tree(1)
                self.assertEqual(tree["summary"]["collection_nodes"], 2)
                self.assertEqual(tree["summary"]["root_nodes"], 0)
                self.assertGreaterEqual(tree["summary"]["orphaned_nodes"], 1)

                visible: set[str] = set()
                stack = [*tree["roots"], *tree["orphaned"]]
                while stack:
                    node = stack.pop()
                    key = str(node["collection_key"])
                    if key in visible:
                        continue
                    visible.add(key)
                    stack.extend(node.get("children", []))
                self.assertEqual(visible, {"CYCLE001", "CYCLE002"})

                # json serialization is the practical guard against an object cycle.
                import json
                encoded = json.dumps(tree, ensure_ascii=False)
                self.assertIn("PARENT_CYCLE", encoded)


if __name__ == "__main__":
    unittest.main()
