"""Build a complete versioned Graph Analytics v1 run."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .algorithms import (
    bibliographic_coupling,
    citation_node_metrics,
    co_citation,
    rpys,
    weighted_label_communities,
)
from .revision import wos_revision
from .snapshot import GraphSnapshot, WosGraphSnapshotLoader
from .store import AnalyticsStore

ANALYSIS_TYPE = "GRAPH_ANALYTICS_V1"
CODE_VERSION = "ga-v1.0"


class GraphAnalyticsBuilder:
    """Materialize deterministic scholarly graph analytics into ``analytics.sqlite3``."""

    def __init__(self, wos_path: str | Path, analytics_path: str | Path):
        self.wos_path = Path(wos_path)
        self.store = AnalyticsStore(analytics_path)

    def build(
        self,
        *,
        min_shared_references: int = 2,
        min_co_citation: int = 2,
        community_min_weight: float = 0.10,
    ) -> dict[str, Any]:
        snapshot = WosGraphSnapshotLoader(self.wos_path).load()
        source_revision = wos_revision(self.wos_path)
        parameters = {
            "min_shared_references": min_shared_references,
            "min_co_citation": min_co_citation,
            "community_algorithm": "DETERMINISTIC_WEIGHTED_LABEL_PROPAGATION_V1",
            "community_min_weight": community_min_weight,
            "pagerank_damping": 0.85,
            "coupling_normalization_policy": "COMPLETE_CR_ONLY",
        }
        run_id = self.store.begin_run(
            analysis_type=ANALYSIS_TYPE,
            input_snapshot_hash=snapshot.snapshot_hash,
            corpus_definition={
                "source": "LOCAL_WOS_CORPUS",
                "wos_database": str(self.wos_path),
                "record_count": len(snapshot.nodes),
                "source_revision": source_revision,
            },
            algorithm="PAPERAZZI_GRAPH_ANALYTICS_V1",
            parameters=parameters,
            code_version=CODE_VERSION,
            input_quality=snapshot.input_quality,
        )
        try:
            metrics = citation_node_metrics(snapshot)
            coupling = bibliographic_coupling(
                snapshot, min_shared_references=min_shared_references
            )
            cocit = co_citation(snapshot, min_count=min_co_citation)
            rpys_result = rpys(snapshot)
            communities = self._communities(
                snapshot,
                coupling,
                cocit,
                min_weight=community_min_weight,
            )

            self.store.write_nodes(run_id, self._paper_nodes(snapshot, metrics))
            self.store.write_nodes(run_id, self._rpys_nodes(rpys_result))
            self.store.write_edges(run_id, self._citation_edges(snapshot))
            self.store.write_edges(run_id, self._coupling_edges(coupling))
            self.store.write_edges(run_id, self._co_citation_edges(cocit))
            clusters, members = self._cluster_rows(snapshot, communities)
            self.store.write_clusters(run_id, clusters, members)
            self.store.complete_run(run_id)
        except BaseException as exc:
            self.store.fail_run(run_id, exc)
            raise

        return {
            "analysis_run_id": run_id,
            "input_snapshot_hash": snapshot.snapshot_hash,
            "source_revision": source_revision,
            "input_quality": snapshot.input_quality,
            "parameters": parameters,
            "paper_nodes": len(snapshot.nodes),
            "citation_edges": len(snapshot.citation_edges),
            "bibliographic_coupling_edges": len(coupling),
            "co_citation_edges": len(cocit),
            "communities": len(set(communities.values())),
            "rpys_years": len(rpys_result["series"]),
            "rpys_peaks": len(rpys_result["peaks"]),
            "status": "COMPLETED",
        }

    @staticmethod
    def _paper_nodes(
        snapshot: GraphSnapshot,
        metrics: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ut in sorted(snapshot.nodes):
            node = snapshot.nodes[ut]
            rows.append(
                {
                    "node_type": "PAPER",
                    "node_key": ut,
                    "attributes": {
                        "title": node.title,
                        "doi": node.doi,
                        "year": node.year,
                        "venue": node.venue,
                        "cr_status": node.cr_status,
                        "reference_count": node.reference_count,
                        "reported_reference_count": node.reported_reference_count,
                        "authors": list(node.authors),
                        "concepts": list(node.concepts),
                        "metrics": metrics[ut],
                    },
                }
            )
        return rows

    @staticmethod
    def _citation_edges(snapshot: GraphSnapshot) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source, target in sorted(snapshot.citation_edges):
            rows.append(
                {
                    "source_key": source,
                    "predicate": "CITES_OBSERVED",
                    "target_key": target,
                    "weight": 1.0,
                    "components": {
                        "source_cr_status": snapshot.nodes[source].cr_status,
                        "fact_class": "FACT",
                        "absence_is_not_inferred": True,
                    },
                    "quality_status": "FACT_OBSERVED",
                }
            )
        return rows

    @staticmethod
    def _coupling_edges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "source_key": row["source_ut"],
                    "predicate": "BIBLIOGRAPHIC_COUPLING",
                    "target_key": row["target_ut"],
                    "weight": row["cosine"],
                    "components": {
                        "shared_reference_count": row["shared_reference_count"],
                        "jaccard": row["jaccard"],
                        "cosine": row["cosine"],
                        "fractional_shared_weight": row["fractional_shared_weight"],
                        "shared_reference_keys": row["shared_reference_keys"],
                        "top_shared_references": row["top_shared_references"],
                        "source_cr_status": row["source_cr_status"],
                        "target_cr_status": row["target_cr_status"],
                    },
                    "quality_status": row["reference_quality"],
                }
            )
        return result

    @staticmethod
    def _co_citation_edges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source_key": row["source_ut"],
                "predicate": "CO_CITATION",
                "target_key": row["target_ut"],
                "weight": row["normalized_co_citation"],
                "components": {
                    "co_citation_count": row["co_citation_count"],
                    "normalized_co_citation": row["normalized_co_citation"],
                    "citing_papers": row["citing_papers"],
                    "complete_support_count": row["complete_support_count"],
                    "incomplete_support_count": row["incomplete_support_count"],
                },
                "quality_status": row["quality_status"],
            }
            for row in rows
        ]

    @staticmethod
    def _communities(
        snapshot: GraphSnapshot,
        coupling: list[dict[str, Any]],
        cocit: list[dict[str, Any]],
        *,
        min_weight: float,
    ) -> dict[str, int]:
        weights: dict[tuple[str, str], float] = defaultdict(float)
        for row in coupling:
            if row["cosine"] is None:
                continue
            key = (str(row["source_ut"]), str(row["target_ut"]))
            weights[key] += 0.60 * float(row["cosine"])
        for row in cocit:
            key = (str(row["source_ut"]), str(row["target_ut"]))
            weights[key] += 0.40 * min(1.0, float(row["normalized_co_citation"]))
        return weighted_label_communities(
            snapshot.nodes,
            [(left, right, weight) for (left, right), weight in weights.items()],
            min_weight=min_weight,
        )

    @staticmethod
    def _cluster_rows(
        snapshot: GraphSnapshot,
        membership: dict[str, int],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        grouped: dict[int, list[str]] = defaultdict(list)
        for ut, cluster_id in membership.items():
            grouped[cluster_id].append(ut)
        clusters: list[dict[str, Any]] = []
        members: list[dict[str, Any]] = []
        for cluster_id, uts in sorted(grouped.items()):
            years = [snapshot.nodes[ut].year for ut in uts if snapshot.nodes[ut].year is not None]
            concept_counts: Counter[str] = Counter()
            venue_counts: Counter[str] = Counter()
            for ut in uts:
                node = snapshot.nodes[ut]
                for concept in node.concepts:
                    concept_counts[concept] += 1
                if node.venue:
                    venue_counts[node.venue] += 1
            top_concepts = [key for key, _ in concept_counts.most_common(5)]
            label = "; ".join(item.split(":", 1)[-1] for item in top_concepts[:3]) or f"Community {cluster_id}"
            clusters.append(
                {
                    "cluster_id": str(cluster_id),
                    "label": label,
                    "metrics": {
                        "size": len(uts),
                        "year_min": min(years) if years else None,
                        "year_max": max(years) if years else None,
                        "top_concepts": top_concepts,
                        "top_venues": venue_counts.most_common(5),
                        "label_is_derived": True,
                        "algorithm": "DETERMINISTIC_WEIGHTED_LABEL_PROPAGATION_V1",
                    },
                }
            )
            members.extend(
                {
                    "cluster_id": str(cluster_id),
                    "node_key": ut,
                    "membership_weight": 1.0,
                }
                for ut in sorted(uts)
            )
        return clusters, members

    @staticmethod
    def _rpys_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
        peak_by_year = {int(row["year"]): row for row in result.get("peaks", [])}
        rows: list[dict[str, Any]] = []
        for point in result.get("series", []):
            year = int(point["year"])
            rows.append(
                {
                    "node_type": "RPYS_YEAR",
                    "node_key": str(year),
                    "attributes": {
                        **point,
                        "is_peak": year in peak_by_year,
                        "top_references": peak_by_year.get(year, {}).get("top_references", []),
                        "quality_warning": result.get("quality_warning"),
                    },
                }
            )
        return rows


__all__ = ["ANALYSIS_TYPE", "CODE_VERSION", "GraphAnalyticsBuilder"]
