from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from paperazzi.wos.parser import (
    CR_COMPLETE,
    CR_COMPLETE_ZERO,
    CR_MISSING_FROM_EXPORT,
    normalize_doi,
    parse_correspondence_groups,
    parse_records,
)
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
NR 2
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
NR 0
PY 2020
DI 10.1000/test-b
UT WOS:BBB
DA 2026-08-18
ER
"""

MISSING_CR_FOR_A = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Xie, XY
   Ma, HB
AF Xie, Xiaoyu
   Ma, Haibo
TI Test singlet fission article A
SO JOURNAL A
DT Article
DE Charge transfer; Singlet fission
FU New Funder [ABC-1]
NR 2
TC 6
PY 2025
DI 10.1000/test-a
UT WOS:AAA
DA 2026-08-19
ER
"""

COMPLETE_A_ONLY = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Xie, XY
   Ma, HB
AF Xie, Xiaoyu
   Ma, Haibo
TI Test singlet fission article A
SO JOURNAL A
DT Article
AB A later export can add fields that were absent from the first observation.
CR Smith, AB, 2020, JOURNAL B, V1, P2, DOI 10.1000/test-b
   Doe, C, 2019, JOURNAL C, V2, P3
NR 2
PY 2025
DI 10.1000/test-a
UT WOS:AAA
DA 2026-08-20
ER
"""

DUPLICATE_TARGET = """PT J
AU Smith, AC
AF Smith, Another C.
TI Duplicate DOI target
SO JOURNAL B
DT Article
NR 0
PY 2020
DI 10.1000/test-b
UT WOS:BBC
DA 2026-08-18
ER
"""

UT_LESS_ARTIFACT = """PT J
CA Example Contributors
SO Example cited reference
DT CITED-REFERENCE
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

    def test_parse_full_record_and_cr_completeness(self) -> None:
        records = parse_records(SAMPLE)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].ut, "WOS:AAA")
        self.assertEqual(records[0].correspondence_groups[0].member_names, ("Xie, XY", "Ma, HB"))
        self.assertEqual(records[0].references[0].doi, "10.1000/test-b")
        self.assertEqual(records[0].authors[0].full_name, "Xie, Xiaoyu")
        self.assertEqual(records[0].reported_reference_count, 2)
        self.assertEqual(records[0].cr_export_status, CR_COMPLETE)
        self.assertEqual(records[1].cr_export_status, CR_COMPLETE_ZERO)

    def test_missing_cr_is_distinguished_from_zero_references(self) -> None:
        record = parse_records(MISSING_CR_FOR_A)[0]
        self.assertEqual(record.reported_reference_count, 2)
        self.assertFalse(record.cr_tag_present)
        self.assertEqual(record.references, [])
        self.assertEqual(record.cr_export_status, CR_MISSING_FROM_EXPORT)

    def test_legacy_wos_doi_keeps_angle_brackets_and_semicolon(self) -> None:
        self.assertEqual(
            normalize_doi("10.1562/0031-8655(2000)072<0632:PBOSAN>2.0.CO;2."),
            "10.1562/0031-8655(2000)072<0632:pbosan>2.0.co;2",
        )

    def test_ut_less_cited_reference_artifacts_are_skipped(self) -> None:
        records = parse_records(SAMPLE + UT_LESS_ARTIFACT)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.ut for record in records))


class WosStoreTests(unittest.TestCase):
    def test_import_is_idempotent_and_resolves_citation_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            first = store.import_text(SAMPLE, source_filename="first.txt")
            self.assertEqual(first["raw_record_count"], 2)
            self.assertEqual(first["skipped_without_ut"], 0)
            self.assertEqual(first["new_count"], 2)
            self.assertEqual(first["cr_complete_count"], 1)
            self.assertEqual(first["cr_complete_zero_count"], 1)
            self.assertEqual(store.stats()["records"], 2)
            self.assertEqual(store.stats()["corresponding_members"], 3)
            self.assertEqual(store.stats()["resolved_citation_edges"], 1)
            a = store.get_record("WOS:AAA")
            assert a is not None
            self.assertEqual(len(a["correspondence_groups"][0]["members"]), 2)
            self.assertEqual(a["resolved_reference_count"], 1)
            self.assertEqual(a["cr_status"], CR_COMPLETE)

            second = store.import_text(SAMPLE, source_filename="second.txt")
            self.assertEqual(second["new_count"], 0)
            self.assertEqual(second["updated_count"], 2)
            self.assertEqual(second["merged_count"], 2)
            self.assertEqual(store.stats()["records"], 2)
            self.assertEqual(store.stats()["cited_references"], 2)
            self.assertEqual(store.stats()["record_observations"], 4)

    def test_later_export_missing_cr_does_not_erase_existing_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            store.import_text(SAMPLE, source_filename="complete.txt")
            result = store.import_text(MISSING_CR_FOR_A, source_filename="missing-cr.txt")
            self.assertEqual(result["merged_count"], 1)
            self.assertEqual(result["cr_missing_from_export_count"], 1)
            a = store.get_record("WOS:AAA")
            assert a is not None
            self.assertEqual(a["reference_count"], 2)
            self.assertEqual(a["reported_reference_count"], 2)
            self.assertEqual(a["cr_status"], CR_COMPLETE)
            self.assertEqual(a["times_cited_wos"], 6)
            keywords = {(x["keyword_type"], x["keyword"]) for x in a["keywords"]}
            self.assertIn(("AUTHOR", "Pentacene"), keywords)
            self.assertIn(("AUTHOR", "Charge transfer"), keywords)
            self.assertEqual(a["funding"]["funding_agencies_raw"], "New Funder [ABC-1]")
            observations = store.list_observations("WOS:AAA")
            self.assertEqual(observations[0]["cr_export_status"], CR_MISSING_FROM_EXPORT)
            self.assertEqual(observations[0]["parsed_cr_count"], 0)
            self.assertEqual(observations[0]["reported_reference_count"], 2)

    def test_missing_cr_first_can_be_completed_by_reimport_of_same_ut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WosCorpusStore(Path(tmp) / "wos.sqlite3")
            first = store.import_text(MISSING_CR_FOR_A, source_filename="missing-cr.txt")
            self.assertEqual(first["new_count"], 1)
            a = store.get_record("WOS:AAA")
            assert a is not None
            self.assertEqual(a["reference_count"], 0)
            self.assertEqual(a["cr_status"], CR_MISSING_FROM_EXPORT)

            second = store.import_text(COMPLETE_A_ONLY, source_filename="complete.txt")
            self.assertEqual(second["new_count"], 0)
            self.assertEqual(second["merged_count"], 1)
            a = store.get_record("WOS:AAA")
            assert a is not None
            self.assertEqual(a["reference_count"], 2)
            self.assertEqual(a["cr_status"], CR_COMPLETE)
            self.assertEqual(a["abstract"], "A later export can add fields that were absent from the first observation.")
            self.assertEqual(a["funding"]["funding_agencies_raw"], "New Funder [ABC-1]")
            self.assertEqual(a["observation_count"], 2)

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
