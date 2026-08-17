"""Optimized similar-name candidate refresh for manual identity review.

The hot path is deliberately corpus-index based: active paper memberships are loaded once,
then pair scoring is performed in memory inside family/initial blocks. Similarity is only a
human-review aid; this module never auto-merges identities.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from .manual_review import (
    _author_variant_map,
    _best_author_pair_score,
    _compact,
    sync_author_name_variants,
)
from .models import Authorship, AuthorNameVariant
from .review import enqueue_review


def _best_review_score(
    left: list[AuthorNameVariant], right: list[AuthorNameVariant]
) -> tuple[float, dict[str, float], tuple[str, str] | None]:
    score, components, names = _best_author_pair_score(left, right)
    # Review-only East-Asian/order guard: some sources swap structured given/family fields.
    # This never becomes an auto-merge condition.
    for lv in left:
        for rv in right:
            lf, lg = _compact(lv.family_name), _compact(lv.given_name)
            rf, rg = _compact(rv.family_name), _compact(rv.given_name)
            if lf and lg and rf and rg and lf == rg and lg == rf and 0.95 > score:
                score = 0.95
                components = {"given_family_order_swapped": 0.95}
                names = (lv.raw_name, rv.raw_name)
    return score, components, names


def _variant_block_keys(row: AuthorNameVariant) -> set[tuple[str, str]]:
    """Return normal + review-only swapped-order blocking keys for one spelling."""
    family = _compact(row.family_name)
    given = _compact(row.given_name)
    given_initial = given[:1] if given else (row.initials or "")[:1].casefold()
    family_initial = family[:1]
    keys: set[tuple[str, str]] = set()
    if family and given_initial:
        keys.add((family, given_initial))
    if given and family_initial:
        keys.add((given, family_initial))
    return keys


def _papers_by_author(session: Any) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for author_id, paper_id in (
        session.query(Authorship.author_id, Authorship.paper_id)
        .filter(Authorship.status == "ACTIVE")
        .all()
    ):
        result[author_id].add(int(paper_id))
    return result


def similar_author_candidates(
    session: Any,
    author_id: str,
    *,
    minimum_score: float = 0.25,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return several review candidates for one canonical author.

    Unlike the queue refresh (one strongest queue entry per source identity), the detail
    view should let a human compare several plausible people. Same-paper candidates are
    retained but flagged because merge itself will be blocked by the Phase 4 guard.
    """
    variants = _author_variant_map(session)
    target = variants.get(author_id, [])
    if not target:
        return []
    target_keys = set().union(*(_variant_block_keys(row) for row in target))
    if not target_keys:
        return []
    papers = _papers_by_author(session)
    rows: list[dict[str, Any]] = []
    for candidate_id, candidate_variants in variants.items():
        if candidate_id == author_id:
            continue
        candidate_keys = set().union(*(_variant_block_keys(row) for row in candidate_variants))
        if target_keys.isdisjoint(candidate_keys):
            continue
        score, components, names = _best_review_score(target, candidate_variants)
        if score < minimum_score:
            continue
        rows.append(
            {
                "author_id": candidate_id,
                "similarity_score": score,
                "similarity_components": components,
                "representative_names": names,
                "same_paper_conflict": bool(papers[author_id] & papers[candidate_id]),
            }
        )
    rows.sort(
        key=lambda row: (
            row["same_paper_conflict"],
            -row["similarity_score"],
            row["author_id"],
        )
    )
    return rows[: min(max(1, limit), 50)]


def refresh_similar_identity_reviews(
    session: Any,
    *,
    minimum_score: float = 0.50,
    max_new_reviews: int = 500,
) -> dict[str, int]:
    sync_author_name_variants(session)
    variants = _author_variant_map(session)

    blocks: dict[tuple[str, str], set[str]] = defaultdict(set)
    for author_id, rows in variants.items():
        for row in rows:
            for key in _variant_block_keys(row):
                blocks[key].add(author_id)

    papers_by_author = _papers_by_author(session)
    best_for_source: dict[str, tuple[float, str, dict[str, float], tuple[str, str] | None]] = {}
    pair_count = 0
    scored_pair_count = 0
    same_paper_blocked = 0
    seen_pairs: set[tuple[str, str]] = set()
    for ids in blocks.values():
        ordered = sorted(ids)
        for index, left_id in enumerate(ordered):
            for right_id in ordered[index + 1 :]:
                pair = (left_id, right_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                pair_count += 1
                if papers_by_author[left_id] & papers_by_author[right_id]:
                    same_paper_blocked += 1
                    continue
                score, components, names = _best_review_score(
                    variants[left_id], variants[right_id]
                )
                scored_pair_count += 1
                if score < minimum_score:
                    continue
                for source_id, candidate_id in ((left_id, right_id), (right_id, left_id)):
                    previous = best_for_source.get(source_id)
                    if previous is None or score > previous[0]:
                        best_for_source[source_id] = (
                            score,
                            candidate_id,
                            components,
                            names,
                        )

    created_or_updated = 0
    for source_id, (score, candidate_id, components, names) in sorted(
        best_for_source.items(), key=lambda item: (-item[1][0], item[0])
    )[:max_new_reviews]:
        enqueue_review(
            session,
            queue_type="SIMILAR_AUTHOR_IDENTITY",
            subject_type="author",
            subject_id=source_id,
            candidate_id=candidate_id,
            reason_code="SIMILAR_NAME_VARIANTS",
            payload={
                "similarity_score": score,
                "components": components,
                "representative_names": names,
            },
            priority=95 if score >= 0.90 else 70,
        )
        created_or_updated += 1
    session.flush()
    return {
        "blocked_pairs_examined": pair_count,
        "same_paper_pairs_blocked": same_paper_blocked,
        "pairs_similarity_scored": scored_pair_count,
        "candidate_sources": len(best_for_source),
        "reviews_created_or_updated": created_or_updated,
    }
