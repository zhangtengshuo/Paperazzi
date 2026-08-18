from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from paperazzi.analytics.builder import GraphAnalyticsBuilder
from paperazzi.analytics.service import GraphAnalyticsService
from paperazzi.analytics.snapshot import WosGraphSnapshotLoader
from paperazzi.analytics.store import AnalyticsStore
from paperazzi.wos.store import WosCorpusStore


SAMPLE = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Alpha, A
AF Alpha, Alice
TI Alpha paper
SO JOURNAL TEST
DT Article
DE singlet fission; coupling
CR Ref, X, 2010, JOURNAL X, DOI 10.1000/x
   Ref, Y, 2012, JOURNAL Y, DOI 10.1000/y
   Beta, B, 2020, JOURNAL TEST, DOI 10.1000/b
NR 3
PY 2021
DI 10.1000/a
UT WOS:A
ER

PT J
AU Beta, B
AF Beta, Bob
TI Beta paper
SO JOURNAL TEST
DT Article
DE singlet fission; dynamics
CR Ref, X, 2010, JOURNAL X, DOI 10.1000/x
   Ref, Y, 2012, JOURNAL Y, DOI 10.1000/y
   Gamma, C, 2019, JOURNAL TEST, DOI 10.1000/c
NR 3
PY 2020
DI 10.1000/b
UT WOS:B
ER

PT J
AU Gamma, C
AF Gamma, Carol
TI Gamma paper
SO JOURNAL TEST
DT Article
DE dynamics
CR Ref, X, 2010, JOURNAL X, DOI 10.1000/x
NR 1
PY 2019
DI 10.1000/c
UT WOS:C
ER

PT J
AU Delta, D
AF Delta, Dan
TI Delta paper
SO JOURNAL TEST
DT Article
DE review
CR Alpha, A, 2021, JOURNAL TEST, DOI 10.1000/a
   Beta, B, 2020, JOURNAL TEST, DOI 10.1000/b
NR 2
PY 2022
DI 10.1000/d
UT WOS:D
ER

PT J
AU Partial, P
AF Partial, Pat
TI Partial export paper
SO JOURNAL TEST
DT Article
CR Ref, X, 2010, JOURNAL X, DOI 10.1000/x
NR 3
PY 2023
DI 10.1000/p
UT WOS:P
ER

PT J
AU Alpha, A
AF Alpha, Alice
TI Metadata-only neighbor
SO JOURNAL OTHER
DT Article
DE unrelated vocabulary
NR 0
PY 2024
DI 10.1000/e
UT WOS:E
ER

PT J
AU Ref, X
AF Reference, Xavier
TI Historical X
SO JOURNAL X
DT Article
NR 0
PY 2010
DI 10.1000/x
UT WOS:X
ER

