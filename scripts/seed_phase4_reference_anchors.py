#!/usr/bin/env python3
"""Seed deterministic Phase 4 PDF candidates and propose high-value review anchors.

This script NEVER accepts an extraction attempt. It persists deterministic Attempt 1 as
REVIEW_PENDING/CANDIDATE, then proposes documents whose candidate references contain a
DOI that uniquely matches another local Paperazzi paper. A local AI/manual reviewer
must review the attempt before any reference can become ACCEPTED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sqlalchemy as sa  # noqa: E402

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentExtractionAttempt,
    Paper,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    ZoteroAttachment,
)
from paperazzi.database.repositories import (  # noqa: E402
    EXTRACTOR_VERSION,
    PROMPT_HASH,
    add_extraction_attempt,
    create_extraction_run,
    decide_extraction_trigger,
    deterministic_reference_quality,
    persist_evidence_spans,
    persist_reference_section,
)
from paperazzi.identity.reference_resolution import normalize_doi  # noqa: E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa: E402

DEFAULT_DB = REPO_ROOT / "data" / "phase4-validation" / "paperazzi.sqlite3"
DEFAULT_V3_REPORT = (
    REPO_ROOT
    / "pdf-evidence-output"
    / "20260817-022324-pdf-evidence-v3"
    / "pdf_evidence_report.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "data" / "phase4-validation" / "reference_anchor_candidates.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--v3-report", type=Path, default=DEFAULT_V3_REPORT)
    parser.add_argument("--sample-size", type=int, default=80)
    parser.add_argument("--anchor-count", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def local_doi_index(session) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for paper in session.query(Paper).all():
        doi = normalize_doi(paper.doi)
        if doi:
            result.setdefault(doi, []).append(paper.paper_id)
    return result


def seed_attempt(session, document: PaperDocument) -> DocumentExtractionAttempt | None:
    pending = (
        session.query(DocumentExtractionAttempt)
        .join(
            __import__("paperazzi.database.models", fromlist=["DocumentExtractionRun"])
            .DocumentExtractionRun,
            __import__("paperazzi.database.models", fromlist=["DocumentExtractionRun"])
            .DocumentExtractionRun.extraction_run_id
            == DocumentExtractionAttempt.extraction_run_id,
        )
        .filter(
            __import__("paperazzi.database.models", fromlist=["DocumentExtractionRun"])
            .DocumentExtractionRun.document_id
            == document.document_id,
            __import__("paperazzi.database.models", fromlist=["DocumentExtractionRun"])
            .DocumentExtractionRun.status
            == "STARTED",
        )
        .order_by(DocumentExtractionAttempt.attempt_id.desc())
        .first()
    )
    if pending is not None:
        return pending

    trigger = decide_extraction_trigger(
        document, document.document_change_key, EXTRACTOR_VERSION, PROMPT_HASH
    )
    if trigger is None:
        return None
    if not document.local_path or not Path(document.local_path).is_file():
        return None

    run = create_extraction_run(
        session, document.document_id, trigger, document.document_change_key
    )
    evidence = extract_pdf_evidence(document.local_path)
    section_confidence, segmentation_confidence, entry_text_quality = (
        deterministic_reference_quality(evidence.references)
    )
    attempt = add_extraction_attempt(
        session,
        run,
        attempt_number=1,
        actor="DETERMINISTIC",
        strategy="deterministic-v3",
        text_source="PDF_NATIVE",
        backend="PyMuPDF",
        backend_version=evidence.backend_version,
        text_channel=evidence.references.text_channel if evidence.references else None,
        channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
        section_confidence=section_confidence,
        segmentation_confidence=segmentation_confidence,
        entry_text_quality=entry_text_quality,
        reference_status=(
            "SEGMENTED"
            if evidence.references and evidence.references.entries
            else ("RAW_SECTION_ONLY" if evidence.references else "NO_REFERENCE_SECTION_FOUND")
        ),
    )
    persist_evidence_spans(
        session,
        document.document_id,
        attempt,
        [
            {"kind": "affiliation", "page_index": span.page_index, "text": span.text}
            for span in evidence.affiliation_candidates[:4]
        ]
        + [
            {"kind": "correspondence", "page_index": span.page_index, "text": span.text}
            for span in evidence.correspondence_candidates[:2]
        ],
        text_source="PDF_NATIVE",
        text_channel="PYMUPDF_SORTED",
    )
    if evidence.references is not None:
        persist_reference_section(
            session,
            document.paper_id,
            document.document_id,
            attempt,
            evidence.references,
        )
    session.flush()
    return attempt


def anchor_hits(session, attempt: DocumentExtractionAttempt, doi_index: dict[str, list[int]]):
    references = (
        session.query(PaperReference)
        .filter_by(originating_attempt_id=attempt.attempt_id, acceptance_status="CANDIDATE")
        .all()
    )
    hits = []
    for reference in references:
        rows = (
            session.query(PaperReferenceIdentifier)
            .filter_by(reference_id=reference.reference_id, identifier_type="DOI")
            .all()
        )
        for row in rows:
            doi = normalize_doi(row.normalized_value or row.identifier_value)
            if not doi:
                continue
            targets = [
                paper_id
                for paper_id in doi_index.get(doi, [])
                if paper_id != reference.citing_paper_id
            ]
            if len(targets) == 1:
                hits.append(
                    {
                        "reference_id": reference.reference_id,
                        "ordinal": reference.ordinal,
                        "doi": doi,
                        "target_paper_id": targets[0],
                        "raw_text": reference.raw_text[:1000],
                    }
                )
    return hits


def main() -> int:
    args = parse_args()
    if not args.db_path.is_file():
        raise FileNotFoundError(
            f"Phase 4 validation DB not found: {args.db_path}; run scripts/validate_phase4.py first"
        )
    if not args.v3_report.is_file():
        raise FileNotFoundError(f"frozen-v3 report not found: {args.v3_report}")

    report = json.loads(args.v3_report.read_text(encoding="utf-8"))
    sample_keys = [sample["attachment_key"] for sample in report["samples"]][
        : args.sample_size
    ]

    engine = create_paperazzi_engine(args.db_path)
    sf = sa.orm.sessionmaker(bind=engine)
    anchors: list[dict] = []
    seeded = 0
    with sf() as session:
        doi_index = local_doi_index(session)
        for attachment_key in sample_keys:
            attachment = (
                session.query(ZoteroAttachment)
                .filter_by(library_id=1, item_key=attachment_key)
                .one_or_none()
            )
            if attachment is None:
                continue
            document = (
                session.query(PaperDocument)
                .filter_by(zotero_attachment_id=attachment.zotero_attachment_id)
                .one_or_none()
            )
            if document is None or document.availability_status != "PDF_AVAILABLE":
                continue
            attempt = seed_attempt(session, document)
            if attempt is None:
                continue
            seeded += 1
            hits = anchor_hits(session, attempt, doi_index)
            if hits:
                anchors.append(
                    {
                        "attempt_id": attempt.attempt_id,
                        "document_id": document.document_id,
                        "paper_id": document.paper_id,
                        "attachment_key": attachment.item_key,
                        "local_path": document.local_path,
                        "decision": attempt.decision,
                        "section_confidence": attempt.section_confidence,
                        "segmentation_confidence": attempt.segmentation_confidence,
                        "entry_text_quality": attempt.entry_text_quality,
                        "local_doi_hits": hits,
                    }
                )
            if len(anchors) >= args.anchor_count:
                break
        session.commit()

    output = {
        "seeded_attempts": seeded,
        "anchor_count": len(anchors),
        "anchors": anchors,
        "rule": (
            "These are review candidates only. Review each PDF/Attempt with "
            "PDF_EVIDENCE_AGENT.md; do not accept based on DOI hit alone."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    engine.dispose()
    return 0 if anchors else 2


if __name__ == "__main__":
    raise SystemExit(main())
