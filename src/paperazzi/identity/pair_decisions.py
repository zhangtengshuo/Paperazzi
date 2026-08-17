"""Manual canonical-author pair decisions used by similar-name review.

`NOT_SAME_PERSON` historically also represents a negative mention→author decision.  For
canonical-author comparison we reuse the existing auditable decision operation with both
source_author_id and target_author_id populated and no creator mention.  Similar-name
candidate generation treats such unordered pairs as a permanent exclusion until a later
explicit identity-history operation changes policy.
"""
from __future__ import annotations

import json
from typing import Any

from .models import Author, AuthorIdentityDecision, ResolutionReviewQueue
from .review import resolve_review_item
from .service import IdentityResolutionError


def canonical_not_same_pairs(session: Any) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    rows = (
        session.query(
            AuthorIdentityDecision.source_author_id,
            AuthorIdentityDecision.target_author_id,
        )
        .filter(
            AuthorIdentityDecision.operation == "NOT_SAME_PERSON",
            AuthorIdentityDecision.creator_mention_id.is_(None),
            AuthorIdentityDecision.source_author_id.is_not(None),
            AuthorIdentityDecision.target_author_id.is_not(None),
        )
        .all()
    )
    for left, right in rows:
        if left != right:
            pairs.add(frozenset((left, right)))
    return pairs


def mark_canonical_authors_not_same(
    session: Any,
    source_author_id: str,
    target_author_id: str,
    *,
    review_item_id: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if source_author_id == target_author_id:
        raise IdentityResolutionError("an author cannot be marked different from itself")
    source = session.get(Author, source_author_id)
    target = session.get(Author, target_author_id)
    if source is None or target is None:
        raise IdentityResolutionError("source or target author does not exist")
    if source.status != "ACTIVE" or target.status != "ACTIVE":
        raise IdentityResolutionError("different-person decisions require two active identities")

    pair = frozenset((source_author_id, target_author_id))
    if pair in canonical_not_same_pairs(session):
        decision = (
            session.query(AuthorIdentityDecision)
            .filter(
                AuthorIdentityDecision.operation == "NOT_SAME_PERSON",
                AuthorIdentityDecision.creator_mention_id.is_(None),
                sa_or_pair(source_author_id, target_author_id),
            )
            .order_by(AuthorIdentityDecision.decision_id.desc())
            .first()
        )
    else:
        decision = AuthorIdentityDecision(
            operation="NOT_SAME_PERSON",
            actor="MANUAL",
            source_author_id=source_author_id,
            target_author_id=target_author_id,
            reason_code="MANUAL_CANONICAL_IDENTITIES_DIFFERENT",
            previous_state_json=json.dumps(
                {"relationship": "UNDECIDED"}, sort_keys=True
            ),
            resulting_state_json=json.dumps(
                {"relationship": "NOT_SAME_PERSON"}, sort_keys=True
            ),
            notes=notes,
        )
        session.add(decision)
        session.flush()

    if review_item_id is not None:
        review = session.get(ResolutionReviewQueue, review_item_id)
        if review is not None and review.status == "OPEN":
            resolve_review_item(session, review_item_id)
    session.flush()
    return {
        "decision_id": decision.decision_id,
        "source_author_id": source_author_id,
        "target_author_id": target_author_id,
        "relationship": "NOT_SAME_PERSON",
    }


def sa_or_pair(left: str, right: str):
    """SQL expression matching either orientation of an unordered canonical pair."""
    import sqlalchemy as sa

    return sa.or_(
        sa.and_(
            AuthorIdentityDecision.source_author_id == left,
            AuthorIdentityDecision.target_author_id == right,
        ),
        sa.and_(
            AuthorIdentityDecision.source_author_id == right,
            AuthorIdentityDecision.target_author_id == left,
        ),
    )
