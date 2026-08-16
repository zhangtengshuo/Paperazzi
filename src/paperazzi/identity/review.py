"""Deterministic review-queue helpers for unresolved Phase 4 decisions."""

from __future__ import annotations

import json
from typing import Any

from paperazzi.database.base import utcnow

from .models import ResolutionReviewQueue


QUEUE_TYPES = {
    "AMBIGUOUS_AUTHOR_IDENTITY",
    "IDENTITY_CONFLICT",
    "UNRESOLVED_CORRESPONDING_AUTHOR",
    "AMBIGUOUS_REFERENCE_MATCH",
    "REFERENCE_CONTRADICTION",
    "UNRESOLVED_REFERENCE",
}


def enqueue_review(
    session: Any,
    *,
    queue_type: str,
    subject_type: str,
    subject_id: str | int,
    candidate_id: str | int | None = None,
    reason_code: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: int = 50,
) -> ResolutionReviewQueue:
    if queue_type not in QUEUE_TYPES:
        raise ValueError(f"unsupported review queue type: {queue_type}")
    subject_id_text = str(subject_id)
    row = (
        session.query(ResolutionReviewQueue)
        .filter_by(
            queue_type=queue_type,
            subject_type=subject_type,
            subject_id=subject_id_text,
            status="OPEN",
        )
        .one_or_none()
    )
    if row is None:
        row = ResolutionReviewQueue(
            queue_type=queue_type,
            subject_type=subject_type,
            subject_id=subject_id_text,
            candidate_id=None if candidate_id is None else str(candidate_id),
            priority=priority,
            status="OPEN",
            reason_code=reason_code,
            payload_json=json.dumps(payload or {}, sort_keys=True, ensure_ascii=False),
        )
        session.add(row)
    else:
        row.candidate_id = None if candidate_id is None else str(candidate_id)
        row.priority = priority
        row.reason_code = reason_code
        row.payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
    session.flush()
    return row


def resolve_review_item(session: Any, review_item_id: int, *, dismissed: bool = False) -> None:
    row = session.get(ResolutionReviewQueue, review_item_id)
    if row is None:
        raise KeyError(f"review_item_id={review_item_id} does not exist")
    row.status = "DISMISSED" if dismissed else "RESOLVED"
    row.resolved_at = utcnow()
    session.flush()


def open_review_counts(session: Any) -> dict[str, int]:
    rows = (
        session.query(ResolutionReviewQueue.queue_type, __import__("sqlalchemy").func.count())
        .filter_by(status="OPEN")
        .group_by(ResolutionReviewQueue.queue_type)
        .all()
    )
    return {queue_type: int(count) for queue_type, count in rows}
