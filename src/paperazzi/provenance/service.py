"""Document-role selection and provenance-aware retraction services.

Retraction never physically deletes extraction history.  Existing status columns use
``SUPERSEDED``/``REJECTED`` for compatibility; ``RetractionEvent`` and
``RetractionImpact`` distinguish an error withdrawal from ordinary version supersession.
Current projections are recomputed from the remaining accepted evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

from paperazzi.database.base import utcnow
from paperazzi.database.models import (
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionRun,
    PaperDocument,
    PaperReference,
    PaperReferenceMatch,
    PaperReferenceSection,
)
from paperazzi.identity.models import Authorship, AuthorshipEvidence, ResolutionReviewQueue

from .models import DocumentRole, RetractionEvent, RetractionImpact


_SUPPLEMENTARY_RE = re.compile(
    r"(?:^|[\W_])(?:si|esi|supp|suppl|supplement|supplementary|supporting[-_ ]?information|"
    r"supporting[-_ ]?info|electronic[-_ ]?supplementary[-_ ]?information)(?:[\W_]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class EffectiveDocumentRole:
    role: str
    source: str
    confidence: float
    reason_code: str


def classify_document_role(path: str | Path | None) -> EffectiveDocumentRole:
    """Classify a PDF conservatively from its filename without mutating the DB."""
    if not path:
        return EffectiveDocumentRole("UNKNOWN", "HEURISTIC", 0.0, "NO_PATH")
    name = Path(str(path)).name
    stem = Path(name).stem
    if _SUPPLEMENTARY_RE.search(stem):
        return EffectiveDocumentRole(
            "SUPPLEMENTARY", "HEURISTIC", 0.98, "SUPPLEMENTARY_FILENAME_MARKER"
        )
    # A PDF without a supplementary marker is a primary *candidate*.  The modest
    # confidence is deliberate; a MANUAL/LOCAL_AI DocumentRole always overrides it.
    return EffectiveDocumentRole(
        "PRIMARY_ARTICLE", "HEURISTIC", 0.60, "NO_SUPPLEMENTARY_FILENAME_MARKER"
    )


def effective_document_role(session: Any, document: PaperDocument) -> EffectiveDocumentRole:
    stored = session.get(DocumentRole, document.document_id)
    if stored is not None:
        return EffectiveDocumentRole(
            stored.role,
            stored.source,
            float(stored.confidence or 0.0),
            stored.reason_code or "PERSISTED_CLASSIFICATION",
        )
    return classify_document_role(document.local_path)


def select_primary_document(session: Any, paper_id: int) -> PaperDocument | None:
    """Return the best reachable primary PDF, never preferring known SI over an article."""
    documents = (
        session.query(PaperDocument)
        .filter(
            PaperDocument.paper_id == paper_id,
            PaperDocument.present_in_last_scan.is_(True),
            PaperDocument.availability_status == "PDF_AVAILABLE",
            PaperDocument.local_path.is_not(None),
        )
        .order_by(PaperDocument.document_id)
        .all()
    )
    reachable: list[tuple[PaperDocument, EffectiveDocumentRole]] = []
    for document in documents:
        if document.local_path and Path(document.local_path).is_file():
            reachable.append((document, effective_document_role(session, document)))
    if not reachable:
        return None
    role_rank = {"PRIMARY_ARTICLE": 0, "UNKNOWN": 1, "SUPPLEMENTARY": 2}
    reachable.sort(
        key=lambda item: (
            role_rank.get(item[1].role, 1),
            -item[1].confidence,
            item[0].document_id,
        )
    )
    return reachable[0][0]


def _state(**values: Any) -> str:
    return json.dumps(values, sort_keys=True, ensure_ascii=False)


def _impact(
    session: Any,
    event: RetractionEvent,
    *,
    entity_type: str,
    entity_id: Any,
    action: str,
    previous: dict[str, Any],
    resulting: dict[str, Any],
) -> None:
    session.add(
        RetractionImpact(
            retraction_id=event.retraction_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            previous_state_json=_state(**previous),
            resulting_state_json=_state(**resulting),
        )
    )


def _new_event(
    session: Any,
    *,
    root_type: str,
    root_id: Any,
    scope: str,
    reason_code: str,
    reason_text: str | None,
    actor: str,
) -> RetractionEvent:
    event = RetractionEvent(
        root_type=root_type,
        root_id=str(root_id),
        scope=scope,
        reason_code=reason_code,
        reason_text=reason_text,
        actor=actor,
    )
    session.add(event)
    session.flush()
    return event


def _recompute_corresponding(session: Any, authorship_ids: Iterable[int], event: RetractionEvent) -> None:
    for authorship_id in sorted(set(authorship_ids)):
        authorship = session.get(Authorship, authorship_id)
        if authorship is None or authorship.status != "ACTIVE":
            continue
        accepted = (
            session.query(AuthorshipEvidence)
            .filter_by(
                authorship_id=authorship_id,
                evidence_type="CORRESPONDING_AUTHOR",
                status="ACCEPTED",
            )
            .count()
        )
        candidate = (
            session.query(AuthorshipEvidence)
            .filter_by(
                authorship_id=authorship_id,
                evidence_type="CORRESPONDING_AUTHOR",
                status="CANDIDATE",
            )
            .count()
        )
        before = {
            "is_corresponding_author": bool(authorship.is_corresponding_author),
            "corresponding_status": authorship.corresponding_status,
        }
        authorship.is_corresponding_author = accepted > 0
        authorship.corresponding_status = (
            "ACCEPTED" if accepted else "CANDIDATE" if candidate else "UNKNOWN"
        )
        after = {
            "is_corresponding_author": bool(authorship.is_corresponding_author),
            "corresponding_status": authorship.corresponding_status,
        }
        if before != after:
            _impact(
                session,
                event,
                entity_type="AUTHORSHIP",
                entity_id=authorship_id,
                action="RECOMPUTE_PROJECTION",
                previous=before,
                resulting=after,
            )


def _supersede_authorship_evidence(
    session: Any, span_ids: list[int], event: RetractionEvent
) -> set[int]:
    if not span_ids:
        return set()
    rows = (
        session.query(AuthorshipEvidence)
        .filter(
            AuthorshipEvidence.evidence_span_id.in_(span_ids),
            AuthorshipEvidence.status.in_(("CANDIDATE", "ACCEPTED")),
        )
        .all()
    )
    affected: set[int] = set()
    for row in rows:
        old = row.status
        row.status = "SUPERSEDED"
        affected.add(row.authorship_id)
        _impact(
            session,
            event,
            entity_type="AUTHORSHIP_EVIDENCE",
            entity_id=row.authorship_evidence_id,
            action="INVALIDATE",
            previous={"status": old},
            resulting={"status": "SUPERSEDED", "retraction_id": event.retraction_id},
        )
    return affected


def _invalidate_reference_outputs(
    session: Any,
    *,
    event: RetractionEvent,
    document_id: int | None = None,
    attempt_id: int | None = None,
) -> None:
    section_query = session.query(PaperReferenceSection)
    reference_query = session.query(PaperReference)
    if attempt_id is not None:
        section_query = section_query.filter(PaperReferenceSection.attempt_id == attempt_id)
        reference_query = reference_query.filter(PaperReference.originating_attempt_id == attempt_id)
    elif document_id is not None:
        section_query = section_query.filter(PaperReferenceSection.document_id == document_id)
        reference_query = reference_query.filter(PaperReference.document_id == document_id)
    else:
        return

    for section in section_query.filter(
        PaperReferenceSection.acceptance_status.in_(("CANDIDATE", "ACCEPTED"))
    ).all():
        old = section.acceptance_status
        section.acceptance_status = "SUPERSEDED"
        _impact(
            session,
            event,
            entity_type="PAPER_REFERENCE_SECTION",
            entity_id=section.reference_section_id,
            action="INVALIDATE",
            previous={"acceptance_status": old},
            resulting={"acceptance_status": "SUPERSEDED", "retraction_id": event.retraction_id},
        )

    references = reference_query.filter(
        PaperReference.acceptance_status.in_(("CANDIDATE", "ACCEPTED"))
    ).all()
    reference_ids: list[int] = []
    for reference in references:
        reference_ids.append(reference.reference_id)
        old = reference.acceptance_status
        reference.acceptance_status = "SUPERSEDED"
        _impact(
            session,
            event,
            entity_type="PAPER_REFERENCE",
            entity_id=reference.reference_id,
            action="INVALIDATE",
            previous={"acceptance_status": old},
            resulting={"acceptance_status": "SUPERSEDED", "retraction_id": event.retraction_id},
        )
    if reference_ids:
        matches = (
            session.query(PaperReferenceMatch)
            .filter(
                PaperReferenceMatch.reference_id.in_(reference_ids),
                PaperReferenceMatch.status.in_(("CANDIDATE", "ACCEPTED")),
            )
            .all()
        )
        for match in matches:
            old = match.status
            match.status = "REJECTED"
            _impact(
                session,
                event,
                entity_type="PAPER_REFERENCE_MATCH",
                entity_id=match.reference_match_id,
                action="INVALIDATE",
                previous={"status": old},
                resulting={"status": "REJECTED", "retraction_id": event.retraction_id},
            )


def _dismiss_span_reviews(session: Any, span_ids: list[int], event: RetractionEvent) -> None:
    if not span_ids:
        return
    ids = {str(value) for value in span_ids}
    rows = (
        session.query(ResolutionReviewQueue)
        .filter(
            ResolutionReviewQueue.subject_type == "evidence_span",
            ResolutionReviewQueue.status == "OPEN",
        )
        .all()
    )
    for row in rows:
        if row.subject_id not in ids:
            continue
        row.status = "DISMISSED"
        row.resolved_at = utcnow()
        _impact(
            session,
            event,
            entity_type="RESOLUTION_REVIEW_QUEUE",
            entity_id=row.review_item_id,
            action="DISMISS",
            previous={"status": "OPEN"},
            resulting={"status": "DISMISSED", "retraction_id": event.retraction_id},
        )


def retract_document_derivations(
    session: Any,
    document_id: int,
    *,
    reason_code: str,
    reason_text: str | None = None,
    actor: str = "MANUAL",
) -> RetractionEvent:
    """Withdraw paper-level derivations from a document while preserving raw extraction."""
    document = session.get(PaperDocument, document_id)
    if document is None:
        raise KeyError(f"document_id={document_id} does not exist")
    event = _new_event(
        session,
        root_type="DOCUMENT",
        root_id=document_id,
        scope="PAPER_LEVEL_DERIVATIONS",
        reason_code=reason_code,
        reason_text=reason_text,
        actor=actor,
    )
    span_ids = [
        value
        for (value,) in session.query(DocumentEvidenceSpan.evidence_span_id)
        .filter(DocumentEvidenceSpan.document_id == document_id)
        .all()
    ]
    affected = _supersede_authorship_evidence(session, span_ids, event)
    _invalidate_reference_outputs(session, event=event, document_id=document_id)
    _dismiss_span_reviews(session, span_ids, event)
    _recompute_corresponding(session, affected, event)
    session.flush()
    return event


def retract_extraction_attempt(
    session: Any,
    attempt_id: int,
    *,
    reason_code: str,
    reason_text: str | None = None,
    actor: str = "MANUAL",
) -> RetractionEvent:
    """Withdraw one bad parse attempt and every currently-live derivation from it."""
    attempt = session.get(DocumentExtractionAttempt, attempt_id)
    if attempt is None:
        raise KeyError(f"attempt_id={attempt_id} does not exist")
    event = _new_event(
        session,
        root_type="EXTRACTION_ATTEMPT",
        root_id=attempt_id,
        scope="ALL_DERIVED_OUTPUTS",
        reason_code=reason_code,
        reason_text=reason_text,
        actor=actor,
    )
    spans = (
        session.query(DocumentEvidenceSpan)
        .filter(DocumentEvidenceSpan.attempt_id == attempt_id)
        .all()
    )
    span_ids = [row.evidence_span_id for row in spans]
    affected = _supersede_authorship_evidence(session, span_ids, event)
    for span in spans:
        if span.acceptance_status not in ("CANDIDATE", "ACCEPTED"):
            continue
        old = span.acceptance_status
        span.acceptance_status = "SUPERSEDED"
        _impact(
            session,
            event,
            entity_type="DOCUMENT_EVIDENCE_SPAN",
            entity_id=span.evidence_span_id,
            action="INVALIDATE",
            previous={"acceptance_status": old},
            resulting={"acceptance_status": "SUPERSEDED", "retraction_id": event.retraction_id},
        )
    _invalidate_reference_outputs(session, event=event, attempt_id=attempt_id)
    _dismiss_span_reviews(session, span_ids, event)
    _recompute_corresponding(session, affected, event)

    run = session.get(DocumentExtractionRun, attempt.extraction_run_id)
    if run is not None and run.accepted_attempt_id == attempt_id:
        before = {"accepted_attempt_id": run.accepted_attempt_id, "final_status": run.final_status}
        run.accepted_attempt_id = None
        run.final_status = "UNRESOLVED"
        _impact(
            session,
            event,
            entity_type="DOCUMENT_EXTRACTION_RUN",
            entity_id=run.extraction_run_id,
            action="RECOMPUTE_PROJECTION",
            previous=before,
            resulting={"accepted_attempt_id": None, "final_status": "UNRESOLVED"},
        )
    session.flush()
    return event


def set_document_role(
    session: Any,
    document_id: int,
    role: str,
    *,
    source: str = "MANUAL",
    confidence: float = 1.0,
    reason_code: str,
    notes: str | None = None,
    actor: str = "MANUAL",
    retract_if_supplementary: bool = True,
) -> DocumentRole:
    """Persist a document role; newly marking SI withdraws its paper-level derivations."""
    if role not in {"PRIMARY_ARTICLE", "SUPPLEMENTARY", "UNKNOWN"}:
        raise ValueError(f"invalid document role: {role}")
    if source not in {"HEURISTIC", "LOCAL_AI", "MANUAL"}:
        raise ValueError(f"invalid document role source: {source}")
    document = session.get(PaperDocument, document_id)
    if document is None:
        raise KeyError(f"document_id={document_id} does not exist")
    row = session.get(DocumentRole, document_id)
    previous_role = None if row is None else row.role
    if row is None:
        row = DocumentRole(document_id=document_id, role=role, source=source)
        session.add(row)
    row.role = role
    row.source = source
    row.confidence = confidence
    row.reason_code = reason_code
    row.notes = notes
    row.updated_at = utcnow()
    session.flush()
    if (
        retract_if_supplementary
        and role == "SUPPLEMENTARY"
        and previous_role != "SUPPLEMENTARY"
    ):
        retract_document_derivations(
            session,
            document_id,
            reason_code="DOCUMENT_RECLASSIFIED_AS_SUPPLEMENTARY",
            reason_text=notes or reason_code,
            actor=actor,
        )
    return row
