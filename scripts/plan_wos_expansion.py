"""Plan broad/manual WoS corpus expansion from unmatched Zotero/Paperazzi papers.

This is intentionally not a browser/API automation tool. It summarizes the current
unmatched personal-library frontier so a human can make a few broad WoS searches and
export large Full Record + Cited References batches.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import sqlalchemy as sa

from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.wos.store import WosCorpusStore

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+-]{2,}")
_STOP = {
    "the", "and", "for", "with", "from", "into", "via", "using", "study", "studies",
    "new", "toward", "towards", "based", "effect", "effects", "role", "analysis",
    "molecular", "state", "states", "system", "systems", "approach", "investigation",
    "properties", "mechanism", "mechanisms", "dynamics", "energy", "electronic",
}


def top(counter: Counter[str], limit: int) -> list[dict[str, object]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def title_terms(titles: list[str]) -> tuple[Counter[str], Counter[str]]:
    unigram: Counter[str] = Counter()
    bigram: Counter[str] = Counter()
    for title in titles:
        words = [word.casefold() for word in _WORD_RE.findall(title)]
        kept = [word for word in words if word not in _STOP]
        unigram.update(set(kept))
        bigram.update(set(" ".join(pair) for pair in zip(kept, kept[1:])))
    return unigram, bigram


def _frequent_values(counter: Counter[str], *, max_items: int, min_count: int) -> list[str]:
    return [value for value, count in counter.most_common(max_items) if count >= min_count]


def suggest_manual_searches(
    bigrams: Counter[str],
    terms: Counter[str],
    authors: Counter[str],
    venues: Counter[str],
    tags: Counter[str],
    collections: Counter[str],
) -> list[dict[str, object]]:
    """Generate human-facing broad-search ideas without accessing or automating WoS."""
    suggestions: list[dict[str, object]] = []
    phrases = _frequent_values(bigrams, max_items=12, min_count=2)
    words = [x for x in _frequent_values(terms, max_items=16, min_count=3) if x not in {w for p in phrases for w in p.split()}]
    topic_terms = phrases[:8] + words[:6]
    if topic_terms:
        suggestions.append({
            "kind": "TOPIC_CLUSTER",
            "values": topic_terms,
            "rationale": "High-frequency title concepts among Zotero papers still unmatched or not checked against the local WoS corpus. Combine related terms into one or a few deliberately broad WoS topic searches.",
        })
    author_values = _frequent_values(authors, max_items=12, min_count=2)
    if author_values:
        suggestions.append({
            "kind": "AUTHOR_CLUSTER",
            "values": author_values,
            "rationale": "Repeated authors among residual Zotero papers. Broad author searches can recover multiple missing papers at once and may also enrich the surrounding research group corpus.",
        })
    venue_values = _frequent_values(venues, max_items=10, min_count=3)
    if venue_values:
        suggestions.append({
            "kind": "VENUE_CLUSTER",
            "values": venue_values,
            "rationale": "Journals containing several residual Zotero papers. Combine venue with one broad subject concept instead of searching individual titles.",
        })
    semantic_values = _frequent_values(tags, max_items=10, min_count=2) + _frequent_values(collections, max_items=10, min_count=2)
    semantic_values = list(dict.fromkeys(semantic_values))[:16]
    if semantic_values:
        suggestions.append({
            "kind": "ZOTERO_SEMANTIC_CLUSTER",
            "values": semantic_values,
            "rationale": "User-maintained Zotero tags/collections can identify themes that title vocabulary alone misses. Use these as human search prompts, not as WoS matching truth.",
        })
    return suggestions


def build_report(paperazzi_db: Path, wos_db: Path, *, limit: int = 30) -> dict[str, object]:
    engine = create_paperazzi_engine(paperazzi_db)
    try:
        with engine.connect() as con:
            inspector = sa.inspect(con)
            has_state = inspector.has_table("paper_wos_match_state")
            if has_state:
                rows = con.execute(sa.text(
                    "SELECT p.paper_id,p.title,p.venue,p.publication_year,s.status "
                    "FROM papers p LEFT JOIN paper_wos_match_state s ON s.paper_id=p.paper_id "
                    "WHERE p.active_in_zotero=1 AND (s.status IS NULL OR s.status!='WOS_MATCHED') "
                    "ORDER BY p.paper_id"
                )).mappings().all()
            else:
                rows = con.execute(sa.text(
                    "SELECT p.paper_id,p.title,p.venue,p.publication_year,NULL AS status "
                    "FROM papers p WHERE p.active_in_zotero=1 ORDER BY p.paper_id"
                )).mappings().all()
            ids = [int(row["paper_id"]) for row in rows]
            id_set = set(ids)
            titles = [str(row["title"]) for row in rows if row["title"]]
            unigram, bigram = title_terms(titles)
            venues = Counter(str(row["venue"]) for row in rows if row["venue"])
            years = Counter(str(row["publication_year"]) for row in rows if row["publication_year"] is not None)
            statuses = Counter(str(row["status"] or "WOS_NOT_CHECKED") for row in rows)

            authors: Counter[str] = Counter()
            if ids and inspector.has_table("paper_creator_mentions"):
                for row in con.execute(sa.text(
                    "SELECT paper_id,coalesce(display_name,trim(coalesce(first_name,'')||' '||coalesce(last_name,''))) AS name "
                    "FROM paper_creator_mentions WHERE creator_type='author'"
                )).mappings():
                    if int(row["paper_id"]) in id_set and row["name"]:
                        authors[str(row["name"]).strip()] += 1

            tags: Counter[str] = Counter()
            if ids and inspector.has_table("zotero_item_tags") and inspector.has_table("zotero_item_state"):
                for row in con.execute(sa.text(
                    "SELECT z.paper_id,t.name FROM zotero_item_tags t JOIN zotero_item_state z "
                    "ON z.zotero_item_state_id=t.zotero_item_state_id WHERE z.present_in_last_scan=1"
                )).mappings():
                    if int(row["paper_id"]) in id_set and row["name"]:
                        tags[str(row["name"])] += 1

            collections: Counter[str] = Counter()
            if ids and inspector.has_table("zotero_item_collections") and inspector.has_table("zotero_item_state"):
                for row in con.execute(sa.text(
                    "SELECT z.paper_id,c.name FROM zotero_item_collections c JOIN zotero_item_state z "
                    "ON z.zotero_item_state_id=c.zotero_item_state_id "
                    "WHERE z.present_in_last_scan=1 AND c.name IS NOT NULL"
                )).mappings():
                    if int(row["paper_id"]) in id_set and row["name"]:
                        collections[str(row["name"])] += 1
    finally:
        engine.dispose()

    frontier: list[dict[str, object]] = []
    wos_stats: dict[str, object] = {"available": False}
    if wos_db.is_file():
        store = WosCorpusStore(wos_db)
        wos_stats = {"available": True, **store.stats()}
        frontier = store.citation_frontier(limit=limit)

    return {
        "paperazzi_db": str(paperazzi_db),
        "wos_db": str(wos_db),
        "unmatched_or_unchecked_papers": len(rows),
        "match_states": dict(statuses),
        "clusters": {
            "title_bigrams": top(bigram, limit),
            "title_terms": top(unigram, limit),
            "venues": top(venues, limit),
            "authors": top(authors, limit),
            "zotero_tags": top(tags, limit),
            "zotero_collections": top(collections, limit),
            "years": top(years, limit),
        },
        "suggested_manual_searches": suggest_manual_searches(
            bigram, unigram, authors, venues, tags, collections
        ),
        "wos_corpus": wos_stats,
        "citation_frontier": frontier,
        "usage_note": (
            "Use the suggested clusters for a small number of broad WoS searches. Import the resulting Plain Text Full Record + Cited References batches, rerun matching, and then regenerate this report. Individual title completion is optional and should be reserved for high-value residual papers."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paperazzi-db", default="data/paperazzi.sqlite3")
    parser.add_argument("--wos-db", default="data/wos.sqlite3")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_report(
        Path(args.paperazzi_db), Path(args.wos_db), limit=max(1, args.limit)
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
