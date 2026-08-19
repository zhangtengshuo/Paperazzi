from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sqlalchemy as sa
from fastapi.testclient import TestClient

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.web.api import create_app

from test_phase3_scan import alembic
from test_zotero_collection_navigation import ZoteroCollectionPersistenceAndQueryTests as Fixture


class ZoteroCollectionWebTests(unittest.TestCase):
    def test_tree_collection_unfiled_organization_and_ui_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "paperazzi.sqlite3"
            proc = alembic("upgrade", "head", db_path=db)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            engine = create_paperazzi_engine(db)
            Session = sa.orm.sessionmaker(bind=engine)
            result = persist_zotero_scan_with_collection_catalog(
                Session,
                [Fixture.item_a(), Fixture.item_b()],
                Fixture.catalog(),
                {"run_token": "web-collections", "source_db_path": "/tmp/zotero.sqlite"},
            )
            self.assertEqual(result.status, "COMPLETED")
            engine.dispose()

            with patch.dict(
                os.environ,
                {
                    "PAPERAZZI_WOS_DB": str(root / "missing-wos.sqlite3"),
                    "PAPERAZZI_ANALYTICS_DB": str(root / "analytics.sqlite3"),
                },
            ):
                app = create_app(db)
                with TestClient(app) as client:
                    tree = client.get("/api/collections/tree?library_id=1&include_empty=true")
                    self.assertEqual(tree.status_code, 200, tree.text)
                    payload = tree.json()
                    self.assertEqual(payload["summary"]["collection_nodes"], 4)
                    self.assertEqual(payload["unfiled"]["active_paper_count"], 1)
                    roots = {row["collection_key"]: row for row in payload["roots"]}
                    self.assertIn("EMPTY001", roots)
                    self.assertEqual(roots["EMPTY001"]["active_paper_count"], 0)

                    child = client.get("/api/collections/CHILD001/papers?library_id=1")
                    self.assertEqual(child.status_code, 200, child.text)
                    self.assertEqual(child.json()["total"], 1)
                    paper_id = child.json()["items"][0]["paper_id"]
                    self.assertEqual(child.json()["items"][0]["collection_order_index"], 4)

                    subtree = client.get(
                        "/api/collections/ROOT0001/papers?library_id=1&include_descendants=true"
                    )
                    self.assertEqual(subtree.status_code, 200)
                    self.assertEqual(subtree.json()["total"], 1)

                    unfiled = client.get("/api/collections/unfiled/papers?library_id=1")
                    self.assertEqual(unfiled.status_code, 200)
                    self.assertEqual(unfiled.json()["total"], 1)

                    org = client.get(f"/api/papers/{paper_id}/organization")
                    self.assertEqual(org.status_code, 200, org.text)
                    self.assertEqual(len(org.json()["collections"]), 2)
                    paths = [[x["name"] for x in path] for path in org.json()["collection_paths"]]
                    self.assertIn(["Programming", "Julia", "Makie"], paths)

                    script = client.get("/api/collections/ui.js")
                    self.assertEqual(script.status_code, 200)
                    self.assertIn("library-layout", script.text)
                    self.assertIn("selectCollection", script.text)

                    home = client.get("/")
                    self.assertEqual(home.status_code, 200)
                    self.assertIn("/api/collections/ui.js", home.text)


if __name__ == "__main__":
    unittest.main()
