"""Phase 3C/3.1 — document extraction, review, evidence and reference persistence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from .base import utcnow
from .models import (
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionReview,
    DocumentExtractionRun,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
)

EXTRACTOR_VERSION = "deterministic-v3"
PROMPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "prompts"
    / "local_ai"
    / "PDF_EVIDENCE_AGENT.md"
)
PROMPT_VERSION = "PDF_EVIDENCE_AGENT.md"


def prompt_content_hash(path: str | Path = PROMPT_PATH) -> str:
    prompt_path = Path(path)
    return hashlib.sha256(prompt_path.read_bytes()).hexdigest()


PROMPT_HASH = prompt_content_hash()


class ExtractionError(RuntimeError):
    pass


def raw_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deterministic_reference_quality(section: Any | None) -> tuple[str | None, str | None, str]:
    """Return section confidence, segmentation confidence and initial entry quality."""
    if section is None:
        return None, None, "UNREVIEWED"
    if section.heading:
        section_confidence = "HIGH"
    else:
        section_confidence = section.confidence
    segmentation_confidence = section.confidence if section.entries else None
    return section_confidence, segmentation_confidence, "UNREVIEWED"


def decide_extraction_trigger(
    document: PaperDocument,
    document_change_key: str | None,
    extractor_version: str,
    prompt_hash: str,
) -> str | None:
    """Return the trigger for a new extraction run, or None if none is needed."""
    if document.availability_status != "PDF_AVAILABLE":
        return None

    session = sa.inspect(document).session
    if session is None:
        raise ExtractionError("PaperDocument must be attached to a session")

    pending = (
        session.query(DocumentExtractionRun)
        .filter_by(document_id=document.document_id, status="STARTED")
        .order_by(DocumentExtractionRun.extraction_run_id.desc())
        .first()
    )
    if pending is not None:
        return None

    if document.current_extraction_run_id is None:
        return "FIRST_AVAILABLE"

    run = (
        session.query(DocumentExtractionRun)
        .filter_by(extraction_run_id=document.current_extraction_run_id)
        .one()
    )
    if run.document_change_key != document_change_key and document_change_key is not None:
        return "FILE_CHANGED"
    if run.extractor_version != extractor_version:
        return "EXTRACTOR_CHANGED"
    if run.prompt_hash != prompt_hash:
        return "PROMPT_CHANGED"
    return None


def create_extraction_run(
    session: Any,
    document_id: int,
    trigger: str,
    document_change_key: str | None,
    *,
    extractor_version: str = EXTRACTOR_VERSION,
    prompt_version: str = PROMPT_VERSION,
    prompt_hash: str = PROMPT_HASH,
) -> DocumentExtractionRun:
    active = (
        session.query(DocumentExtractionRun)
        .filter_by(document_id=document_id, status="STARTED")
        .first()
    )
    if active is not None:
        raise ExtractionError(
            f"document_id={document_id} already has STARTED extraction_run_id="
            f"{active.extraction_run_id}"
        )
    run = DocumentExtractionRun(
        document_id=document_id,
        trigger=trigger,
        status="STARTED",
        document_change_key=document_change_key,
        extractor_version=extractor_version,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        started_at=utcnow(),
    )
    session.add(run)
    session.flush()
    return run


def _latest_review(
    session: Any, attempt: DocumentExtractionAttempt
) -> DocumentExtractionReview | None:
    return (
        session.query(DocumentExtractionReview)
        .filter_by(attempt_id=attempt.attempt_id)
        .order_by(DocumentExtractionReview.review_id.desc())
        .first()
    )


def add_extraction_attempt(
    session: Any,
    run: DocumentExtractionRun,
    *,
    attempt_number: int,
    actor: str,
    strategy: str,
    text_source: str,
    decision: str = "REVIEW_PENDING",
    strategy_parameters: dict[str, Any] | None = None,
    backend: str | None = None,
    backend_version: str | None = None,
    text_channel: str | None = None,
    channels_evaluated: list[str] | None = None,
    problem_codes: list[str] | None = None,
    section_confidence: str | None = None,
    segmentation_confidence: str | None = None,
    entry_text_quality: str | None = "UNREVIEWED",
    front_matter_status: str | None = None,
    reference_status: str | None = None,
    output_hash: str | None = None,
    quality_notes: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    prompt_hash: str = PROMPT_HASH,
) -> DocumentExtractionAttempt:
    if not 1 <= attempt_number <= 3:
        raise ExtractionError(f"attempt_number must be 1..3, got {attempt_number}")
    if decision != "REVIEW_PENDING":
        raise ExtractionError(
            "new extraction attempts must start as REVIEW_PENDING; "
            "record a review before assigning PASS/ACCEPT_PARTIAL/RETRY"
        )
    if run.status != "STARTED":
        raise ExtractionError("cannot add an attempt to a non-STARTED extraction run")
    if attempt_number > 1:
        previous = (
            session.query(DocumentExtractionAttempt)
            .filter_by(
                extraction_run_id=run.extraction_run_id,
                attempt_number=attempt_number - 1,
            )
            .one_or_none()
        )
        if previous is None:
            raise ExtractionError(
                f"Attempt {attempt_number} requires Attempt {attempt_number - 1}"
            )
        previous_review = _latest_review(session, previous)
        if previous_review is None or previous_review.decision != "RETRY":
            raise ExtractionError(
                f"Attempt {attempt_number} requires Attempt {attempt_number - 1} "
                "to have latest review decision RETRY"
            )

    attempt = DocumentExtractionAttempt(
        extraction_run_id=run.extraction_run_id,
        attempt_number=attempt_number,
        actor=actor,
        strategy=strategy,
        strategy_parameters_json=json.dumps(strategy_parameters or {}, sort_keys=True),
        backend=backend,
        backend_version=backend_version,
        text_source=text_source,
        text_channel=text_channel,
        channels_evaluated_json=json.dumps(channels_evaluated or []),
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        decision=decision,
        problem_codes_json=json.dumps(problem_codes or []),
        section_confidence=section_confidence,
        segmentation_confidence=segmentation_confidence,
        entry_text_quality=entry_text_quality,
        front_matter_status=front_matter_status,
        reference_status=reference_status,
        output_hash=output_hash,
        quality_notes=quality_notes,
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(attempt)
    session.flush()
    return attempt


def record_extraction_review(
    session: Any,
    attempt: DocumentExtractionAttempt,
    *,
    reviewer_type: str,
    decision: str,
    problem_codes: list[str] | None = None,
    quality_notes: str | None = None,
    section_confidence: str | None = None,
    segmentation_confidence: str | None = None,
    entry_text_quality: str | None = None,
    review_output_hash: str | None = None,
    reviewer_runtime: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    prompt_hash: str = PROMPT_HASH,
) -> DocumentExtractionReview:
    if reviewer_type not in ("LOCAL_AI", "MANUAL"):
        raise ExtractionError(f"invalid reviewer_type={reviewer_type}")
    if decision not in ("PASS", "ACCEPT_PARTIAL", "RETRY", "UNRESOLVED", "NEEDS_OCR"):
        raise ExtractionError(f"invalid review decision={decision}")
    if attempt.attempt_number == 3 and decision == "RETRY":
        raise ExtractionError(
            "Attempt 3 is the final allowed attempt; its review must be terminal "
            "(PASS/ACCEPT_PARTIAL/UNRESOLVED/NEEDS_OCR)"
        )
    review = DocumentExtractionReview(
        attempt_id=attempt.attempt_id,
        reviewer_type=reviewer_type,
        prompt_version=prompt_version if reviewer_type == "LOCAL_AI" else None,
        prompt_hash=prompt_hash if reviewer_type == "LOCAL_AI" else None,
        reviewer_runtime=reviewer_runtime,
        decision=decision,
        problem_codes_json=json.dumps(problem_codes or []),
        quality_notes=quality_notes,
        section_confidence=section_confidence,
        segmentation_confidence=segmentation_confidence,
        entry_text_quality=entry_text_quality,
        review_output_hash=review_output_hash,
        reviewed_at=utcnow(),
    )
    session.add(review)
    attempt.decision = decision
    session.flush()
    return review


def persist_evidence_spans(
    session: Any,
    document_id: int,
    attempt: DocumentExtractionAttempt,
    spans: list[dict[str, Any]],
    *,
    acceptance_status: str = "CANDIDATE",
    text_source: str = "PDF_NATIVE",
    text_channel: str | None = None,
) -> int:
    count = 0
    for span in spans:
        raw = span.get("text") or ""
        if not raw:
            continue
        session.add(
            DocumentEvidenceSpan(
                document_id=document_id,
                attempt_id=attempt.attempt_id,
                kind=span.get("kind", "unknown"),
                page_start=span.get("page_index", 0),
                page_end=span.get("page_end"),
                bbox_json=json.dumps(span["bbox"]) if span.get("bbox") else None,
                raw_text=raw,
                raw_text_hash=raw_text_hash(raw),
                text_source=text_source,
                text_channel=text_channel,
                acceptance_status=acceptance_status,
            )
        )
        count += 1
    return count


def persist_reference_section(
    session: Any,
    paper_id: int,
    document_id: int,
    attempt: DocumentExtractionAttempt,
    section: Any,
    *,
    acceptance_status: str = "CANDIDATE",
    text_source: str = "PDF_NATIVE",
) -> PaperReferenceSection:
    """Persist a deterministic reference section as candidate evidence."""
    section_confidence, segmentation_confidence, entry_text_quality = (
        deterministic_reference_quality(section)
    )
    row = PaperReferenceSection(
        paper_id=paper_id,
        document_id=document_id,
        attempt_id=attempt.attempt_id,
        heading=section.heading or None,
        is_explicit_heading=bool(section.heading),
        start_page=section.start_page,
        end_page=section.end_page,
        parse_method=section.method,
        section_confidence=section_confidence,
        segmentation_confidence=segmentation_confidence,
        entry_text_quality=entry_text_quality,
        text_source=text_source,
        text_channel=section.text_channel,
        acceptance_status=acceptance_status,
        raw_text=section.raw_text,
        raw_text_hash=raw_text_hash(section.raw_text),
    )
    session.add(row)
    session.flush()

    for entry in section.entries:
        entry_row = PaperReference(
            citing_paper_id=paper_id,
            reference_section_id=row.reference_section_id,
            document_id=document_id,
            originating_attempt_id=attempt.attempt_id,
            ordinal=entry.ordinal,
            raw_text=entry.raw_text,
            raw_text_hash=raw_text_hash(entry.raw_text),
            acceptance_status=acceptance_status,
        )
        session.add(entry_row)
        session.flush()
        for doi in entry.dois:
            session.add(
                PaperReferenceIdentifier(
                    reference_id=entry_row.reference_id,
                    identifier_type="DOI",
                    identifier_value=doi,
                    normalized_value=doi.lower(),
                    extractor=EXTRACTOR_VERSION,
                )
            )
        for year in entry.years:
            session.add(
                PaperReferenceIdentifier(
                    reference_id=entry_row.reference_id,
                    identifier_type="YEAR",
                    identifier_value=year,
                    normalized_value=year,
                    extractor=EXTRACTOR_VERSION,
                )
            )
    return row


def _supersede_earlier_attempt_outputs(
    session: Any,
    run: DocumentExtractionRun,
    attempt: DocumentExtractionAttempt,
    superseded_status: str,
) -> None:
    earlier = (
        session.query(DocumentExtractionAttempt)
        .filter(
            DocumentExtractionAttempt.extraction_run_id == run.extraction_run_id,
            DocumentExtractionAttempt.attempt_number < attempt.attempt_number,
        )
        .all()
    )
    for prev in earlier:
        session.query(DocumentEvidenceSpan).filter(
            DocumentEvidenceSpan.attempt_id == prev.attempt_id,
            DocumentEvidenceSpan.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
        ).update({"acceptance_status": superseded_status})
        session.query(PaperReferenceSection).filter(
            PaperReferenceSection.attempt_id == prev.attempt_id,
            PaperReferenceSection.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
        ).update({"acceptance_status": superseded_status})
        session.query(PaperReference).filter(
            PaperReference.originating_attempt_id == prev.attempt_id,
            PaperReference.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
        ).update({"acceptance_status": superseded_status})


def accept_attempt(
    session: Any,
    run: DocumentExtractionRun,
    attempt: DocumentExtractionAttempt,
    final_status: str | None = None,
    *,
    evidence_status: str = "ACCEPTED",
    reference_status: str = "ACCEPTED",
    superseded_status: str = "SUPERSEDED",
) -> None:
    """Accept a reviewed PASS/ACCEPT_PARTIAL attempt."""
    review = _latest_review(session, attempt)
    if review is None:
        raise ExtractionError(
            f"attempt_id={attempt.attempt_id} has no AI/manual review; cannot accept"
        )
    if review.decision not in ("PASS", "ACCEPT_PARTIAL"):
        raise ExtractionError(
            f"review decision {review.decision} is terminal-but-unaccepted or retry; "
            "only PASS/ACCEPT_PARTIAL may accept evidence"
        )
    if attempt.extraction_run_id != run.extraction_run_id:
        raise ExtractionError("attempt does not belong to extraction run")
    if final_status is not None and final_status != review.decision:
        raise ExtractionError(
            f"final_status={final_status} contradicts latest review decision={review.decision}"
        )

    run.status = "COMPLETED"
    run.completed_at = utcnow()
    run.final_status = review.decision
    run.accepted_attempt_id = attempt.attempt_id

    if review.entry_text_quality is not None:
        attempt.entry_text_quality = review.entry_text_quality

    section_updates: dict[str, Any] = {"acceptance_status": reference_status}
    if review.section_confidence is not None:
        section_updates["section_confidence"] = review.section_confidence
    if review.segmentation_confidence is not None:
        section_updates["segmentation_confidence"] = review.segmentation_confidence
    if review.entry_text_quality is not None:
        section_updates["entry_text_quality"] = review.entry_text_quality

    session.query(DocumentEvidenceSpan).filter(
        DocumentEvidenceSpan.attempt_id == attempt.attempt_id,
        DocumentEvidenceSpan.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update({"acceptance_status": evidence_status})
    session.query(PaperReferenceSection).filter(
        PaperReferenceSection.attempt_id == attempt.attempt_id,
        PaperReferenceSection.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update(section_updates)
    session.query(PaperReference).filter(
        PaperReference.originating_attempt_id == attempt.attempt_id,
        PaperReference.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update({"acceptance_status": reference_status})

    _supersede_earlier_attempt_outputs(session, run, attempt, superseded_status)
    session.query(PaperDocument).filter_by(document_id=run.document_id).update(
        {"current_extraction_run_id": run.extraction_run_id, "updated_at": utcnow()}
    )


def finalize_unaccepted_attempt(
    session: Any,
    run: DocumentExtractionRun,
    attempt: DocumentExtractionAttempt,
    *,
    rejected_status: str = "REJECTED",
    superseded_status: str = "SUPERSEDED",
) -> None:
    """Complete NEEDS_OCR/UNRESOLVED without promoting candidate evidence."""
    review = _latest_review(session, attempt)
    if review is None:
        raise ExtractionError("cannot finalize an unreviewed attempt")
    if review.decision not in ("NEEDS_OCR", "UNRESOLVED"):
        raise ExtractionError(
            "finalize_unaccepted_attempt only accepts NEEDS_OCR/UNRESOLVED reviews"
        )
    if attempt.extraction_run_id != run.extraction_run_id:
        raise ExtractionError("attempt does not belong to extraction run")

    run.status = "COMPLETED"
    run.completed_at = utcnow()
    run.final_status = review.decision
    run.accepted_attempt_id = None

    session.query(DocumentEvidenceSpan).filter(
        DocumentEvidenceSpan.attempt_id == attempt.attempt_id,
        DocumentEvidenceSpan.acceptance_status == "CANDIDATE",
    ).update({"acceptance_status": rejected_status})
    session.query(PaperReferenceSection).filter(
        PaperReferenceSection.attempt_id == attempt.attempt_id,
        PaperReferenceSection.acceptance_status == "CANDIDATE",
    ).update({"acceptance_status": rejected_status})
    session.query(PaperReference).filter(
        PaperReference.originating_attempt_id == attempt.attempt_id,
        PaperReference.acceptance_status == "CANDIDATE",
    ).update({"acceptance_status": rejected_status})

    _supersede_earlier_attempt_outputs(session, run, attempt, superseded_status)
