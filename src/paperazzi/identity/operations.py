"""Explicit reversible/manual identity operations for Phase 4."""

from __future__ import annotations

import json
from typing import Any

from paperazzi.database.base import utcnow
from paperazzi.database.models import PaperCreatorMention

from .models import (
    Author,
    AuthorExternalID,
    AuthorIdentityEvidence,
    AuthorIdentityMembership,
    Authorship,
)
from .review import enqueue_review
from .service import (
    IdentityResolutionError,
    RESOLVER_VERSION,
    _accepted_membership,
    _record_decision,
)


def unlink_mention(
    session: Any,
    creator_mention_id: int,
    *,
    actor: str = "MANUAL",
    notes: str | None = None,
) -> None:
    mention = session.get(PaperCreatorMention, creator_mention_id)
    if mention is None:
        raise IdentityResolutionError("creator mention does not exist")
    membership = _accepted_membership(session, creator_mention_id)
    if membership is None:
        return
    author = session.get(Author, membership.author_id)
    if author.locked and actor != "MANUAL":
        raise IdentityResolutionError("locked identities may only be modified manually")
    membership.status = "SUPERSEDED"
    membership.updated_at = utcnow()
    active = (
        session.query(Authorship)
        .filter_by(creator_mention_id=creator_mention_id, status="ACTIVE")
        .one_or_none()
    )
    if active is not None:
        active.status = "SUPERSEDED"
        active.updated_at = utcnow()
    session.flush()
    _record_decision(
        session,
        operation="UNLINK_MENTION",
        actor=actor,
        mention=mention,
        membership=membership,
        source_author_id=author.author_id,
        previous={"membership_status": "ACCEPTED"},
        result={"membership_status": "SUPERSEDED"},
        reason_code="EXPLICIT_UNLINK",
        notes=notes,
    )


def mark_not_same_person(
    session: Any,
    creator_mention_id: int,
    author_id: str,
    *,
    actor: str = "MANUAL",
    notes: str | None = None,
) -> AuthorIdentityMembership:
    mention = session.get(PaperCreatorMention, creator_mention_id)
    author = session.get(Author, author_id)
    if mention is None or author is None:
        raise IdentityResolutionError("mention or author does not exist")
    if author.locked and actor != "MANUAL":
        raise IdentityResolutionError("locked identities may only be modified manually")

    accepted = _accepted_membership(session, creator_mention_id)
    if accepted is not None and accepted.author_id == author_id:
        unlink_mention(session, creator_mention_id, actor=actor, notes=notes)

    candidate = (
        session.query(AuthorIdentityMembership)
        .filter_by(
            creator_mention_id=creator_mention_id,
            author_id=author_id,
            status="CANDIDATE",
        )
        .order_by(AuthorIdentityMembership.membership_id.desc())
        .first()
    )
    if candidate is None:
        candidate = AuthorIdentityMembership(
            creator_mention_id=creator_mention_id,
            author_id=author_id,
            status="REJECTED",
            resolver="manual" if actor == "MANUAL" else RESOLVER_VERSION,
            score=0.0,
            score_components_json=json.dumps({"explicit_not_same": -1.0}),
            reason_code="NOT_SAME_PERSON",
        )
        session.add(candidate)
    else:
        candidate.status = "REJECTED"
        candidate.score = 0.0
        candidate.score_components_json = json.dumps({"explicit_not_same": -1.0})
        candidate.reason_code = "NOT_SAME_PERSON"
        candidate.updated_at = utcnow()
    session.flush()
    session.add(
        AuthorIdentityEvidence(
            membership_id=candidate.membership_id,
            creator_mention_id=creator_mention_id,
            candidate_author_id=author_id,
            evidence_type="manual_not_same_person",
            polarity="CONFLICT",
            score=-1.0,
            source_kind="MANUAL" if actor == "MANUAL" else "LOCAL_AI",
            payload_json=json.dumps({"notes": notes}, ensure_ascii=False),
        )
    )
    _record_decision(
        session,
        operation="NOT_SAME_PERSON",
        actor=actor,
        mention=mention,
        membership=candidate,
        target_author_id=author_id,
        result={"membership_status": "REJECTED"},
        reason_code="NOT_SAME_PERSON",
        notes=notes,
    )
    session.flush()
    return candidate


def set_identity_lock(
    session: Any,
    author_id: str,
    locked: bool,
    *,
    actor: str = "MANUAL",
    notes: str | None = None,
) -> Author:
    if actor != "MANUAL":
        raise IdentityResolutionError("identity lock/unlock is a manual authority operation")
    author = session.get(Author, author_id)
    if author is None:
        raise IdentityResolutionError("author does not exist")
    previous = author.locked
    author.locked = locked
    author.updated_at = utcnow()
    _record_decision(
        session,
        operation="LOCK_IDENTITY" if locked else "UNLOCK_IDENTITY",
        actor=actor,
        target_author_id=author_id,
        previous={"locked": previous},
        result={"locked": locked},
        reason_code="MANUAL_IDENTITY_LOCK",
        notes=notes,
    )
    session.flush()
    return author


def normalize_external_id(namespace: str, value: str) -> str:
    namespace = namespace.strip().upper()
    normalized = value.strip()
    if namespace == "ORCID":
        for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid:"):
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        normalized = normalized.upper()
    return normalized


def add_external_id(
    session: Any,
    author_id: str,
    namespace: str,
    value: str,
    *,
    source: str,
    status: str = "ACCEPTED",
) -> AuthorExternalID:
    author = session.get(Author, author_id)
    if author is None:
        raise IdentityResolutionError("author does not exist")
    namespace_norm = namespace.strip().upper()
    value_norm = normalize_external_id(namespace_norm, value)

    if status == "ACCEPTED":
        conflict = (
            session.query(AuthorExternalID)
            .filter_by(
                namespace=namespace_norm,
                normalized_value=value_norm,
                status="ACCEPTED",
            )
            .filter(AuthorExternalID.author_id != author_id)
            .first()
        )
        if conflict is not None:
            enqueue_review(
                session,
                queue_type="IDENTITY_CONFLICT",
                subject_type="author",
                subject_id=author_id,
                candidate_id=conflict.author_id,
                reason_code="EXTERNAL_ID_CONFLICT",
                payload={"namespace": namespace_norm, "value": value_norm},
                priority=100,
            )
            raise IdentityResolutionError(
                f"{namespace_norm} {value_norm} already belongs to another accepted author"
            )

    existing = (
        session.query(AuthorExternalID)
        .filter_by(
            author_id=author_id,
            namespace=namespace_norm,
            normalized_value=value_norm,
            status=status,
        )
        .first()
    )
    if existing is not None:
        return existing
    row = AuthorExternalID(
        author_id=author_id,
        namespace=namespace_norm,
        raw_value=value,
        normalized_value=value_norm,
        source=source,
        status=status,
    )
    session.add(row)
    session.flush()
    return row
