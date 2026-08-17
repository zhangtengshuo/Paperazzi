"""Optimized similar-name candidate refresh for manual identity review.

The hot path is deliberately corpus-index based: active paper memberships are loaded once,
then pair scoring is performed in memory inside family/initial blocks.  This avoids one SQL
query per candidate pair on the ~7k-author real corpus.
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
from .models import Authorship
from .review import enqueue_review


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
            family = _compact(row.family_name)
            given = _compact(row.given_name)
            initial = given[:1] if given else (row.initials or "")[:1]
            if family and initial:
                blocks[(family, initial)].add(author_id)

    # One query builds the same-paper negative guard for every identity.
    papers_by_author: dict[str, set[int]] = defaultdict(set)
    for author_id, paper_id in (
        session.query(Authorship.author_id, Authorship.paper_id)
        .filter(Authorship.status == "ACTIVE")
        .all()
    ):
        papers_by_author[author_id].add(int(paper_id))

    best_for_source: dict[str, tuple[float, str, dict[str, float], tuple[str, str] | None]] = {}
    pair_count = 0
    scored_pair_count = 0
    same_paper_blocked = 0
    for ids in blocks.values():
        ordered = sorted(ids)
        for index, left_id in enumerate(ordered):
            for right_id in ordered[index + 1 :]:
                pair_count += 1
                if papers_by_author[left_id] & papers_by_author[right_id]:
                    same_paper_blocked += 1
                    continue
                score, components, names = _best_author_pair_score(
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
            queue_type="IDENTITY_CONFLICT",
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
