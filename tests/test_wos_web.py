from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import Paper  # noqa: E402
from paperazzi.web.api import create_app  # noqa: E402
from paperazzi.wos.integration import match_all_papers  # noqa: E402
from paperazzi.wos.store import WosCorpusStore  # noqa: E402


WOS_SAMPLE = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Xie, XY
   Ma, HB
AF Xie, Xiaoyu
   Ma, Haibo
TI Web integration article
SO JOURNAL A
DT Article
C1 [Xie, Xiaoyu; Ma, Haibo] Shandong Univ, Qingdao, China
C3 Shandong University
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, Qingdao, China.
EM xiaoyuxie@sdu.edu.cn; haibo.ma@sdu.edu.cn
RI Ma, Haibo/H-1155-2011
OI Xie, Xiaoyu/0000-0001-2345-6789; Ma, Haibo/0000-0002-2345-6789
DE Singlet fission; Pentacene
ID EXCITON FISSION; CHARGE TRANSFER
FU National Science Foundation [CHE-12345]; Example Foundation
FX Funding acknowledgement text.
CR Smith, AB, 2020, JOURNAL B, V1, P2, DOI 10.1000/reference
NR 1
TC 5
Z9 7
PY 2025
DI 10.1000/web-integration
UT WOS:WEB
DA 2026-08-18
ER
"""


def alembic_upgrade(db_path: Path) -> None:
    env = dict(os.environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise AssertionError(proc.stderr[-1600:])


class WosWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "paperazzi.sqlite3"
        self.wos_db = root / "wos.sqlite3"
        alembic_upgrade(self.db)
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        with self.sf() as session:
            session.add_all([
                Paper(
                    paper_id=1,
                    title="Web integration article",
                    doi="10.1000/web-integration",
                    publication_year=2025,
                    venue="JOURNAL A",
                    active_in_zotero=True,
                ),
                Paper(
                    paper_id=2,
                    title="Residual Zotero article",
                    doi="10.1000/not-exported",
                    publication_year=2023,
                    venue="JOURNAL X",
                    active_in_zotero=True,
                ),
            ])
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_no_wos_database_is_non_blocking(self) -> None:
        missing = Path(self.tmp.name) / "not-created.sqlite3"
        with patch.dict(os.environ, {"PAPERAZZI_WOS_DB": str(missing)}):
            app = create_app(self.db)
            with TestClient(app) as client:
                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertFalse(health.json()["wos_available"])
                stats = client.get("/api/wos/stats")
                self.assertEqual(stats.status_code, 200)
                self.assertFalse(stats.json()["available"])
                paper = client.get("/api/papers/1/wos")
                self.assertEqual(paper.status_code, 200)
                self.assertEqual(paper.json()["status"], "WOS_NOT_CHECKED")
                self.assertEqual(client.get("/api/papers/1").status_code, 200)
                self.assertIn("WoS Corpus", client.get("/").text)
            app.state.engine.dispose()

    def test_matched_wos_record_is_exposed_with_rich_metadata(self) -> None:
        store = WosCorpusStore(self.wos_db)
        store.import_text(WOS_SAMPLE, source_filename="wos-test.txt", label="test import")
        with self.sf() as session:
            result = match_all_papers(session, self.wos_db, apply=True)
            session.commit()
            self.assertEqual(result["matched"], 1)
            self.assertEqual(result["not_in_local_corpus"], 1)

        with patch.dict(os.environ, {"PAPERAZZI_WOS_DB": str(self.wos_db)}):
            app = create_app(self.db)
            with TestClient(app) as client:
                detail = client.get("/api/papers/1/wos")
                self.assertEqual(detail.status_code, 200)
                body = detail.json()
                self.assertEqual(body["status"], "WOS_MATCHED")
                self.assertEqual(body["record"]["ut"], "WOS:WEB")
                self.assertEqual(body["record"]["cr_status"], "COMPLETE")
                self.assertEqual(body["record"]["reported_reference_count"], 1)
                self.assertEqual(
                    [row["full_name"] for row in body["record"]["corresponding_authors"]],
                    ["Xie, Xiaoyu", "Ma, Haibo"],
                )
                self.assertEqual(body["record"]["reference_count"], 1)
                self.assertTrue(body["record"]["funding"]["items"])
                author_ids = {
                    item["namespace"]
                    for author in body["record"]["authors"]
                    for item in author["identifiers"]
                }
                self.assertIn("ORCID", author_ids)

                observations = client.get("/api/wos/records/WOS:WEB/observations")
                self.assertEqual(observations.status_code, 200)
                obs_body = observations.json()
                self.assertEqual(obs_body["canonical_cr_status"], "COMPLETE")
                self.assertEqual(obs_body["canonical_reference_count"], 1)
                self.assertEqual(obs_body["reported_reference_count"], 1)
                self.assertEqual(obs_body["items"][0]["cr_export_status"], "COMPLETE")

                refs = client.get("/api/wos/records/WOS:WEB/references")
                self.assertEqual(refs.status_code, 200)
                self.assertEqual(refs.json()["cr_status"], "COMPLETE")
                self.assertEqual(refs.json()["reported_reference_count"], 1)

                missing = client.get("/api/papers/2/wos").json()
                self.assertEqual(missing["status"], "WOS_NOT_IN_LOCAL_CORPUS")

                stats = client.get("/api/wos/stats").json()
                self.assertEqual(stats["records"], 1)
                self.assertEqual(stats["records_cr_complete"], 1)
                coverage = client.get("/api/wos/coverage").json()
                self.assertEqual(coverage["active_zotero_papers"], 2)
                self.assertEqual(coverage["matched"], 1)
                self.assertEqual(coverage["not_in_local_corpus"], 1)
                self.assertEqual(coverage["not_checked"], 0)

                standalone = client.get("/api/wos/records/WOS:WEB")
                self.assertEqual(standalone.status_code, 200)
                self.assertEqual(standalone.json()["funding"]["items"][0]["funder"], "National Science Foundation")
            app.state.engine.dispose()


if __name__ == "__main__":
    unittest.main()
