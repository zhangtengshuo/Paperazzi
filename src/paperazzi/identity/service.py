"""Conservative, reversible author identity resolution for Phase 4.

The resolver may create a new identity for an unresolved source mention. It never
merges two existing people from normalized name alone.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from paperazzi.database.base import utcnow
from paperazzi.database.models import PaperCreatorMention

from .models import (
    Author,
    AuthorIdentityDecision,
    AuthorIdentityEvidence,
    AuthorIdentityMembership,
    AuthorNameVariant,
    Authorship,
)
from .normalization import compatible_initials, name_features, normalize_name
from .review import enqueue_review

RESOLVER_VERSION = "phase4-identity-v1"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class IdentityResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class IdentityScore:
    score: float
    components: dict[str, float]
    coauthor_overlap: int
    source_creator_exact: bool

    @property
    def auto_accept_eligible(self) -> bool:
        # Name never closes the decision. Automatic linking requires an independent
        # source-local signal plus a strong collaboration-neighborhood signal.
        return (
            self.score >= 0.85
            and self.source_creator_exact
            and self.coauthor_overlap >= 2
        )


def new_author_id(timestamp_ms: int | None = None) -> str:
    """Generate a 26-character ULID-compatible sortable identifier."""
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if timestamp_ms < 0 or timestamp_ms >= 2**48:
        raise ValueError("ULID timestamp must fit in 48 bits")
    value = (timestamp_ms << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _CROCKFORD[value & 31]
        value >>= 5
    return "".join(chars)


def _mention_features(mention: PaperCreatorMention):
    return name_features(mention.first_name, mention.last_name, mention.display_name)


def _accepted_membership(session: Any, creator_mention_id: int) -> AuthorIdentityMembership | None:
    return (
        session.query(AuthorIdentityMembership)
        .filter_by(creator_mention_id=creator_mention_id, status="ACCEPTED")
        .one_or_none()
    )


def _paper_coauthor_names(session: Any, mention: PaperCreatorMention) -> set[str]:
    rows = (
        session.query(PaperCreatorMention)
        .filter(
            PaperCreatorMention.paper_id == mention.paper_id,
            PaperCreatorMention.creator_mention_id != mention.creator_mention_id,
            PaperCreatorMention.creator_type == "author",
        )
        .all()
    )
    return {
        _mention_features(row).normalized_name
        for row in rows
        if _mention_features(row).normalized_name
    }


def _author_mentions(session: Any, author_id: str) -> list[PaperCreatorMention]:
    return (
        session.query(PaperCreatorMention)
        .join(
            AuthorIdentityMembership,
            AuthorIdentityMembership.creator_mention_id == PaperCreatorMention.creator_mention_id,
        )
        .filter(
            AuthorIdentityMembership.author_id == author_id,
            AuthorIdentityMembership.status == "ACCEPTED",
        )
        .all()
    )


def _author_coauthor_names(session: Any, author_id: str, target_name: str) -> set[str]:
    mentions = _author_mentions(session, author_id)
    paper_ids = {mention.paper_id for mention in mentions}
    if not paper_ids:
        return set()
    rows = (
        session.query(PaperCreatorMention)
        .filter(
            PaperCreatorMention.paper_id.in_(paper_ids),
            PaperCreatorMention.creator_type == "author",
        )
        .all()
    )
    names = {
        _mention_features(row).normalized_name
        for row in rows
        if _mention_features(row).normalized_name
    }
    names.discard(target_name)
    return names


def score_mention_against_author(
    session: Any,
    mention: PaperCreatorMention,
    author: Author,
) -> IdentityScore:
    target = _mention_features(mention)
    variants = (
        session.query(AuthorNameVariant)
        .filter_by(author_id=author.author_id)
        .all()
    )
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

    accepted_mentions = _author_mentions(session, author.author_id)
    source_creator_exact = bool(
        mention.source_creator_id is not None
        and any(row.source_creator_id == mention.source_creator_id for row in accepted_mentions)
    )
    if source_creator_exact:
        components["source_creator_reuse"] = 0.25

    current_coauthors = _paper_coauthor_names(session, mention)
    historical_coauthors = _author_coauthor_names(
        session, author.author_id, target.normalized_name
    )
    overlap = len(current_coauthors & historical_coauthors)
    if overlap >= 2:
        components["coauthor_overlap"] = 0.35
    elif overlap == 1:
        components["coauthor_overlap"] = 0.15

    return IdentityScore(
        score=min(1.0, sum(components.values())),
        components=components,
        coauthor_overlap=overlap,
        source_creator_exact=source_creator_exact,
    )


def _first_author(session: Any, mention: PaperCreatorMention) -> bool:
    if mention.creator_type != "author":
        return False
    first_order = (
        session.query(sa.func.min(PaperCreatorMention.order_index))
        .filter(
            PaperCreatorMention.paper_id == mention.paper_id,
            PaperCreatorMention.creator_type == "author",
        )
        .scalar()
    )
    return first_order == mention.order_index


def _ensure_authorship(
    session: Any,
    mention: PaperCreatorMention,
    author_id: str,
) -> Authorship:
    active = (
        session.query(Authorship)
        .filter_by(creator_mention_id=mention.creator_mention_id, status="ACTIVE")
        .one_or_none()
    )
    if active is not None:
        if active.author_id != author_id:
            active.status = "SUPERSEDED"
            active.updated_at = utcnow()
            session.flush()
        else:
            return active
    row = Authorship(
        author_id=author_id,
        paper_id=mention.paper_id,
        creator_mention_id=mention.creator_mention_id,
        order_index=mention.order_index,
        creator_type=mention.creator_type,
        is_first_author=_first_author(session, mention),
        is_corresponding_author=False,
        corresponding_status="UNKNOWN",
        status="ACTIVE",
    )
    session.add(row)
    session.flush()
    return row


def _record_decision(
    session: Any,
    *,
    operation: str,
    actor: str,
    mention: PaperCreatorMention | None = None,
    membership: AuthorIdentityMembership | None = None,
    source_author_id: str | None = None,
    target_author_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    reason_code: str | None = None,
    notes: str | None = None,
) -> AuthorIdentityDecision:
    row = AuthorIdentityDecision(
        operation=operation,
        actor=actor,
        creator_mention_id=None if mention is None else mention.creator_mention_id,
        membership_id=None if membership is None else membership.membership_id,
        source_author_id=source_author_id,
        target_author_id=target_author_id,
        algorithm_version=RESOLVER_VERSION if actor != "MANUAL" else None,
        evidence_json=json.dumps(evidence or {}, sort_keys=True, ensure_ascii=False),
        previous_state_json=json.dumps(previous or {}, sort_keys=True, ensure_ascii=False),
        resulting_state_json=json.dumps(result or {}, sort_keys=True, ensure_ascii=False),
        reason_code=reason_code,
        notes=notes,
    )
    session.add(row)
    session.flush()
    return row


def create_author_for_mention(
    session: Any,
    mention: PaperCreatorMention,
    *,
    actor: str = "DETERMINISTIC",
    reason_code: str = "NEW_NAME_BLOCK",
) -> tuple[Author, AuthorIdentityMembership]:
    existing = _accepted_membership(session, mention.creator_mention_id)
    if existing is not None:
        return session.get(Author, existing.author_id), existing

    features = _mention_features(mention)
    author = Author(
        author_id=new_author_id(),
        preferred_name=features.raw_name or mention.display_name,
        normalized_name=features.normalized_name or None,
        status="ACTIVE",
        locked=False,
    )
    session.add(author)
    session.flush()
    session.add(
        AuthorNameVariant(
            author_id=author.author_id,
            source_creator_mention_id=mention.creator_mention_id,
            raw_name=features.raw_name or mention.display_name or "",
            normalized_name=features.normalized_name,
            family_name=features.family_name,
            given_name=features.given_name,
            initials=features.initials,
            search_form=features.search_form,
            variant_type="SOURCE",
            provenance="paper_creator_mentions",
        )
    )
    membership = AuthorIdentityMembership(
        creator_mention_id=mention.creator_mention_id,
        author_id=author.author_id,
        status="ACCEPTED",
        resolver=RESOLVER_VERSION,
        score=1.0,
        score_components_json=json.dumps({"new_identity": 1.0}),
        reason_code=reason_code,
    )
    session.add(membership)
    session.flush()
    _ensure_authorship(session, mention, author.author_id)
    _record_decision(
        session,
        operation="CREATE_IDENTITY",
        actor=actor,
        mention=mention,
        membership=membership,
        target_author_id=author.author_id,
        result={"membership_status": "ACCEPTED"},
        reason_code=reason_code,
    )
    return author, membership


def _candidate_membership(
    session: Any,
    mention: PaperCreatorMention,
    author: Author,
    score: IdentityScore,
) -> AuthorIdentityMembership:
    row = (
        session.query(AuthorIdentityMembership)
        .filter_by(
            creator_mention_id=mention.creator_mention_id,
            author_id=author.author_id,
            status="CANDIDATE",
        )
        .one_or_none()
    )
    if row is None:
        row = AuthorIdentityMembership(
            creator_mention_id=mention.creator_mention_id,
            author_id=author.author_id,
            status="CANDIDATE",
            resolver=RESOLVER_VERSION,
            score=score.score,
            score_components_json=json.dumps(score.components, sort_keys=True),
            reason_code="NAME_BLOCK_CANDIDATE",
        )
        session.add(row)
        session.flush()
    else:
        row.score = score.score
        row.score_components_json = json.dumps(score.components, sort_keys=True)
        row.updated_at = utcnow()

    for evidence_type, component_score in score.components.items():
        exists = (
            session.query(AuthorIdentityEvidence)
            .filter_by(
                membership_id=row.membership_id,
                evidence_type=evidence_type,
            )
            .first()
        )
        if exists is None:
            session.add(
                AuthorIdentityEvidence(
                    membership_id=row.membership_id,
                    creator_mention_id=mention.creator_mention_id,
                    candidate_author_id=author.author_id,
                    evidence_type=evidence_type,
                    polarity="POSITIVE",
                    score=component_score,
                    source_kind="LOCAL_CORPUS",
                    payload_json="{}",
                )
            )
    session.flush()
    return row


def accept_membership(
    session: Any,
    mention: PaperCreatorMention,
    author: Author,
    *,
    actor: str,
    score: IdentityScore | None = None,
    reason_code: str = "REVIEW_ACCEPTED",
    notes: str | None = None,
) -> AuthorIdentityMembership:
    if author.status != "ACTIVE":
        raise IdentityResolutionError("cannot link a mention to a non-active author")
    if author.locked and actor != "MANUAL":
        raise IdentityResolutionError("locked identities may only be modified manually")

    current = _accepted_membership(session, mention.creator_mention_id)
    if current is not None and current.author_id == author.author_id:
        _ensure_authorship(session, mention, author.author_id)
        return current
    if current is not None:
        current.status = "SUPERSEDED"
        current.updated_at = utcnow()
        active_authorship = (
            session.query(Authorship)
            .filter_by(creator_mention_id=mention.creator_mention_id, status="ACTIVE")
            .one_or_none()
        )
        if active_authorship is not None:
            active_authorship.status = "SUPERSEDED"
            active_authorship.updated_at = utcnow()
        session.flush()

    candidate = (
        session.query(AuthorIdentityMembership)
        .filter_by(
            creator_mention_id=mention.creator_mention_id,
            author_id=author.author_id,
            status="CANDIDATE",
        )
        .one_or_none()
    )
    if candidate is None:
        candidate = AuthorIdentityMembership(
            creator_mention_id=mention.creator_mention_id,
            author_id=author.author_id,
            status="ACCEPTED",
            resolver=RESOLVER_VERSION if actor != "MANUAL" else "manual",
            score=None if score is None else score.score,
            score_components_json=json.dumps(
                {} if score is None else score.components, sort_keys=True
            ),
            reason_code=reason_code,
        )
        session.add(candidate)
    else:
        candidate.status = "ACCEPTED"
        candidate.reason_code = reason_code
        candidate.updated_at = utcnow()
    session.flush()
    _ensure_authorship(session, mention, author.author_id)
    _record_decision(
        session,
        operation="LINK_MENTION",
        actor=actor,
        mention=mention,
        membership=candidate,
        source_author_id=None if current is None else current.author_id,
        target_author_id=author.author_id,
        evidence={} if score is None else score.components,
        previous={} if current is None else {"author_id": current.author_id},
        result={"author_id": author.author_id, "membership_status": "ACCEPTED"},
        reason_code=reason_code,
        notes=notes,
    )
    return candidate


def bootstrap_author_identities(session: Any, *, limit: int | None = None) -> dict[str, int]:
    query = session.query(PaperCreatorMention).order_by(
        PaperCreatorMention.paper_id, PaperCreatorMention.order_index
    )
    if limit is not None:
        query = query.limit(limit)

    counts = {"created": 0, "linked": 0, "candidate": 0, "already_resolved": 0}
    for mention in query.all():
        if _accepted_membership(session, mention.creator_mention_id) is not None:
            counts["already_resolved"] += 1
            continue
        features = _mention_features(mention)
        if not features.normalized_name:
            create_author_for_mention(session, mention, reason_code="EMPTY_NAME_NEW_IDENTITY")
            counts["created"] += 1
            continue

        author_ids = {
            author_id
            for (author_id,) in (
                session.query(AuthorNameVariant.author_id)
                .join(Author, Author.author_id == AuthorNameVariant.author_id)
                .filter(
                    AuthorNameVariant.normalized_name == features.normalized_name,
                    Author.status == "ACTIVE",
                )
                .all()
            )
        }
        # Never collapse two same-name people who already occur on the same paper.
        same_paper_author_ids = {
            membership.author_id
            for membership in (
                session.query(AuthorIdentityMembership)
                .join(
                    PaperCreatorMention,
                    PaperCreatorMention.creator_mention_id
                    == AuthorIdentityMembership.creator_mention_id,
                )
                .filter(
                    PaperCreatorMention.paper_id == mention.paper_id,
                    AuthorIdentityMembership.status == "ACCEPTED",
                )
                .all()
            )
        }
        author_ids -= same_paper_author_ids

        if not author_ids:
            create_author_for_mention(session, mention)
            counts["created"] += 1
            continue

        scored: list[tuple[Author, IdentityScore]] = []
        for author_id in author_ids:
            author = session.get(Author, author_id)
            score = score_mention_against_author(session, mention, author)
            _candidate_membership(session, mention, author, score)
            scored.append((author, score))
        scored.sort(key=lambda item: item[1].score, reverse=True)
        best_author, best = scored[0]
        second_score = scored[1][1].score if len(scored) > 1 else 0.0

        if best.auto_accept_eligible and best.score - second_score >= 0.15:
            accept_membership(
                session,
                mention,
                best_author,
                actor="DETERMINISTIC",
                score=best,
                reason_code="STRONG_LOCAL_IDENTITY_EVIDENCE",
            )
            counts["linked"] += 1
        else:
            enqueue_review(
                session,
                queue_type="AMBIGUOUS_AUTHOR_IDENTITY",
                subject_type="creator_mention",
                subject_id=mention.creator_mention_id,
                candidate_id=best_author.author_id,
                reason_code="NAME_BLOCK_REQUIRES_REVIEW",
                payload={
                    "normalized_name": features.normalized_name,
                    "best_score": best.score,
                    "second_score": second_score,
                    "candidate_count": len(scored),
                    "components": best.components,
                },
                priority=60 if best.score >= 0.6 else 40,
            )
            counts["candidate"] += 1
    session.flush()
    return counts


def merge_authors(
    session: Any,
    source_author_id: str,
    target_author_id: str,
    *,
    actor: str = "MANUAL",
    notes: str | None = None,
) -> AuthorIdentityDecision:
    if source_author_id == target_author_id:
        raise IdentityResolutionError("cannot merge an author into itself")
    source = session.get(Author, source_author_id)
    target = session.get(Author, target_author_id)
    if source is None or target is None:
        raise IdentityResolutionError("merge author does not exist")
    if source.status != "ACTIVE" or target.status != "ACTIVE":
        raise IdentityResolutionError("merge requires two active authors")
    if (source.locked or target.locked) and actor != "MANUAL":
        raise IdentityResolutionError("locked identities may only be merged manually")

    memberships = (
        session.query(AuthorIdentityMembership)
        .filter_by(author_id=source_author_id, status="ACCEPTED")
        .all()
    )
    moved_mentions: list[int] = []
    for membership in memberships:
        mention = session.get(PaperCreatorMention, membership.creator_mention_id)
        membership.status = "SUPERSEDED"
        membership.updated_at = utcnow()
        active_authorship = (
            session.query(Authorship)
            .filter_by(creator_mention_id=mention.creator_mention_id, status="ACTIVE")
            .one_or_none()
        )
        if active_authorship is not None:
            active_authorship.status = "SUPERSEDED"
            active_authorship.updated_at = utcnow()
        session.flush()
        accept_membership(
            session,
            mention,
            target,
            actor=actor,
            reason_code="MERGE_IDENTITY",
            notes=notes,
        )
        moved_mentions.append(mention.creator_mention_id)

    source.status = "MERGED"
    source.merged_into_author_id = target_author_id
    source.updated_at = utcnow()
    if source.preferred_name:
        normalized = normalize_name(source.preferred_name)
        exists = (
            session.query(AuthorNameVariant)
            .filter_by(author_id=target_author_id, normalized_name=normalized)
            .first()
        )
        if exists is None:
            features = name_features(None, None, source.preferred_name)
            session.add(
                AuthorNameVariant(
                    author_id=target_author_id,
                    raw_name=source.preferred_name,
                    normalized_name=features.normalized_name,
                    family_name=features.family_name,
                    given_name=features.given_name,
                    initials=features.initials,
                    search_form=features.search_form,
                    variant_type="DERIVED",
                    provenance=f"merge:{source_author_id}",
                )
            )
    decision = _record_decision(
        session,
        operation="MERGE_IDENTITY",
        actor=actor,
        source_author_id=source_author_id,
        target_author_id=target_author_id,
        previous={"source_status": "ACTIVE"},
        result={"source_status": "MERGED", "moved_mentions": moved_mentions},
        reason_code="MERGE_IDENTITY",
        notes=notes,
    )
    session.flush()
    return decision


def split_mention(
    session: Any,
    creator_mention_id: int,
    *,
    actor: str = "MANUAL",
    notes: str | None = None,
) -> tuple[Author, AuthorIdentityDecision]:
    mention = session.get(PaperCreatorMention, creator_mention_id)
    if mention is None:
        raise IdentityResolutionError("creator mention does not exist")
    current = _accepted_membership(session, creator_mention_id)
    if current is None:
        raise IdentityResolutionError("creator mention has no accepted identity to split")
    old_author = session.get(Author, current.author_id)
    if old_author.locked and actor != "MANUAL":
        raise IdentityResolutionError("locked identities may only be split manually")

    current.status = "SUPERSEDED"
    current.updated_at = utcnow()
    active_authorship = (
        session.query(Authorship)
        .filter_by(creator_mention_id=creator_mention_id, status="ACTIVE")
        .one_or_none()
    )
    if active_authorship is not None:
        active_authorship.status = "SUPERSEDED"
        active_authorship.updated_at = utcnow()
    session.flush()

    new_author, membership = create_author_for_mention(
        session,
        mention,
        actor=actor,
        reason_code="SPLIT_IDENTITY",
    )
    decision = _record_decision(
        session,
        operation="SPLIT_IDENTITY",
        actor=actor,
        mention=mention,
        membership=membership,
        source_author_id=old_author.author_id,
        target_author_id=new_author.author_id,
        previous={"author_id": old_author.author_id},
        result={"author_id": new_author.author_id},
        reason_code="SPLIT_IDENTITY",
        notes=notes,
    )
    session.flush()
    return new_author, decision
