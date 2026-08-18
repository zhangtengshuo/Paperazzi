"""Query service over a materialized Graph Analytics run."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Any

from .builder import ANALYSIS_TYPE
from .store import AnalyticsStore


class AnalyticsUnavailableError(RuntimeError):
    pass


class AnalyticsNotFoundError(KeyError):
    pass


def _decode(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


def _pair_neighbor(edge: dict[str, Any], seed: str) -> str:
    return str(edge["target_key"] if edge["source_key"] == seed else edge["source_key"])


class GraphAnalyticsService:
    def __init__(self, analytics_path: str | Path):
        self.store = AnalyticsStore(analytics_path)

    def latest_run(self) -> dict[str, Any]:
        run = self.store.latest_run(ANALYSIS_TYPE)
        if run is None:
            raise AnalyticsUnavailableError(
                "no completed Graph Analytics run; build one with paperazzi-analytics build"
            )
        return run

    def stats(self) -> dict[str, Any]:
        return self.store.stats()

    def paper_node(self, ut: str, *, run_id: str | None = None) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        node = self.store.node(str(run["analysis_run_id"]), ut)
        if node is None:
            raise AnalyticsNotFoundError(f"paper {ut} is not in analysis run {run['analysis_run_id']}")
        return node

    def centrality(
        self,
        *,
        metric: str = "pagerank_local",
        limit: int = 50,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        allowed = {
            "pagerank_local",
            "betweenness_undirected",
            "in_degree_local",
            "out_degree_local_observed",
        }
        if metric not in allowed:
            raise ValueError(f"unsupported centrality metric {metric!r}")
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        return {
            "analysis_run": run,
            "metric": metric,
            "items": self.store.top_nodes(str(run["analysis_run_id"]), metric, limit=limit),
            "interpretation_guardrail": "Centrality is a structural corpus metric, not a paper-quality score.",
        }

    def related(
        self,
        ut: str,
        *,
        limit: int = 30,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        rid = str(run["analysis_run_id"])
        seed = self.store.node(rid, ut)
        if seed is None:
            raise AnalyticsNotFoundError(f"paper {ut} is not in analysis run")
        edges = self.store.edges_for_node(
            rid,
            ut,
            predicates=("CITES_OBSERVED", "BIBLIOGRAPHIC_COUPLING", "CO_CITATION"),
            limit=10000,
        )
        by_candidate: dict[str, dict[str, Any]] = {}
        for edge in edges:
            candidate = _pair_neighbor(edge, ut)
            if candidate == ut:
                continue
            entry = by_candidate.setdefault(
                candidate,
                {
                    "direct_citation": 0.0,
                    "bibliographic_coupling": 0.0,
                    "co_citation": 0.0,
                    "shared_reference_count": 0,
                    "co_citation_count": 0,
                    "warnings": [],
                },
            )
            components = edge.get("components", {})
            if edge["predicate"] == "CITES_OBSERVED":
                entry["direct_citation"] = 1.0
                entry.setdefault("citation_directions", []).append(
                    {
                        "citing": edge["source_key"],
                        "cited": edge["target_key"],
                    }
                )
            elif edge["predicate"] == "BIBLIOGRAPHIC_COUPLING":
                cosine = components.get("cosine")
                entry["bibliographic_coupling"] = float(cosine) if cosine is not None else 0.0
                entry["shared_reference_count"] = int(components.get("shared_reference_count", 0))
                entry["top_shared_references"] = components.get("top_shared_references", [])
                entry["coupling_quality"] = edge["quality_status"]
                if edge["quality_status"] != "COMPLETE_BOTH":
                    entry["warnings"].append(
                        "BIBLIOGRAPHIC_COUPLING_NORMALIZATION_SUPPRESSED_INCOMPLETE_CR"
                    )
            elif edge["predicate"] == "CO_CITATION":
                entry["co_citation"] = float(components.get("normalized_co_citation", edge.get("weight") or 0.0))
                entry["co_citation_count"] = int(components.get("co_citation_count", 0))
                entry["co_citation_quality"] = edge["quality_status"]

        seed_attrs = seed["attributes"]
        seed_authors = set(seed_attrs.get("authors", []))
        seed_concepts = set(seed_attrs.get("concepts", []))
        items: list[dict[str, Any]] = []
        for candidate_ut, components in by_candidate.items():
            candidate = self.store.node(rid, candidate_ut)
            if candidate is None:
                continue
            attrs = candidate["attributes"]
            authors = set(attrs.get("authors", []))
            concepts = set(attrs.get("concepts", []))
            author_union = seed_authors | authors
            concept_union = seed_concepts | concepts
            author_jaccard = len(seed_authors & authors) / len(author_union) if author_union else 0.0
            concept_jaccard = len(seed_concepts & concepts) / len(concept_union) if concept_union else 0.0
            score = (
                0.20 * components["direct_citation"]
                + 0.35 * min(1.0, components["bibliographic_coupling"])
                + 0.25 * min(1.0, components["co_citation"])
                + 0.10 * author_jaccard
                + 0.10 * concept_jaccard
            )
            reasons = {
                "direct_citation": components["direct_citation"],
                "bibliographic_coupling": components["bibliographic_coupling"],
                "co_citation": components["co_citation"],
                "shared_author_jaccard": author_jaccard,
                "shared_concept_jaccard": concept_jaccard,
            }
            items.append(
                {
                    "ut": candidate_ut,
                    "title": attrs.get("title"),
                    "year": attrs.get("year"),
                    "venue": attrs.get("venue"),
                    "score": score,
                    "reasons": reasons,
                    "shared_reference_count": components["shared_reference_count"],
                    "top_shared_references": components.get("top_shared_references", []),
                    "co_citation_count": components["co_citation_count"],
                    "citation_directions": components.get("citation_directions", []),
                    "warnings": sorted(set(components["warnings"])),
                }
            )
        items.sort(
            key=lambda row: (-row["score"], -row["shared_reference_count"], -row["co_citation_count"], row["ut"])
        )
        return {
            "analysis_run": run,
            "seed": seed,
            "score_model": {
                "DIRECT_CITATION": 0.20,
                "BIBLIOGRAPHIC_COUPLING": 0.35,
                "CO_CITATION": 0.25,
                "SHARED_AUTHORS": 0.10,
                "SHARED_CONCEPTS": 0.10,
                "semantic_embeddings": False,
            },
            "items": items[: max(1, min(limit, 500))],
        }

    def neighborhood(
        self,
        ut: str,
        *,
        limit: int = 30,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        rid = str(run["analysis_run_id"])
        seed = self.store.node(rid, ut)
        if seed is None:
            raise AnalyticsNotFoundError(f"paper {ut} is not in analysis run")
        edges = self.store.edges_for_node(rid, ut, limit=10000)
        direct_out = []
        direct_in = []
        coupling = []
        cocit = []
        for edge in edges:
            neighbor_ut = _pair_neighbor(edge, ut)
            neighbor = self.store.node(rid, neighbor_ut)
            summary = {
                "ut": neighbor_ut,
                "title": neighbor["attributes"].get("title") if neighbor else None,
                "year": neighbor["attributes"].get("year") if neighbor else None,
                "weight": edge.get("weight"),
                "quality_status": edge["quality_status"],
                "components": edge.get("components", {}),
            }
            if edge["predicate"] == "CITES_OBSERVED":
                if edge["source_key"] == ut:
                    direct_out.append(summary)
                else:
                    direct_in.append(summary)
            elif edge["predicate"] == "BIBLIOGRAPHIC_COUPLING":
                coupling.append(summary)
            elif edge["predicate"] == "CO_CITATION":
                cocit.append(summary)
        coupling.sort(key=lambda row: (-(row["weight"] or -1.0), -int(row["components"].get("shared_reference_count", 0))))
        cocit.sort(key=lambda row: (-(row["weight"] or 0.0), -int(row["components"].get("co_citation_count", 0))))
        return {
            "analysis_run": run,
            "seed": seed,
            "direct_citations": direct_out[:limit],
            "cited_by": direct_in[:limit],
            "shared_reference_neighbors": coupling[:limit],
            "co_cited_neighbors": cocit[:limit],
            "related": self.related(ut, limit=limit, run_id=rid)["items"],
        }

    def connector(
        self,
        source_ut: str,
        target_ut: str,
        *,
        max_paths: int = 3,
        max_hops: int = 8,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        rid = str(run["analysis_run_id"])
        for ut in (source_ut, target_ut):
            if self.store.node(rid, ut) is None:
                raise AnalyticsNotFoundError(f"paper {ut} is not in analysis run")
        citation_edges = self.store.edges(rid, "CITES_OBSERVED")
        adjacency: dict[str, set[str]] = {}
        directions: set[tuple[str, str]] = set()
        for edge in citation_edges:
            left = str(edge["source_key"])
            right = str(edge["target_key"])
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)
            directions.add((left, right))
        queue: deque[list[str]] = deque([[source_ut]])
        paths: list[list[str]] = []
        shortest_nodes: int | None = None
        while queue and len(paths) < max_paths:
            path = queue.popleft()
            if len(path) - 1 >= max_hops:
                continue
            if shortest_nodes is not None and len(path) >= shortest_nodes:
                continue
            for neighbor in sorted(adjacency.get(path[-1], ())):
                if neighbor in path:
                    continue
                candidate = [*path, neighbor]
                if neighbor == target_ut:
                    shortest_nodes = len(candidate)
                    paths.append(candidate)
                    if len(paths) >= max_paths:
                        break
                else:
                    queue.append(candidate)
        rendered = []
        for path in paths:
            nodes = []
            for ut in path:
                node = self.store.node(rid, ut)
                attrs = node["attributes"] if node else {}
                nodes.append({"ut": ut, "title": attrs.get("title"), "year": attrs.get("year")})
            edges = []
            for left, right in zip(path, path[1:]):
                if (left, right) in directions:
                    direction = "FORWARD_CITATION"
                    citing, cited = left, right
                else:
                    direction = "REVERSE_TRAVERSAL"
                    citing, cited = right, left
                edges.append({"from": left, "to": right, "direction": direction, "citing": citing, "cited": cited})
            rendered.append({"nodes": nodes, "edges": edges, "hop_count": len(path) - 1})
        return {
            "analysis_run": run,
            "source_ut": source_ut,
            "target_ut": target_ut,
            "paths": rendered,
            "traversal": "UNDIRECTED_PROJECTION_OF_OBSERVED_CITATIONS",
            "quality_warning": "Missing/partial CR can hide paths; every returned edge is an observed citation fact.",
        }

    def communities(self, *, run_id: str | None = None) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        return {
            "analysis_run": run,
            "algorithm": run["parameters"].get("community_algorithm"),
            "clusters": self.store.clusters(str(run["analysis_run_id"])),
            "interpretation_guardrail": "Community labels and membership are derived analytical results, not canonical scientific facts.",
        }

    def rpys(self, *, run_id: str | None = None, peaks_only: bool = False) -> dict[str, Any]:
        run = self.store.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            raise AnalyticsUnavailableError("analysis run does not exist")
        rid = str(run["analysis_run_id"])
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT node_key,attributes_json FROM analysis_nodes
                   WHERE analysis_run_id=? AND node_type='RPYS_YEAR' ORDER BY CAST(node_key AS INTEGER)""",
                (rid,),
            ).fetchall()
        series = []
        for row in rows:
            item = _decode(row["attributes_json"])
            if peaks_only and not item.get("is_peak"):
                continue
            series.append(item)
        return {
            "analysis_run": run,
            "series": series,
            "peaks": [row for row in series if row.get("is_peak")],
            "quality_warning": "RPYS is based on observed local WoS references and is completeness-aware only through run provenance.",
        }


__all__ = [
    "AnalyticsNotFoundError",
    "AnalyticsUnavailableError",
    "GraphAnalyticsService",
]
