from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from paperazzi.web.wos_api import build_wos_router
from paperazzi.wos.store import WosCorpusStore

from test_graph_analytics import SAMPLE


class GraphAnalyticsWebTests(unittest.TestCase):
    def test_build_and_query_analytics_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wos_db = root / "wos.sqlite3"
            analytics_db = root / "analytics.sqlite3"
            WosCorpusStore(wos_db).import_text(SAMPLE, source_filename="web-graph-sample.txt")

            # The WoS-level analytics routes do not require a Paperazzi session.
            # A session factory is still supplied because the same router also owns
            # Paperazzi↔WoS endpoints that this test does not invoke.
            def unused_session_factory():  # pragma: no cover - assertion guard
                raise AssertionError("Paperazzi session should not be used by WoS-only analytics routes")

            with patch.dict(os.environ, {"PAPERAZZI_ANALYTICS_DB": str(analytics_db)}):
                app = FastAPI()
                app.include_router(build_wos_router(unused_session_factory, wos_db))
                with TestClient(app) as client:
                    unavailable = client.get("/api/analytics/wos/WOS:A/related")
                    self.assertEqual(unavailable.status_code, 409)

                    built = client.post(
                        "/api/analytics/runs",
                        json={
                            "min_shared_references": 1,
                            "min_co_citation": 1,
                            "community_min_weight": 0.05,
                        },
                    )
                    self.assertEqual(built.status_code, 200, built.text)
                    self.assertEqual(built.json()["status"], "COMPLETED")

                    stats = client.get("/api/analytics/stats")
                    self.assertEqual(stats.status_code, 200)
                    self.assertTrue(stats.json()["available"])
                    self.assertIn("BIBLIOGRAPHIC_COUPLING", stats.json()["edges_by_predicate"])

                    related = client.get("/api/analytics/wos/WOS:A/related?limit=20")
                    self.assertEqual(related.status_code, 200, related.text)
                    self.assertIn("WOS:B", {row["ut"] for row in related.json()["items"]})

                    connector = client.get(
                        "/api/analytics/connector",
                        params={"from_ut": "WOS:D", "to_ut": "WOS:C", "max_hops": 4},
                    )
                    self.assertEqual(connector.status_code, 200, connector.text)
                    self.assertTrue(connector.json()["paths"])

                    rpys = client.get("/api/analytics/rpys")
                    self.assertEqual(rpys.status_code, 200)
                    self.assertTrue(rpys.json()["series"])

                    communities = client.get("/api/analytics/communities")
                    self.assertEqual(communities.status_code, 200)
                    self.assertTrue(communities.json()["clusters"])


if __name__ == "__main__":
    unittest.main()