PT J
AU Ref, Y
AF Reference, Yvonne
TI Historical Y
SO JOURNAL Y
DT Article
NR 0
PY 2012
DI 10.1000/y
UT WOS:Y
ER
"""


class GraphAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wos_db = root / "wos.sqlite3"
        self.analytics_db = root / "analytics.sqlite3"
        WosCorpusStore(self.wos_db).import_text(SAMPLE, source_filename="graph-sample.txt")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_snapshot_is_deterministic_and_completeness_aware(self) -> None:
        first = WosGraphSnapshotLoader(self.wos_db).load()
        second = WosGraphSnapshotLoader(self.wos_db).load()
        self.assertEqual(first.snapshot_hash, second.snapshot_hash)
        self.assertIn(("WOS:A", "WOS:B"), first.citation_edges)
        self.assertIn(("WOS:D", "WOS:A"), first.citation_edges)
        self.assertTrue(first.nodes["WOS:A"].references_complete)
        self.assertFalse(first.nodes["WOS:P"].references_complete)
        self.assertTrue(first.input_quality["absence_from_incomplete_cr_is_not_negative_evidence"])

    def test_build_materializes_explainable_relations_and_connector(self) -> None:
        result = GraphAnalyticsBuilder(self.wos_db, self.analytics_db).build(
            min_shared_references=1,
            min_co_citation=1,
            community_min_weight=0.05,
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertGreaterEqual(result["citation_edges"], 5)
        self.assertGreaterEqual(result["bibliographic_coupling_edges"], 1)
        self.assertGreaterEqual(result["co_citation_edges"], 1)

        store = AnalyticsStore(self.analytics_db)
        run = store.latest_run()
        assert run is not None
        coupling = store.edges(str(run["analysis_run_id"]), "BIBLIOGRAPHIC_COUPLING")
        ab = next(
            edge
            for edge in coupling
            if {edge["source_key"], edge["target_key"]} == {"WOS:A", "WOS:B"}
        )
        self.assertEqual(ab["quality_status"], "COMPLETE_BOTH")
        self.assertEqual(ab["components"]["shared_reference_count"], 2)
        self.assertIsNotNone(ab["components"]["cosine"])

        ap = next(
            edge
            for edge in coupling
            if {edge["source_key"], edge["target_key"]} == {"WOS:A", "WOS:P"}
        )
        self.assertEqual(ap["quality_status"], "INCOMPLETE_INPUT")
        self.assertIsNone(ap["components"]["cosine"])
        self.assertIsNone(ap["weight"])

        service = GraphAnalyticsService(self.analytics_db)
        connector = service.connector("WOS:D", "WOS:C", max_paths=3, max_hops=4)
        self.assertTrue(connector["paths"])
        first_path = connector["paths"][0]
        self.assertEqual(first_path["nodes"][0]["ut"], "WOS:D")
        self.assertEqual(first_path["nodes"][-1]["ut"], "WOS:C")
        self.assertTrue(
            all(
                edge["direction"] in {"FORWARD_CITATION", "REVERSE_TRAVERSAL"}
                for edge in first_path["edges"]
            )
        )

    def test_related_centrality_community_and_rpys_services(self) -> None:
        GraphAnalyticsBuilder(self.wos_db, self.analytics_db).build(
            min_shared_references=1,
            min_co_citation=1,
            community_min_weight=0.05,
        )
        service = GraphAnalyticsService(self.analytics_db)

        related = service.related("WOS:A", limit=30)
        by_ut = {row["ut"]: row for row in related["items"]}
        self.assertIn("WOS:B", by_ut)
        self.assertGreater(by_ut["WOS:B"]["shared_reference_count"], 0)
        self.assertIn("bibliographic_coupling", by_ut["WOS:B"]["reasons"])
        self.assertIn("WOS:P", by_ut)
        self.assertIn(
            "BIBLIOGRAPHIC_COUPLING_NORMALIZATION_SUPPRESSED_INCOMPLETE_CR",
            by_ut["WOS:P"]["warnings"],
        )

        # E has no citation, coupling or co-citation edge with A. It must still be a
        # candidate because the explicit author metadata is shared.
        self.assertIn("WOS:E", by_ut)
        self.assertEqual(by_ut["WOS:E"]["shared_reference_count"], 0)
        self.assertIn("SHARED_AUTHORS", by_ut["WOS:E"]["evidence_classes"])
        self.assertGreater(by_ut["WOS:E"]["reasons"]["shared_author_jaccard"], 0)

        centrality = service.centrality(metric="pagerank_local", limit=10)
        self.assertEqual(centrality["metric"], "pagerank_local")
        self.assertTrue(centrality["items"])

        communities = service.communities()
        self.assertTrue(communities["clusters"])
        self.assertIn("LABEL_PROPAGATION", communities["algorithm"])

        rpys = service.rpys()
        by_year = {row["year"]: row for row in rpys["series"]}
        self.assertIn(2010, by_year)
        self.assertIn(2012, by_year)
        self.assertEqual(by_year[2010]["local_baseline"], 0.0)


if __name__ == "__main__":
    unittest.main()
