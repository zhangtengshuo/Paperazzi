"""Efficient deterministic seed construction for the stable Phase 4 resolver."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from paperazzi.database.models import PaperCreatorMention

from . import service as _legacy_service
from .models import Author, AuthorNameVariant
from .normalization import name_features


def _features(mention: PaperCreatorMention):
    return name_features(mention.first_name, mention.last_name, mention.display_name)


def _active_author_ids_for_name(session: Any, normalized_name: str) -> set[str]:
    return {
        author_id
        for (author_id,) in (
            session.query(AuthorNameVariant.author_id)
            .join(Author, Author.author_id == AuthorNameVariant.author_id)
            .filter(
                AuthorNameVariant.normalized_name == normalized_name,
                Author.status == "ACTIVE",
            )
            .all()
        )
    }


def seed_required_name_multiplicity(
    session: Any,
    mentions: list[PaperCreatorMention],
    counts: dict[str, int],
) -> None:
    """Create the minimum stable seed set in O(N + blocks) source-side work."""
    unresolved_blocks: dict[str, list[PaperCreatorMention]] = defaultdict(list)
    multiplicity: dict[str, Counter[int]] = defaultdict(Counter)

    for mention in mentions:
        normalized = _features(mention).normalized_name
        if normalized:
            multiplicity[normalized][mention.paper_id] += 1
        if _legacy_service._accepted_membership(
            session, mention.creator_mention_id
        ) is not None:
            continue
        if not normalized:
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="EMPTY_NAME_NEW_IDENTITY",
            )
            counts["created"] += 1
            continue
        unresolved_blocks[normalized].append(mention)

    for normalized_name in sorted(unresolved_blocks):
        block = unresolved_blocks[normalized_name]
        active_ids = _active_author_ids_for_name(session, normalized_name)
        per_paper = multiplicity[normalized_name]
        max_multiplicity = max(per_paper.values(), default=1)
        needed = max(0, max_multiplicity - len(active_ids))
        if needed == 0:
            continue

        exemplar_paper = min(
            paper_id for paper_id, number in per_paper.items()
            if number == max_multiplicity
        )
        preferred = sorted(
            [m for m in block if m.paper_id == exemplar_paper],
            key=lambda m: (-m.order_index, m.creator_mention_id),
        )
        fallback = sorted(
            [m for m in block if m.paper_id != exemplar_paper],
            key=lambda m: (m.paper_id, m.order_index, m.creator_mention_id),
        )
        pool = preferred + fallback
        if not active_ids and needed == 1:
            pool = sorted(
                block,
                key=lambda m: (m.paper_id, m.order_index, m.creator_mention_id),
            )

        for mention in pool:
            if needed == 0:
                break
            if _legacy_service._accepted_membership(
                session, mention.creator_mention_id
            ) is not None:
                continue
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="STABLE_NAME_BLOCK_SEED",
            )
            counts["created"] += 1
            needed -= 1
