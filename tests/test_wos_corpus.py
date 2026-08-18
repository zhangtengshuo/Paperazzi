from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from paperazzi.wos.parser import parse_correspondence_groups, parse_records
from paperazzi.wos.store import WosCorpusStore


SAMPLE = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Xie, XY
   Ma, HB
AF Xie, Xiaoyu
   Ma, Haibo
TI Test singlet fission article A
SO JOURNAL A
DT Article
C1 [Xie, Xiaoyu; Ma, Haibo] Shandong Univ, Qingdao, China
C3 Shandong University
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, Qingdao, China.
EM xiaoyuxie@sdu.edu.cn; haibo.ma@sdu.edu.cn
DE Singlet fission; Pentacene
ID EXCITON FISSION; DYNAMICS
CR Smith, AB, 2020, JOURNAL B, V1, P2, DOI 10.1000/test-b
   Doe, C, 2019, JOURNAL C, V2, P3
TC 4
Z9 5
PY 2025
DI 10.1000/test-a
UT WOS:AAA
DA 2026-08-18
ER

PT J
AU Smith, AB
AF Smith, Alice B.
TI Test article B
SO JOURNAL B
DT Article
RP Smith, AB (corresponding author), Univ B, USA.
EM alice@example.edu
PY 2020
DI 10.1000/test-b
UT WOS:BBB
DA 2026-08-18
ER
"""

DUPLICATE_TARGET = """PT J
AU Smith, AC
AF Smith, Another C.
TI Duplicate DOI target
SO JOURNAL B
DT Article
PY 2020
DI 10.1000/test-b
UT WOS:BBC
DA 2026-08-18
ER
"""


class WosParserTests(unittest.TestCase):
    def test_group_level_corresponding_author_semantics(self) -> None:
        groups = parse_correspondence_groups(
            "Sun, CL; Wang, Q; Zhang, HL (corresponding author), Lanzhou Univ, China.; "
            "Zhang, CF (corresponding author), Nanjing Univ, China."
        )
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].member_names, ("Sun, CL", "Wang, Q", "Zhang, HL"))
        self.assertEqual(groups[1].member_names, ("Zhang, CF",))

    def test_parse_full_record(self) -> None:
        records = parse_records(SAMPLE)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].ut, "WOS:AAA")
        self.assertEqual(records[0].correspondence_groups[0].member_names, ("Xie, XY", "Ma, HB"))
        self.assertEqual(records[0].references[0].doi, "10.1000/test-b")
        self.assertEqual(records[0].authors[0].full_name, "Xie, Xiaoyu")


class WosStoreTests(unittest.TestCase):
    def test_import_is_idempotent_and_resolves_citation_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            first = store.import_text(SAMPLE, source_filename="first.txt")
            self.assertEqual(first["new_count"], 2)
            self.assertEqual(store.stats()["records"], 2)
            self.assertEqual(store.stats()["corresponding_members"], 3)
            self.assertEqual(store.stats()["resolved_citation_edges"], 1)
            a = store.get_record("WOS:AAA")
            assert a is not None
            self.assertEqual(len(a["correspondence_groups"][0]["members"]), 2)
            self.assertEqual(a["resolved_reference_count"], 1)

            second = store.import_text(SAMPLE, source_filename="second.txt")
            self.assertEqual(second["new_count"], 0)
            self.assertEqual(second["updated_count"], 2)
            self.assertEqual(store.stats()["records"], 2)
            self.assertEqual(store.stats()["cited_references"], 2)

    def test_duplicate_target_doi_is_not_forced_into_a_citation_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            store.import_text(SAMPLE)
            self.assertEqual(store.stats()["resolved_citation_edges"], 1)
            store.import_text(DUPLICATE_TARGET)
            self.assertEqual(store.stats()["resolved_citation_edges"], 0)
            ref = store.list_references("WOS:AAA")[0]
            self.assertEqual(ref["cited_doi"], "10.1000/test-b")
            self.assertIsNone(ref["target_ut"])
            self.assertEqual(store.citation_frontier()[0]["cited_doi"], "10.1000/test-b")

    def test_citation_frontier_retains_unresolved_external_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            store.import_text(SAMPLE)
            frontier = store.citation_frontier()
            self.assertEqual(store.stats()["cited_references"], 2)
            self.assertEqual(frontier, [])


if __name__ == "__main__":
    unittest.main()
