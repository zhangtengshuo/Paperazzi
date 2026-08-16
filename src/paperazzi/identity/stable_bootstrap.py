"""Stable Phase 4 author bootstrap built from immutable source-corpus evidence.

The original bootstrap scored a mention against the *current* canonical identity graph.
That made results depend on loop order: an accepted mention enlarged an author's
collaboration neighborhood and could push an earlier candidate over the threshold on a
second run.  This implementation separates seed creation from scoring and derives
collaboration evidence exclusively from Phase-3 source mentions.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from paperazzi.database.models import PaperCreatorMention

from . import service as _legacy_service
from .models import Author, AuthorNameVariant
from .normalization import compatible_initials, name_features
from .policy import (
    IDENTITY_AUTO_ACCEPT_MARGIN,
    POLICY_VERSION,
)
from .review import enqueue_review
from .source_collaboration import SourceCollaborationIndex

RESOLVER_VERSION = f"phase4-identity-v3-source-corpus+{POLICY_VERSION}"


@dataclass
class _ResolutionPlan:
    mention: PaperCreatorMention
    best_author: Author
    best_score: _legacy_service.IdentityScore
    second_score: float
    candidate_count: int
    auto_accept: bool


def _accepted_membership(session: Any, creator_mention_id: int):
    return _legacy_service._accepted_membership(session, creator_mention_id)


def _mention_features(mention: PaperCreatorMention):
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


def _anchor_source_creator_ids(
    session: Any,
    author_id: str,
    source_index: SourceCollaborationIndex,
) -> set[int]:
    mention_ids = [
        mention_id
        for (mention_id,) in (
            session.query(AuthorNameVariant.source_creator_mention_id)
            .filter(
                AuthorNameVariant.author_id == author_id,
                AuthorNameVariant.source_creator_mention_id.is_not(None),
            )
            .all()
        )
        if mention_id is not None
    ]
    result: set[int] = set()
    for mention_id in mention_ids:
        mention = source_index.mention(int(mention_id))
        if mention is not None and mention.source_creator_id is not None:
            result.add(mention.source_creator_id)
    return result


def _author_stable_key(
    session: Any,
    author: Author,
) -> tuple[int, str]:
    source_ids = [
        value
        for (value,) in (
            session.query(AuthorNameVariant.source_creator_mention_id)
            .filter(
                AuthorNameVariant.author_id == author.author_id,
                AuthorNameVariant.source_creator_mention_id.is_not(None),
            )
            .all()
        )
        if value is not None
    ]
    return (min(source_ids) if source_ids else 2**63 - 1, author.author_id)


def score_mention_against_author(
    session: Any,
    mention: PaperCreatorMention,
    author: Author,
    *,
    source_index: SourceCollaborationIndex | None = None,
) -> _legacy_service.IdentityScore:
    """Score using source-only collaboration evidence.

    No accepted membership or authorship created by this resolver participates in the
    score.  Manual merge history may change an author's source-name variants, which is
    intentional authoritative input; deterministic links do not add source anchors.
    """
    if source_index is None:
        source_index = SourceCollaborationIndex.from_session(session)

    target = _mention_features(mention)
    variants = session.query(AuthorNameVariant).filter_by(author_id=author.author_id).all()
    components: dict[str, float] = {}

    exact_name = any(v.normalized_name == target.normalized_name for v in variants)
    if exact_name and target.normalized_name:
        components["normalized_full_name"] = 0.40

    family_initial_match = any(
        v.family_name == target.family_name
        and compatible_initials(v.initials, target.initials)
        for v in variants
        if v.family_name and target.family_name
    )
    if family_initial_match:
        components["family_initials"] = 0.10

    anchor_source_ids = _anchor_source_creator_ids(
        session, author.author_id, source_index
    )
    source_creator_exact = bool(
        mention.source_creator_id is not None
        and mention.source_creator_id in anchor_source_ids
    )
    if source_creator_exact:
        components["source_creator_reuse"] = 0.25

    overlap = source_index.overlap(
        mention,
        anchor_source_ids,
        target_name=target.normalized_name,
    )
    effective_overlap = overlap.effective_overlap
    if effective_overlap >= 2:
        components["coauthor_overlap"] = 0.35
    elif effective_overlap == 1:
        components["coauthor_overlap"] = 0.15

    return _legacy_service.IdentityScore(
        score=min(1.0, sum(components.values())),
        components=components,
        coauthor_overlap=effective_overlap,
        source_creator_exact=source_creator_exact,
    )


def _same_paper_accepted_author_ids(session: Any) -> dict[int, set[str]]:
    rows = (
        session.query(PaperCreatorMention.paper_id, _legacy_service.AuthorIdentityMembership.author_id)
        .join(
            _legacy_service.AuthorIdentityMembership,
            _legacy_service.AuthorIdentityMembership.creator_mention_id
            == PaperCreatorMention.creator_mention_id,
        )
        .filter(
            PaperCreatorMention.creator_type == "author",
            _legacy_service.AuthorIdentityMembership.status == "ACCEPTED",
        )
        .all()
    )
    result: dict[int, set[str]] = defaultdict(set)
    for paper_id, author_id in rows:
        result[int(paper_id)].add(author_id)
    return result


def _seed_required_name_multiplicity(
    session: Any,
    mentions: list[PaperCreatorMention],
    counts: dict[str, int],
) -> None:
    """Create the minimum stable seed set before any positive identity propagation.

    One name block needs at least as many distinct canonical identities as the maximum
    number of same-normalized-name authors appearing together on one paper.  This makes
    same-paper namesake protection part of the frozen candidate set rather than a side
    effect of loop order.
    """
    blocks: dict[str, list[PaperCreatorMention]] = defaultdict(list)
    for mention in mentions:
        if _accepted_membership(session, mention.creator_mention_id) is not None:
            continue
        normalized = _mention_features(mention).normalized_name
        if not normalized:
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="EMPTY_NAME_NEW_IDENTITY",
            )
            counts["created"] += 1
            continue
        blocks[normalized].append(mention)

    for normalized_name in sorted(blocks):
        block = blocks[normalized_name]
        active_ids = _active_author_ids_for_name(session, normalized_name)
        per_paper = Counter(mention.paper_id for mention in block)

        # Include already-resolved source mentions in the multiplicity requirement.
        resolved_same_name = (
            session.query(PaperCreatorMention)
            .filter(PaperCreatorMention.creator_type == "author")
            .all()
        )
        full_per_paper: Counter[int] = Counter()
        for row in resolved_same_name:
            if _mention_features(row).normalized_name == normalized_name:
                full_per_paper[row.paper_id] += 1
        max_multiplicity = max(full_per_paper.values(), default=max(per_paper.values(), default=1))
        needed = max(0, max_multiplicity - len(active_ids))
        if needed == 0:
            continue

        exemplar_paper = min(
            (paper_id for paper_id, n in full_per_paper.items() if n == max_multiplicity),
            default=min(per_paper),
        )
        # Prefer later-listed duplicate names as extra seeds.  If there is no existing
        # identity, the final fallback still deterministically seeds the earliest source
        # mention in the block.
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
            if _accepted_membership(session, mention.creator_mention_id) is not None:
                continue
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="STABLE_NAME_BLOCK_SEED",
            )
            counts["created"] += 1
            needed -= 1


def _seed_no_candidate_closure(
    session: Any,
    mentions: list[PaperCreatorMention],
    counts: dict[str, int],
) -> None:
    """Resolve only negative/capacity holes before freezing candidates.

    This closure may create source seeds, but it never accepts a positive match.  It is
    therefore not an identity-propagation loop.
    """
    while True:
        same_paper = _same_paper_accepted_author_ids(session)
        seed_by_name: dict[str, PaperCreatorMention] = {}
        for mention in mentions:
            if _accepted_membership(session, mention.creator_mention_id) is not None:
                continue
            features = _mention_features(mention)
            if not features.normalized_name:
                continue
            candidate_ids = _active_author_ids_for_name(
                session, features.normalized_name
            )
            candidate_ids -= same_paper.get(mention.paper_id, set())
            candidate_ids = {
                author_id
                for author_id in candidate_ids
                if not _legacy_service._not_same_blocked(
                    session, mention.creator_mention_id, author_id
                )
            }
            if not candidate_ids:
                current = seed_by_name.get(features.normalized_name)
                key = (mention.paper_id, mention.order_index, mention.creator_mention_id)
                if current is None or key < (
                    current.paper_id,
                    current.order_index,
                    current.creator_mention_id,
                ):
                    seed_by_name[features.normalized_name] = mention
        if not seed_by_name:
            return
        for normalized_name in sorted(seed_by_name):
            mention = seed_by_name[normalized_name]
            if _accepted_membership(session, mention.creator_mention_id) is not None:
                continue
            _legacy_service.create_author_for_mention(
                session,
                mention,
                reason_code="STABLE_NO_CANDIDATE_SEED",
            )
            counts["created"] += 1
        session.flush()


def bootstrap_author_identities(session: Any, *, limit: int | None = None) -> dict[str, int]:
    """Resolve Zotero author mentions with deterministic, rerun-idempotent evidence.

    Every Zotero `creator_type='author'` mention remains recorded in
    `paper_creator_mentions`, whether or not its person identity can be resolved.
    Non-author creator types remain source records but are outside the Phase-4 author
    identity resolver.
    """
    query = (
        session.query(PaperCreatorMention)
        .filter(PaperCreatorMention.creator_type == "author")
        .order_by(
            PaperCreatorMention.paper_id,
            PaperCreatorMention.order_index,
            PaperCreatorMention.creator_mention_id,
        )
    )
    if limit is not None:
        query = query.limit(limit)
    mentions = query.all()
    source_index = SourceCollaborationIndex.from_session(session)

    counts = {
        "source_author_mentions": len(mentions),
        "created": 0,
        "linked": 0,
        "candidate": 0,
        "already_resolved": 0,
        "not_same_blocked": 0,
        "locked_review": 0,
        "same_paper_collision_review": 0,
    }

    initial_resolved = {
        mention.creator_mention_id
        for mention in mentions
        if _accepted_membership(session, mention.creator_mention_id) is not None
    }
    counts["already_resolved"] = len(initial_resolved)

    # Phase A: complete the minimum canonical seed set.  No positive candidate score is
    # evaluated until this seed set is stable.
    _seed_required_name_multiplicity(session, mentions, counts)
    _seed_no_candidate_closure(session, mentions, counts)
    session.flush()

    # Phase B: freeze candidate universe and same-paper exclusions.  Everything below
    # may write decisions, but none of those writes can alter another score in this run.
    same_paper_snapshot = _same_paper_accepted_author_ids(session)
    author_ids_by_name: dict[str, set[str]] = {}
    for mention in mentions:
        normalized = _mention_features(mention).normalized_name
        if normalized and normalized not in author_ids_by_name:
            author_ids_by_name[normalized] = _active_author_ids_for_name(
                session, normalized
            )

    plans: list[_ResolutionPlan] = []
    for mention in mentions:
        if _accepted_membership(session, mention.creator_mention_id) is not None:
            continue
        features = _mention_features(mention)
        if not features.normalized_name:
            raise _legacy_service.IdentityResolutionError(
                "empty-name author remained unresolved after stable seed phase"
            )

        author_ids = set(author_ids_by_name.get(features.normalized_name, set()))
        author_ids -= same_paper_snapshot.get(mention.paper_id, set())
        blocked_ids = {
            author_id
            for author_id in author_ids
            if _legacy_service._not_same_blocked(
                session, mention.creator_mention_id, author_id
            )
        }
        counts["not_same_blocked"] += len(blocked_ids)
        author_ids -= blocked_ids
        if not author_ids:
            raise _legacy_service.IdentityResolutionError(
                "stable seed closure left an author mention without a candidate"
            )

        scored: list[tuple[Author, _legacy_service.IdentityScore]] = []
        for author_id in author_ids:
            author = session.get(Author, author_id)
            if author is None:
                continue
            score = score_mention_against_author(
                session,
                mention,
                author,
                source_index=source_index,
            )
            _legacy_service._candidate_membership(session, mention, author, score)
            scored.append((author, score))
        if not scored:
            raise _legacy_service.IdentityResolutionError(
                "stable candidate author rows disappeared during planning"
            )

        scored.sort(
            key=lambda item: (-item[1].score, _author_stable_key(session, item[0]))
        )
        best_author, best = scored[0]
        second_score = scored[1][1].score if len(scored) > 1 else 0.0
        can_auto_accept = (
            best.auto_accept_eligible
            and best.score - second_score >= IDENTITY_AUTO_ACCEPT_MARGIN
            and not best_author.locked
        )
        plans.append(
            _ResolutionPlan(
                mention=mention,
                best_author=best_author,
                best_score=best,
                second_score=second_score,
                candidate_count=len(scored),
                auto_accept=can_auto_accept,
            )
        )

    # A canonical author cannot occupy two author slots on one paper.  Suppress all
    # colliding auto-links rather than letting loop order select a winner.
    proposed_by_paper_author: dict[tuple[int, str], list[_ResolutionPlan]] = defaultdict(list)
    for plan in plans:
        if plan.auto_accept:
            proposed_by_paper_author[
                (plan.mention.paper_id, plan.best_author.author_id)
            ].append(plan)
    collisions = {
        key
        for key, rows in proposed_by_paper_author.items()
        if len(rows) > 1
    }

    for plan in plans:
        collision = (
            plan.mention.paper_id,
            plan.best_author.author_id,
        ) in collisions
        if plan.auto_accept and not collision:
            _legacy_service.accept_membership(
                session,
                plan.mention,
                plan.best_author,
                actor="DETERMINISTIC",
                score=plan.best_score,
                reason_code="STRONG_IMMUTABLE_SOURCE_IDENTITY_EVIDENCE",
            )
            counts["linked"] += 1
            continue

        if plan.best_author.locked:
            counts["locked_review"] += 1
        if collision:
            counts["same_paper_collision_review"] += 1
        enqueue_review(
            session,
            queue_type="AMBIGUOUS_AUTHOR_IDENTITY",
            subject_type="creator_mention",
            subject_id=plan.mention.creator_mention_id,
            candidate_id=plan.best_author.author_id,
            reason_code=(
                "SAME_PAPER_IDENTITY_COLLISION"
                if collision
                else (
                    "LOCKED_IDENTITY_REQUIRES_REVIEW"
                    if plan.best_author.locked
                    else "NAME_BLOCK_REQUIRES_REVIEW"
                )
            ),
            payload={
                "normalized_name": _mention_features(plan.mention).normalized_name,
                "best_score": plan.best_score.score,
                "second_score": plan.second_score,
                "candidate_count": plan.candidate_count,
                "components": plan.best_score.components,
                "evidence_basis": "IMMUTABLE_SOURCE_CORPUS",
            },
            priority=70 if collision else (60 if plan.best_score.score >= 0.6 else 40),
        )
        counts["candidate"] += 1

    session.flush()
    return counts


# Compatibility patch: `paperazzi.identity.service` has been the public import path in
# Phase 4 tests/scripts.  Keep that API while replacing only the unstable batch/scoring
# implementation.  Merge/split/manual operations remain in service.py.
_legacy_service.RESOLVER_VERSION = RESOLVER_VERSION
_legacy_service.score_mention_against_author = score_mention_against_author
_legacy_service.bootstrap_author_identities = bootstrap_author_identities
