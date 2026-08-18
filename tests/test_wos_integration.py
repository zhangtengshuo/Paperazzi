from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import sqlalchemy as sa
from sqlalchemy.orm import Session

from paperazzi.database.models import Paper
from paperazzi.wos.integration import MatchDecision, WosPaperConsumer, apply_match, match_all_papers
from paperazzi.wos.store import WosCorpusStore


WOS_SAMPLE = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Xie, XY
   Ma, HB
AF Xie, Xiaoyu
   Ma, Haibo
TI Exact DOI paper
SO JOURNAL A
DT Article
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, China.
EM xiaoyuxie@sdu.edu.cn; haibo.ma@sdu.edu.cn
DE Singlet fission; Pentacene
ID EXCITON FISSION
FU National Science Foundation [123]
FX Funding acknowledgement text.
CR Smith, AB, 2020, JOURNAL B, V1, P2, DOI 10.1000/reference
TC 5
Z9 7
PY 2025
DI 10.1000/exact-doi
UT WOS:DOI
DA 2026-08-18
ER

PT J
AU Smith, AB
AF Smith, Alice B.
TI Exact title only paper
SO JOURNAL B
DT Article
RP Smith, AB (corresponding author), Univ B, USA.
EM alice@example.edu
PY 2024
DI 10.1000/title-target
UT WOS:TITLE
DA 2026-08-18
ER
"""


def create_bridge_tables(engine: sa.Engine) -> None:
    with engine.begin() as con:
        con.exec_driver_sql(
            """CREATE TABLE paper_wos_links (
            paper_wos_link_id INTEGER PRIMARY KEY,
            paper_id INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
            wos_ut TEXT NOT NULL,
            match_method TEXT NOT NULL,
            match_score REAL,
            status TEXT NOT NULL,
            matched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            UNIQUE(paper_id,wos_ut))"""
        )
        con.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_paper_wos_one_accepted ON paper_wos_links(paper_id) WHERE status='ACCEPTED'"
        )
        con.exec_driver_sql(
            """CREATE TABLE paper_wos_match_state (
            paper_id INTEGER PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )


class WosIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paperazzi_db = root / "paperazzi.sqlite3"
        self.wos_db = root / "wos.sqlite3"
        self.engine = sa.create_engine(f"sqlite:///{self.paperazzi_db}", future=True)
        Paper.__table__.create(self.engine)
        with Session(self.engine) as session:
            session.add_all([
                Paper(paper_id=1, title="Different local title", doi="https://doi.org/10.1000/EXACT-DOI", publication_year=2025, venue="Journal A", active_in_zotero=True),
                Paper(paper_id=2, title="Exact title only paper", doi=None, publication_year=2024, venue="JOURNAL B", active_in_zotero=True),
                Paper(paper_id=3, title="Not exported to local WoS corpus", doi="10.1000/missing", publication_year=2023, venue="Journal C", active_in_zotero=True),
            ])
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_missing_wos_database_is_not_a_failure(self) -> None:
        with Session(self.engine) as session:
            result = match_all_papers(session, self.wos_db, apply=False)
            self.assertFalse(result["wos_database_available"])
            self.assertEqual(result["papers"], 3)
            self.assertEqual(result["not_checked"], 3)
            state = WosPaperConsumer(session, self.wos_db).state(1)
            self.assertEqual(state["status"], "WOS_NOT_CHECKED")
            self.assertFalse(state["available"])

    def test_dry_run_matches_without_requiring_bridge_schema(self) -> None:
        WosCorpusStore(self.wos_db).import_text(WOS_SAMPLE)
        with Session(self.engine) as session:
            result = match_all_papers(session, self.wos_db, apply=False)
            self.assertEqual(result["matched"], 2)
            self.assertEqual(result["not_in_local_corpus"], 1)
            decisions = {row["paper_id"]: row for row in result["decisions"]}
            self.assertEqual(decisions[1]["match_method"], "DOI_EXACT")
            self.assertEqual(decisions[2]["match_method"], "TITLE_EXACT")
            self.assertEqual(WosPaperConsumer(session, self.wos_db).state(3)["status"], "WOS_NOT_CHECKED")

    def test_apply_persists_positive_and_negative_match_state(self) -> None:
        WosCorpusStore(self.wos_db).import_text(WOS_SAMPLE)
        create_bridge_tables(self.engine)
        with Session(self.engine) as session:
            result = match_all_papers(session, self.wos_db, apply=True)
            session.commit()
            self.assertEqual(result["links_written"], 2)
            self.assertEqual(result["states_written"], 3)

        with Session(self.engine) as session:
            matched = WosPaperConsumer(session, self.wos_db).detail(1)
            self.assertEqual(matched["status"], "WOS_MATCHED")
            self.assertEqual(matched["wos_ut"], "WOS:DOI")
            self.assertEqual(
                [a["full_name"] for a in matched["record"]["corresponding_authors"]],
                ["Xie, Xiaoyu", "Ma, Haibo"],
            )
            self.assertEqual(matched["record"]["reference_count"], 1)
            self.assertTrue(matched["record"]["funding"])
            missing = WosPaperConsumer(session, self.wos_db).state(3)
            self.assertEqual(missing["status"], "WOS_NOT_IN_LOCAL_CORPUS")
            self.assertTrue(missing["available"])

    def test_repeated_apply_is_stable(self) -> None:
        WosCorpusStore(self.wos_db).import_text(WOS_SAMPLE)
        create_bridge_tables(self.engine)
        with Session(self.engine) as session:
            match_all_papers(session, self.wos_db, apply=True)
            session.commit()
        with Session(self.engine) as session:
            second = match_all_papers(session, self.wos_db, apply=True)
            session.commit()
            self.assertEqual(second["links_written"], 0)
            self.assertEqual(
                session.execute(sa.text("SELECT count(*) FROM paper_wos_links WHERE status='ACCEPTED'")).scalar(),
                2,
            )
            self.assertEqual(
                session.execute(sa.text("SELECT count(*) FROM paper_wos_match_state")).scalar(),
                3,
            )

    def test_fresh_nonmatch_supersedes_old_accepted_link(self) -> None:
        WosCorpusStore(self.wos_db).import_text(WOS_SAMPLE)
        create_bridge_tables(self.engine)
        with Session(self.engine) as session:
            self.assertTrue(apply_match(session, MatchDecision(1, "WOS_MATCHED", "WOS:DOI", "DOI_EXACT", 1.0, candidate_count=1)))
            session.commit()
            self.assertEqual(WosPaperConsumer(session, self.wos_db).state(1)["status"], "WOS_MATCHED")

        with Session(self.engine) as session:
            self.assertFalse(apply_match(session, MatchDecision(1, "WOS_NOT_IN_LOCAL_CORPUS", reason="fresh check found no candidate")))
            session.commit()
            self.assertEqual(WosPaperConsumer(session, self.wos_db).state(1)["status"], "WOS_NOT_IN_LOCAL_CORPUS")
            self.assertEqual(
                session.execute(sa.text("SELECT count(*) FROM paper_wos_links WHERE paper_id=1 AND status='ACCEPTED'")).scalar(),
                0,
            )
            self.assertEqual(
                session.execute(sa.text("SELECT count(*) FROM paper_wos_links WHERE paper_id=1 AND status='SUPERSEDED'")).scalar(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
