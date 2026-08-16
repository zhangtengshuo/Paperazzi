"""Phase 3C — document extraction / evidence / reference persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa

from .base import utcnow
from .models import (
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionRun,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
)

EXTRACTOR_VERSION = "deterministic-v3"
PROMPT_VERSION = "PDF_EVIDENCE_AGENT.md@bb7cb47"
PROMPT_HASH = hashlib.sha256(PROMPT_VERSION.encode()).hexdigest()[:16]


class ExtractionError(RuntimeError):
    pass


def raw_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decide_extraction_trigger(
    document: PaperDocument,
    document_change_key: str | None,
    extractor_version: str,
    prompt_hash: str,
) -> str | None:
    """Return the trigger for a new extraction run, or None if no re-extraction needed.

    Re-extraction triggers: first local availability, file/document change-key
    change, extractor version change, prompt version/hash change, or manual rebuild.
    """
    if document.availability_status == "PDF_AVAILABLE":
        if document.current_extraction_run_id is None:
            return "FIRST_AVAILABLE"
        run = (
            sa.inspect(document).session.query(DocumentExtractionRun)
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


def add_extraction_attempt(
    session: Any,
    run: DocumentExtractionRun,
    *,
    attempt_number: int,
    actor: str,
    strategy: str,
    text_source: str,
    decision: str,
    strategy_parameters: dict[str, Any] | None = None,
    backend: str | None = None,
    backend_version: str | None = None,
    text_channel: str | None = None,
    channels_evaluated: list[str] | None = None,
    problem_codes: list[str] | None = None,
    section_confidence: str | None = None,
    segmentation_confidence: str | None = None,
    entry_text_quality: str | None = None,
    front_matter_status: str | None = None,
    reference_status: str | None = None,
    output_hash: str | None = None,
    quality_notes: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    prompt_hash: str = PROMPT_HASH,
) -> DocumentExtractionAttempt:
    if not 1 <= attempt_number <= 3:
        raise ExtractionError(f"attempt_number must be 1..3, got {attempt_number}")
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
    acceptance_status: str = "ACCEPTED",
    text_source: str = "PDF_NATIVE",
) -> PaperReferenceSection:
    """Persist a reference section and its segmented entries/identifiers."""
    row = PaperReferenceSection(
        paper_id=paper_id,
        document_id=document_id,
        attempt_id=attempt.attempt_id,
        heading=section.heading or None,
        is_explicit_heading=bool(section.heading),
        start_page=section.start_page,
        end_page=section.end_page,
        parse_method=section.method,
        section_confidence=section.confidence,
        segmentation_confidence=section.confidence,
        entry_text_quality=attempt.entry_text_quality,
        text_source=text_source,
        text_channel=section.text_channel,
        acceptance_status=acceptance_status,
        raw_text=section.raw_text,
        raw_text_hash=raw_text_hash(section.raw_text),
    )
    session.add(row)
    session.flush()

    entry_count = 0
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
        entry_count += 1
        for doi in entry.dois:
            session.add(
                PaperReferenceIdentifier(
                    reference_id=entry_row.reference_id,
                    identifier_type="DOI",
                    identifier_value=doi,
                    normalized_value=doi.lower(),
                    extractor="deterministic-v3",
                )
            )
        for year in entry.years:
            session.add(
                PaperReferenceIdentifier(
                    reference_id=entry_row.reference_id,
                    identifier_type="YEAR",
                    identifier_value=year,
                    normalized_value=year,
                    extractor="deterministic-v3",
                )
            )
    return row


def accept_attempt(
    session: Any,
    run: DocumentExtractionRun,
    attempt: DocumentExtractionAttempt,
    final_status: str,
    *,
    evidence_status: str = "ACCEPTED",
    reference_status: str = "ACCEPTED",
    superseded_status: str = "SUPERSEDED",
) -> None:
    """Mark the accepted attempt and supersede earlier attempts' accepted outputs."""
    run.status = "COMPLETED"
    run.completed_at = utcnow()
    run.final_status = final_status
    run.accepted_attempt_id = attempt.attempt_id

    session.query(DocumentEvidenceSpan).filter(
        DocumentEvidenceSpan.attempt_id == attempt.attempt_id,
        DocumentEvidenceSpan.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update({"acceptance_status": evidence_status})

    session.query(PaperReferenceSection).filter(
        PaperReferenceSection.attempt_id == attempt.attempt_id,
        PaperReferenceSection.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update({"acceptance_status": reference_status})

    session.query(PaperReference).filter(
        PaperReference.originating_attempt_id == attempt.attempt_id,
        PaperReference.acceptance_status.in_(("CANDIDATE", "ACCEPTED")),
    ).update({"acceptance_status": reference_status})

    # 早于被接受尝试的同一 run 内尝试: 其候选输出标记 SUPERSEDED
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

    # 指向接受的 run
    session.query(PaperDocument).filter_by(
        document_id=run.document_id
    ).update({"current_extraction_run_id": run.extraction_run_id, "updated_at": utcnow()})
