"""Efficient deterministic seed construction for the stable Phase 4 resolver."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from paperazzi.database.models import PaperCreatorMention

from . import service as _legacy_service
from .models import Author, AuthorIdentityMembership, AuthorNameVariant
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


def _same_paper_accepted_author_ids(session: Any) -> dict[int, set[str]]:
    rows = (
        session.query(PaperCreatorMention.paper_id, AuthorIdentityMembership.author_id)
        .join(
            AuthorIdentityMembership,
            AuthorIdentityMembership.creator_mention_id
            == PaperCreatorMention.creator_mention_id,
        )
        .filter(
            PaperCreatorMention.creator_type == "author",
            AuthorIdentityMembership.status == "ACCEPTED",
        )
        .all()
    )
    result: dict[int, set[str]] = defaultdict(set)
    for paper_id, author_id in rows:
        result[int(paper_id)].add(author_id)
    return result


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
            paper_id
            for paper_id, number in per_paper.items()
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


def seed_no_candidate_closure(
    session: Any,
    mentions: list[PaperCreatorMention],
    counts: dict[str, int],
) -> None:
    """Create deterministic seeds for negative/capacity holes before scoring.

    Explicit NOT_SAME_PERSON constraints remain observable in `not_same_blocked` even
    when they force immediate creation of a separate identity.
    """
    counted_blocks: set[tuple[int, str]] = set()
    while True:
        same_paper = _same_paper_accepted_author_ids(session)
        unresolved_names = {
            _features(mention).normalized_name
            for mention in mentions
            if _legacy_service._accepted_membership(
                session, mention.creator_mention_id
            ) is None
            and _features(mention).normalized_name
        }
        active_by_name = {
            name: _active_author_ids_for_name(session, name)
            for name in unresolved_names
        }
        seed_by_name: dict[str, PaperCreatorMention] = {}

        for mention in mentions:
            if _legacy_service._accepted_membership(
                session, mention.creator_mention_id
            ) is not None:
                continue
            normalized = _features(mention).normalized_name
            if not normalized:
                continue
            candidate_ids = set(active_by_name.get(normalized, set()))
            candidate_ids -= same_paper.get(mention.paper_id, set())
            blocked_ids = {
                author_id
                for author_id in candidate_ids
                if _legacy_service._not_same_blocked(
                    session, mention.creator_mention_id, author_id
                )
            }
            for author_id in blocked_ids:
                key = (mention.creator_mention_id, author_id)
                if key not in counted_blocks:
                    counted_blocks.add(key)
                    counts["not_same_blocked"] += 1
            candidate_ids -= blocked_ids
            if candidate_ids:
                continue

            current = seed_by_name.get(normalized)
            mention_key = (
                mention.paper_id,
                mention.order_index,
                mention.creator_mention_id,
            )
            if current is None or mention_key < (
                current.paper_id,
                current.order_index,
                current.creator_mention_id,
            ):
                seed_by_name[normalized] = mention

        if not seed_by_name:
            return

        for normalized in sorted(seed_by_name):
            mention = seed_by_name[normalized]
            if _legacy_service._accepted_membership(
                session, mention.creator_mention_id
            ) is not None:
                continue
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="STABLE_NO_CANDIDATE_SEED",
            )
            counts["created"] += 1
        session.flush()
