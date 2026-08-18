"""Read-only scholarly graph snapshot built from the independent WoS corpus.

The snapshot is deliberately source-oriented: it contains observed citation facts and
source metadata only. Similarity, centrality, communities and recommendations are
computed later as derived analytics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

_COMPLETE_CR = {"COMPLETE", "COMPLETE_ZERO"}
_SPACE_RE = re.compile(r"\s+")


def _norm_text(value: str | None) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip()).casefold()


def _raw_reference_key(raw: str) -> str:
    normalized = _norm_text(raw)
    return "raw:" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class PaperNode:
    ut: str
    title: str | None
    doi: str | None
    year: int | None
    venue: str | None
    cr_status: str
    reference_count: int
    reported_reference_count: int | None
    authors: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()

    @property
    def references_complete(self) -> bool:
        return self.cr_status in _COMPLETE_CR


@dataclass(slots=True, frozen=True)
class ReferenceFact:
    source_ut: str
    reference_key: str
    target_ut: str | None
    cited_doi: str | None
    cited_author: str | None
    cited_year: int | None
    cited_source: str | None
    raw_reference: str


@dataclass(slots=True)
class GraphSnapshot:
    nodes: dict[str, PaperNode]
    references: dict[str, tuple[ReferenceFact, ...]]
    citation_edges: set[tuple[str, str]]
    snapshot_hash: str
    input_quality: dict[str, Any]
    source_path: str

    def node(self, ut: str) -> PaperNode:
        try:
            return self.nodes[ut]
        except KeyError as exc:
            raise KeyError(f"WoS record {ut} is not in this graph snapshot") from exc

    def reference_keys(self, ut: str) -> set[str]:
        return {row.reference_key for row in self.references.get(ut, ())}


class WosGraphSnapshotLoader:
    """Build a deterministic read-only graph snapshot from ``wos.sqlite3``."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> GraphSnapshot:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            records = [
                dict(row)
                for row in con.execute(
                    """SELECT ut,title,doi,publication_year,source_title,cr_status,
                              best_cr_count,reported_reference_count
                       FROM wos_records ORDER BY ut"""
                ).fetchall()
            ]
            author_rows = con.execute(
                """SELECT ut,order_index,coalesce(full_name,au_name) AS name
                   FROM wos_authors ORDER BY ut,order_index"""
            ).fetchall()
            keyword_rows = con.execute(
                """SELECT ut,keyword_type,keyword FROM wos_keywords
                   ORDER BY ut,keyword_type,order_index"""
            ).fetchall()
            class_rows = con.execute(
                """SELECT ut,namespace,value FROM wos_classifications
                   ORDER BY ut,namespace,order_index"""
            ).fetchall()
            ref_rows = [
                dict(row)
                for row in con.execute(
                    """SELECT source_ut,order_index,raw_reference,cited_doi,cited_author,
                              cited_year,cited_source,target_ut
                       FROM wos_cited_references ORDER BY source_ut,order_index"""
                ).fetchall()
            ]
        finally:
            con.close()

        authors: dict[str, list[str]] = {}
        for row in author_rows:
            name = _norm_text(row["name"])
            if name:
                authors.setdefault(str(row["ut"]), []).append(name)

        concepts: dict[str, list[str]] = {}
        for row in keyword_rows:
            value = _norm_text(row["keyword"])
            if value:
                concepts.setdefault(str(row["ut"]), []).append(
                    f"{str(row['keyword_type']).casefold()}:{value}"
                )
        for row in class_rows:
            value = _norm_text(row["value"])
            if value:
                concepts.setdefault(str(row["ut"]), []).append(
                    f"{str(row['namespace']).casefold()}:{value}"
                )

        nodes: dict[str, PaperNode] = {}
        complete_count = 0
        incomplete_count = 0
        for row in records:
            ut = str(row["ut"])
            node = PaperNode(
                ut=ut,
                title=row["title"],
                doi=row["doi"],
                year=int(row["publication_year"]) if row["publication_year"] is not None else None,
                venue=row["source_title"],
                cr_status=str(row["cr_status"] or "UNKNOWN"),
                reference_count=int(row["best_cr_count"] or 0),
                reported_reference_count=(
                    int(row["reported_reference_count"])
                    if row["reported_reference_count"] is not None
                    else None
                ),
                authors=tuple(dict.fromkeys(authors.get(ut, ()))),
                concepts=tuple(dict.fromkeys(concepts.get(ut, ()))),
            )
            nodes[ut] = node
            if node.references_complete:
                complete_count += 1
            else:
                incomplete_count += 1

        references: dict[str, list[ReferenceFact]] = {}
        citation_edges: set[tuple[str, str]] = set()
        digest = hashlib.sha256()
        for ut in sorted(nodes):
            node = nodes[ut]
            digest.update(
                json.dumps(
                    {
                        "ut": node.ut,
                        "doi": node.doi,
                        "title": node.title,
                        "year": node.year,
                        "cr_status": node.cr_status,
                        "reference_count": node.reference_count,
                        "reported_reference_count": node.reported_reference_count,
                        "authors": node.authors,
                        "concepts": node.concepts,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )

        for row in ref_rows:
            source_ut = str(row["source_ut"])
            target_ut = str(row["target_ut"]) if row["target_ut"] is not None else None
            cited_doi = str(row["cited_doi"]).casefold() if row["cited_doi"] else None
            raw = str(row["raw_reference"])
            if target_ut:
                reference_key = f"wos:{target_ut}"
            elif cited_doi:
                reference_key = f"doi:{cited_doi}"
            else:
                reference_key = _raw_reference_key(raw)
            fact = ReferenceFact(
                source_ut=source_ut,
                reference_key=reference_key,
                target_ut=target_ut,
                cited_doi=cited_doi,
                cited_author=row["cited_author"],
                cited_year=int(row["cited_year"]) if row["cited_year"] is not None else None,
                cited_source=row["cited_source"],
                raw_reference=raw,
            )
            references.setdefault(source_ut, []).append(fact)
            if target_ut and target_ut in nodes:
                citation_edges.add((source_ut, target_ut))
            digest.update(
                json.dumps(
                    {
                        "source_ut": source_ut,
                        "reference_key": reference_key,
                        "target_ut": target_ut,
                        "cited_year": fact.cited_year,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )

        return GraphSnapshot(
            nodes=nodes,
            references={key: tuple(value) for key, value in references.items()},
            citation_edges=citation_edges,
            snapshot_hash=digest.hexdigest(),
            input_quality={
                "records": len(nodes),
                "observed_references": len(ref_rows),
                "resolved_citation_edges": len(citation_edges),
                "complete_reference_lists": complete_count,
                "incomplete_or_uncertain_reference_lists": incomplete_count,
                "normalized_overlap_policy": "COMPLETE_CR_ONLY",
                "absence_from_incomplete_cr_is_not_negative_evidence": True,
            },
            source_path=str(self.path),
        )


__all__ = [
    "GraphSnapshot",
    "PaperNode",
    "ReferenceFact",
    "WosGraphSnapshotLoader",
]
