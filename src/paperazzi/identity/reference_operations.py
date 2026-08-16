"""Explicit AI/manual reference-match decisions for Phase 4.

These operations never consume unaccepted raw references and never write CITES edges.
Reviewed decisions are appended as new accepted rows; deterministic candidate rows are
retained and rejected rather than overwritten, preserving resolver history.
"""

from __future__ import annotations

from typing import Any

from paperazzi.database.models import Paper, PaperReference, PaperReferenceMatch

from .models import ReferenceMatchEvidence
from .review import resolve_review_item


class ReferenceResolutionError(RuntimeError):
    pass


def accept_reviewed_reference_match(
    session: Any,
    reference_id: int,
    cited_paper_id: int,
    *,
    actor: str,
    resolver_version: str,
    notes: str | None = None,
    score: float | None = None,
) -> PaperReferenceMatch:
    if actor not in {"LOCAL_AI", "MANUAL"}:
        raise ReferenceResolutionError(
            "reviewed reference decisions require LOCAL_AI or MANUAL actor"
        )
    reference = session.get(PaperReference, reference_id)
    target = session.get(Paper, cited_paper_id)
    if reference is None or target is None:
        raise ReferenceResolutionError("reference or target paper does not exist")
    if reference.acceptance_status != "ACCEPTED":
        raise ReferenceResolutionError("only ACCEPTED paper_reference rows may be resolved")
    if reference.citing_paper_id == cited_paper_id:
        raise ReferenceResolutionError("citation self-match is forbidden")

    current = (
        session.query(PaperReferenceMatch)
        .filter_by(reference_id=reference_id, status="ACCEPTED")
        .one_or_none()
    )
    if current is not None and current.cited_paper_id == cited_paper_id:
        return current
    if current is not None:
        current.status = "REJECTED"
        session.add(
            ReferenceMatchEvidence(
                reference_match_id=current.reference_match_id,
                component="reviewed_supersession",
                score=0.0,
                value=notes,
                contradiction=True,
            )
        )
        session.flush()

    # All deterministic/earlier candidates remain as history but cease being active.
    session.query(PaperReferenceMatch).filter(
        PaperReferenceMatch.reference_id == reference_id,
        PaperReferenceMatch.status == "CANDIDATE",
    ).update({"status": "REJECTED"})
    session.flush()

    resolver = f"{actor}:{resolver_version}"
    row = PaperReferenceMatch(
        reference_id=reference_id,
        cited_paper_id=cited_paper_id,
        match_type="AI_RESOLVED" if actor == "LOCAL_AI" else "BIBLIOGRAPHIC_COMPOSITE",
        match_score=score,
        status="ACCEPTED",
        resolver=resolver,
    )
    session.add(row)
    session.flush()
    session.add(
        ReferenceMatchEvidence(
            reference_match_id=row.reference_match_id,
            component="reviewed_resolution",
            score=score,
            value=notes,
            contradiction=False,
        )
    )
    session.flush()
    return row


def reject_reference_match(
    session: Any,
    reference_match_id: int,
    *,
    actor: str,
    resolver_version: str,
    notes: str | None = None,
) -> PaperReferenceMatch:
    if actor not in {"LOCAL_AI", "MANUAL"}:
        raise ReferenceResolutionError("rejection requires LOCAL_AI or MANUAL actor")
    row = session.get(PaperReferenceMatch, reference_match_id)
    if row is None:
        raise ReferenceResolutionError("reference match does not exist")
    row.status = "REJECTED"
    row.resolver = f"{actor}:{resolver_version}"
    session.add(
        ReferenceMatchEvidence(
            reference_match_id=row.reference_match_id,
            component="reviewed_rejection",
            score=0.0,
            value=notes,
            contradiction=True,
        )
    )
    session.flush()
    return row


def resolve_reference_review_queue_item(
    session: Any,
    review_item_id: int,
    reference_id: int,
    cited_paper_id: int,
    *,
    actor: str,
    resolver_version: str,
    notes: str | None = None,
    score: float | None = None,
) -> PaperReferenceMatch:
    row = accept_reviewed_reference_match(
        session,
        reference_id,
        cited_paper_id,
        actor=actor,
        resolver_version=resolver_version,
        notes=notes,
        score=score,
    )
    resolve_review_item(session, review_item_id)
    return row
