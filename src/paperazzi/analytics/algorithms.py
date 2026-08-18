"""Deterministic graph algorithms used by Paperazzi Graph Analytics v1.

No AI/embedding dependency is used here.  All outputs are derived from the supplied
:class:`GraphSnapshot` and remain explainable through their score components.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from itertools import combinations
import math
import statistics
from typing import Any, Iterable

from .snapshot import GraphSnapshot


def citation_adjacency(snapshot: GraphSnapshot) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    outgoing = {ut: set() for ut in snapshot.nodes}
    incoming = {ut: set() for ut in snapshot.nodes}
    for source, target in snapshot.citation_edges:
        if source in outgoing and target in incoming:
            outgoing[source].add(target)
            incoming[target].add(source)
    return outgoing, incoming


def weak_components(snapshot: GraphSnapshot) -> dict[str, int]:
    outgoing, incoming = citation_adjacency(snapshot)
    seen: set[str] = set()
    component_by_node: dict[str, int] = {}
    component_id = 0
    for start in sorted(snapshot.nodes):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            component_by_node[node] = component_id
            for neighbor in sorted(outgoing[node] | incoming[node]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        component_id += 1
    return component_by_node


def pagerank(
    snapshot: GraphSnapshot,
    *,
    damping: float = 0.85,
    tolerance: float = 1.0e-10,
    max_iter: int = 200,
) -> dict[str, float]:
    """PageRank over observed local WoS citation edges."""
    nodes = sorted(snapshot.nodes)
    if not nodes:
        return {}
    outgoing, _ = citation_adjacency(snapshot)
    n = len(nodes)
    ranks = {node: 1.0 / n for node in nodes}
    teleport = (1.0 - damping) / n
    for _ in range(max_iter):
        dangling = damping * sum(ranks[node] for node in nodes if not outgoing[node]) / n
        next_ranks = {node: teleport + dangling for node in nodes}
        for source in nodes:
            targets = outgoing[source]
            if not targets:
                continue
            share = damping * ranks[source] / len(targets)
            for target in targets:
                next_ranks[target] += share
        delta = sum(abs(next_ranks[node] - ranks[node]) for node in nodes)
        ranks = next_ranks
        if delta <= tolerance:
            break
    total = sum(ranks.values()) or 1.0
    return {node: ranks[node] / total for node in nodes}


def betweenness_undirected(snapshot: GraphSnapshot) -> dict[str, float]:
    """Brandes betweenness on the undirected projection of observed citations.

    This score is deliberately labeled as structural bridge centrality rather than
    paper quality.  Values are normalized to [0, 1] when at least three nodes exist.
    """
    outgoing, incoming = citation_adjacency(snapshot)
    neighbors = {node: outgoing[node] | incoming[node] for node in snapshot.nodes}
    centrality = {node: 0.0 for node in snapshot.nodes}
    nodes = sorted(snapshot.nodes)
    for source in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in nodes}
        sigma = {node: 0.0 for node in nodes}
        sigma[source] = 1.0
        distance = {node: -1 for node in nodes}
        distance[source] = 0
        queue = deque([source])
        while queue:
            vertex = queue.popleft()
            stack.append(vertex)
            for neighbor in sorted(neighbors[vertex]):
                if distance[neighbor] < 0:
                    queue.append(neighbor)
                    distance[neighbor] = distance[vertex] + 1
                if distance[neighbor] == distance[vertex] + 1:
                    sigma[neighbor] += sigma[vertex]
                    predecessors[neighbor].append(vertex)
        dependency = {node: 0.0 for node in nodes}
        while stack:
            vertex = stack.pop()
            if sigma[vertex]:
                factor = (1.0 + dependency[vertex]) / sigma[vertex]
                for pred in predecessors[vertex]:
                    dependency[pred] += sigma[pred] * factor
            if vertex != source:
                centrality[vertex] += dependency[vertex]
    for node in centrality:
        centrality[node] /= 2.0
    n = len(nodes)
    if n > 2:
        scale = 2.0 / ((n - 1) * (n - 2))
        for node in centrality:
            centrality[node] *= scale
    return centrality


def citation_node_metrics(snapshot: GraphSnapshot) -> dict[str, dict[str, Any]]:
    outgoing, incoming = citation_adjacency(snapshot)
    ranks = pagerank(snapshot)
    bridge = betweenness_undirected(snapshot)
    components = weak_components(snapshot)
    component_sizes = Counter(components.values())
    result: dict[str, dict[str, Any]] = {}
    for ut, node in snapshot.nodes.items():
        result[ut] = {
            "in_degree_local": len(incoming[ut]),
            "out_degree_local_observed": len(outgoing[ut]),
            "pagerank_local": ranks.get(ut, 0.0),
            "betweenness_undirected": bridge.get(ut, 0.0),
            "weak_component": components[ut],
            "weak_component_size": component_sizes[components[ut]],
            "cr_status": node.cr_status,
            "reference_count": node.reference_count,
            "out_degree_completeness_warning": not node.references_complete,
        }
    return result


def _reference_index(snapshot: GraphSnapshot) -> tuple[dict[str, set[str]], dict[str, str]]:
    index: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for source, refs in snapshot.references.items():
        for ref in refs:
            index[ref.reference_key].add(source)
            labels.setdefault(ref.reference_key, ref.raw_reference)
    return index, labels


def bibliographic_coupling(
    snapshot: GraphSnapshot,
    *,
    min_shared_references: int = 2,
) -> list[dict[str, Any]]:
    """Compute explainable shared-reference relations.

    Raw shared-reference evidence is retained for all inputs. Jaccard and Salton/cosine
    are emitted only when both source reference lists are confirmed complete.
    """
    ref_index, labels = _reference_index(snapshot)
    shared: dict[tuple[str, str], list[str]] = defaultdict(list)
    fractional: Counter[tuple[str, str]] = Counter()
    for ref_key, citing in ref_index.items():
        papers = sorted(citing)
        if len(papers) < 2:
            continue
        contribution = 1.0 / max(1, len(papers) - 1)
        for left, right in combinations(papers, 2):
            shared[(left, right)].append(ref_key)
            fractional[(left, right)] += contribution

    reference_sets = {ut: snapshot.reference_keys(ut) for ut in snapshot.nodes}
    rows: list[dict[str, Any]] = []
    for (left, right), keys in shared.items():
        count = len(keys)
        if count < min_shared_references:
            continue
        left_complete = snapshot.nodes[left].references_complete
        right_complete = snapshot.nodes[right].references_complete
        complete_both = left_complete and right_complete
        left_count = len(reference_sets[left])
        right_count = len(reference_sets[right])
        union_count = len(reference_sets[left] | reference_sets[right])
        jaccard = count / union_count if complete_both and union_count else None
        cosine = (
            count / math.sqrt(left_count * right_count)
            if complete_both and left_count and right_count
            else None
        )
        rows.append(
            {
                "source_ut": left,
                "target_ut": right,
                "shared_reference_count": count,
                "jaccard": jaccard,
                "cosine": cosine,
                "fractional_shared_weight": float(fractional[(left, right)]),
                "reference_quality": "COMPLETE_BOTH" if complete_both else "INCOMPLETE_INPUT",
                "source_cr_status": snapshot.nodes[left].cr_status,
                "target_cr_status": snapshot.nodes[right].cr_status,
                "shared_reference_keys": sorted(keys),
                "top_shared_references": [labels[key] for key in sorted(keys)[:20]],
            }
        )
    rows.sort(
        key=lambda row: (
            -(row["cosine"] if row["cosine"] is not None else -1.0),
            -row["shared_reference_count"],
            row["source_ut"],
            row["target_ut"],
        )
    )
    return rows


def co_citation(snapshot: GraphSnapshot, *, min_count: int = 2) -> list[dict[str, Any]]:
    """Compute pairs of local WoS papers observed being cited together."""
    pair_sources: dict[tuple[str, str], list[str]] = defaultdict(list)
    local_in_degree = Counter(target for _, target in snapshot.citation_edges)
    for source, refs in snapshot.references.items():
        targets = sorted({ref.target_ut for ref in refs if ref.target_ut in snapshot.nodes})
        for left, right in combinations(targets, 2):
            pair_sources[(left, right)].append(source)

    rows: list[dict[str, Any]] = []
    for (left, right), sources in pair_sources.items():
        count = len(sources)
        if count < min_count:
            continue
        denom = math.sqrt(local_in_degree[left] * local_in_degree[right])
        normalized = count / denom if denom else 0.0
        complete_support = sum(snapshot.nodes[source].references_complete for source in sources)
        incomplete_support = len(sources) - complete_support
        rows.append(
            {
                "source_ut": left,
                "target_ut": right,
                "co_citation_count": count,
                "normalized_co_citation": normalized,
                "citing_papers": sorted(sources),
                "complete_support_count": complete_support,
                "incomplete_support_count": incomplete_support,
                "quality_status": (
                    "ALL_SUPPORTING_CR_COMPLETE" if incomplete_support == 0 else "OBSERVED_WITH_INCOMPLETE_SUPPORT"
                ),
            }
        )
    rows.sort(
        key=lambda row: (-row["normalized_co_citation"], -row["co_citation_count"], row["source_ut"], row["target_ut"])
    )
    return rows


def _undirected_neighbors(snapshot: GraphSnapshot) -> dict[str, set[str]]:
    outgoing, incoming = citation_adjacency(snapshot)
    return {node: outgoing[node] | incoming[node] for node in snapshot.nodes}


def shortest_citation_paths(
    snapshot: GraphSnapshot,
    source_ut: str,
    target_ut: str,
    *,
    max_paths: int = 3,
    max_hops: int = 8,
) -> list[list[str]]:
    """Return several shortest simple paths on the undirected citation projection."""
    snapshot.node(source_ut)
    snapshot.node(target_ut)
    if source_ut == target_ut:
        return [[source_ut]]
    neighbors = _undirected_neighbors(snapshot)
    queue: deque[list[str]] = deque([[source_ut]])
    found: list[list[str]] = []
    shortest_length: int | None = None
    while queue and len(found) < max_paths:
        path = queue.popleft()
        if len(path) - 1 >= max_hops:
            continue
        if shortest_length is not None and len(path) >= shortest_length:
            continue
        for neighbor in sorted(neighbors[path[-1]]):
            if neighbor in path:
                continue
            candidate = [*path, neighbor]
            if neighbor == target_ut:
                shortest_length = len(candidate)
                found.append(candidate)
                if len(found) >= max_paths:
                    break
            else:
                queue.append(candidate)
    return found


def path_edges(snapshot: GraphSnapshot, path: list[str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for left, right in zip(path, path[1:]):
        if (left, right) in snapshot.citation_edges:
            direction = "FORWARD_CITATION"
            citing, cited = left, right
        elif (right, left) in snapshot.citation_edges:
            direction = "REVERSE_TRAVERSAL"
            citing, cited = right, left
        else:  # pragma: no cover - guarded by path construction
            direction = "UNKNOWN"
            citing, cited = left, right
        edges.append({"from": left, "to": right, "direction": direction, "citing": citing, "cited": cited})
    return edges


def weighted_label_communities(
    nodes: Iterable[str],
    weighted_edges: Iterable[tuple[str, str, float]],
    *,
    min_weight: float = 0.10,
    max_iter: int = 100,
) -> dict[str, int]:
    """Dependency-free deterministic weighted label propagation.

    This is a pragmatic v1 community detector, not a claim to reproduce Leiden or
    Louvain.  The algorithm name and threshold are persisted with every run.
    """
    ordered = sorted(set(nodes))
    neighbors: dict[str, dict[str, float]] = {node: {} for node in ordered}
    for left, right, weight in weighted_edges:
        if weight < min_weight or left == right or left not in neighbors or right not in neighbors:
            continue
        neighbors[left][right] = max(weight, neighbors[left].get(right, 0.0))
        neighbors[right][left] = max(weight, neighbors[right].get(left, 0.0))
    labels = {node: node for node in ordered}
    for _ in range(max_iter):
        changed = False
        for node in ordered:
            if not neighbors[node]:
                continue
            score_by_label: Counter[str] = Counter()
            for neighbor, weight in neighbors[node].items():
                score_by_label[labels[neighbor]] += weight
            best_score = max(score_by_label.values())
            best_label = min(label for label, score in score_by_label.items() if score == best_score)
            if best_label != labels[node]:
                labels[node] = best_label
                changed = True
        if not changed:
            break
    canonical = {label: index for index, label in enumerate(sorted(set(labels.values())))}
    return {node: canonical[labels[node]] for node in ordered}


def rpys(snapshot: GraphSnapshot, *, baseline_radius: int = 2, top_peaks: int = 20) -> dict[str, Any]:
    """Reference Publication Year Spectroscopy over all observed cited references."""
    year_counts: Counter[int] = Counter()
    refs_by_year: dict[int, Counter[str]] = defaultdict(Counter)
    labels: dict[str, str] = {}
    for refs in snapshot.references.values():
        for ref in refs:
            if ref.cited_year is None:
                continue
            year_counts[ref.cited_year] += 1
            refs_by_year[ref.cited_year][ref.reference_key] += 1
            labels.setdefault(ref.reference_key, ref.raw_reference)
    if not year_counts:
        return {"series": [], "peaks": [], "input_quality": snapshot.input_quality}
    first_year = min(year_counts)
    last_year = max(year_counts)
    series: list[dict[str, Any]] = []
    for year in range(first_year, last_year + 1):
        neighbors = [
            year_counts[y]
            for y in range(year - baseline_radius, year + baseline_radius + 1)
            if y != year and y in year_counts
        ]
        baseline = statistics.median(neighbors) if neighbors else 0.0
        count = year_counts[year]
        deviation = float(count - baseline)
        series.append({"year": year, "reference_count": count, "local_baseline": baseline, "deviation": deviation})
    peaks = sorted(series, key=lambda row: (-row["deviation"], -row["reference_count"], row["year"]))[:top_peaks]
    enriched_peaks: list[dict[str, Any]] = []
    for row in peaks:
        if row["deviation"] <= 0:
            continue
        year = int(row["year"])
        top_refs = [
            {"reference_key": key, "cited_count": count, "raw_reference": labels.get(key)}
            for key, count in refs_by_year[year].most_common(10)
        ]
        enriched_peaks.append({**row, "top_references": top_refs})
    return {
        "series": series,
        "peaks": enriched_peaks,
        "baseline_radius": baseline_radius,
        "input_quality": snapshot.input_quality,
        "quality_warning": "RPYS uses observed references; missing/partial WoS CR can lower year counts but never invent peaks.",
    }


def pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def related_papers(
    snapshot: GraphSnapshot,
    seed_ut: str,
    coupling_rows: Iterable[dict[str, Any]],
    co_citation_rows: Iterable[dict[str, Any]],
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Explainable composite relatedness for one seed paper.

    The score is intentionally decomposable and contains no embedding/LLM component.
    Incomplete CR suppresses normalized coupling rather than treating missing references
    as negative evidence.
    """
    seed = snapshot.node(seed_ut)
    coupling: dict[tuple[str, str], dict[str, Any]] = {
        pair_key(str(row["source_ut"]), str(row["target_ut"])): row for row in coupling_rows
    }
    cocit: dict[tuple[str, str], dict[str, Any]] = {
        pair_key(str(row["source_ut"]), str(row["target_ut"])): row for row in co_citation_rows
    }
    outgoing, incoming = citation_adjacency(snapshot)
    seed_authors = set(seed.authors)
    seed_concepts = set(seed.concepts)
    candidates: set[str] = outgoing[seed_ut] | incoming[seed_ut]
    for key in coupling:
        if seed_ut in key:
            candidates.update(key)
    for key in cocit:
        if seed_ut in key:
            candidates.update(key)
    candidates.discard(seed_ut)

    rows: list[dict[str, Any]] = []
    for candidate_ut in sorted(candidates):
        node = snapshot.nodes[candidate_ut]
        key = pair_key(seed_ut, candidate_ut)
        coupling_row = coupling.get(key)
        cocit_row = cocit.get(key)
        direct = 1.0 if (seed_ut, candidate_ut) in snapshot.citation_edges or (candidate_ut, seed_ut) in snapshot.citation_edges else 0.0
        coupling_score = (
            float(coupling_row["cosine"])
            if coupling_row is not None and coupling_row.get("cosine") is not None
            else 0.0
        )
        cocit_score = float(cocit_row["normalized_co_citation"]) if cocit_row is not None else 0.0
        author_union = seed_authors | set(node.authors)
        concept_union = seed_concepts | set(node.concepts)
        author_score = len(seed_authors & set(node.authors)) / len(author_union) if author_union else 0.0
        concept_score = len(seed_concepts & set(node.concepts)) / len(concept_union) if concept_union else 0.0
        score = (
            0.20 * direct
            + 0.35 * min(1.0, coupling_score)
            + 0.25 * min(1.0, cocit_score)
            + 0.10 * author_score
            + 0.10 * concept_score
        )
        reasons: dict[str, Any] = {
            "direct_citation": direct,
            "bibliographic_coupling": coupling_score,
            "co_citation": cocit_score,
            "shared_author_jaccard": author_score,
            "shared_concept_jaccard": concept_score,
        }
        warnings: list[str] = []
        if coupling_row is not None and coupling_row.get("reference_quality") != "COMPLETE_BOTH":
            warnings.append("BIBLIOGRAPHIC_COUPLING_NORMALIZATION_SUPPRESSED_INCOMPLETE_CR")
        rows.append(
            {
                "ut": candidate_ut,
                "title": node.title,
                "year": node.year,
                "venue": node.venue,
                "score": score,
                "reasons": reasons,
                "shared_reference_count": coupling_row.get("shared_reference_count", 0) if coupling_row else 0,
                "co_citation_count": cocit_row.get("co_citation_count", 0) if cocit_row else 0,
                "warnings": warnings,
            }
        )
    rows.sort(key=lambda row: (-row["score"], -row["shared_reference_count"], row["ut"]))
    return rows[: max(1, min(limit, 500))]


__all__ = [
    "betweenness_undirected",
    "bibliographic_coupling",
    "citation_adjacency",
    "citation_node_metrics",
    "co_citation",
    "pagerank",
    "path_edges",
    "related_papers",
    "rpys",
    "shortest_citation_paths",
    "weak_components",
    "weighted_label_communities",
]
