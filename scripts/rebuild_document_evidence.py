#!/usr/bin/env python3
"""Preview or explicitly rebuild one Paperazzi document's local-PDF evidence.

Preview is read-only. Applying a rebuild requires an explicit review decision and
``--apply``.  The script writes only the Paperazzi-owned database; it never writes the
PDF or Zotero source.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import PaperDocument  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    EXTRACTOR_VERSION,
    PROMPT_HASH,
    PROMPT_VERSION,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    finalize_unaccepted_attempt,
    persist_evidence_spans,
    persist_reference_section,
    record_extraction_review,
)
from paperazzi.identity.authorship_evidence import propose_authorship_evidence  # noqa: E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa: E402
from paperazzi.provenance.service import effective_document_role  # noqa: E402


def _preview(evidence, role) -> dict:
    return {
        "document_role": {
            "role": role.role,
            "source": role.source,
            "confidence": role.confidence,
            "reason_code": role.reason_code,
        },
        "file_name": Path(evidence.path).name,
        "page_count": evidence.page_count,
        "text_status": evidence.text_status,
        "error": evidence.error,
        "emails": list(evidence.emails),
        "affiliation_candidates": [asdict(span) for span in evidence.affiliation_candidates],
        "correspondence_candidates": [asdict(span) for span in evidence.correspondence_candidates],
        "reference": None
        if evidence.references is None
        else {
            "heading": evidence.references.heading,
            "start_page": evidence.references.start_page,
            "end_page": evidence.references.end_page,
            "method": evidence.references.method,
            "confidence": evidence.references.confidence,
            "entry_count": len(evidence.references.entries),
            "text_channel": evidence.references.text_channel,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--document-id", type=int, required=True)
    parser.add_argument(
        "--review-decision",
        choices=["PASS", "ACCEPT_PARTIAL", "UNRESOLVED", "NEEDS_OCR"],
    )
    parser.add_argument("--reviewer", choices=["LOCAL_AI", "MANUAL"])
    parser.add_argument("--quality-notes")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.db_path.is_file():
        print(json.dumps({"error": f"database does not exist: {args.db_path}"}))
        return 2
    engine = create_paperazzi_engine(args.db_path)
    sf = sa.orm.sessionmaker(bind=engine)
    try:
        with sf() as session:
            document = session.get(PaperDocument, args.document_id)
            if document is None:
                print(json.dumps({"error": f"document_id={args.document_id} does not exist"}))
                return 2
            if not document.local_path:
                print(json.dumps({"error": "document has no local_path"}))
                return 2
            role = effective_document_role(session, document)
            evidence = extract_pdf_evidence(document.local_path)
            payload = _preview(evidence, role)
            payload["document_id"] = document.document_id
            payload["paper_id"] = document.paper_id
            payload["apply_requested"] = bool(args.apply)

            if not args.apply:
                payload["dry_run"] = True
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                return 0
            if not args.review_decision or not args.reviewer:
                print(json.dumps({"error": "--apply requires --review-decision and --reviewer"}))
                return 2
            if role.role == "SUPPLEMENTARY":
                print(json.dumps({"error": "refusing paper-level evidence rebuild from SUPPLEMENTARY document"}))
                return 3
            if evidence.error:
                print(json.dumps({"error": f"PDF extraction failed: {evidence.error}", "preview": payload}, ensure_ascii=False))
                return 3

            run = create_extraction_run(
                session,
                document.document_id,
                "MANUAL_REBUILD",
                document.document_change_key,
                extractor_version=EXTRACTOR_VERSION,
                prompt_version=PROMPT_VERSION,
                prompt_hash=PROMPT_HASH,
            )
            attempt = add_extraction_attempt(
                session,
                run,
                attempt_number=1,
                actor="DETERMINISTIC",
                strategy="manual-reviewed-rebuild",
                text_source="PDF_NATIVE",
                backend=evidence.backend,
                backend_version=evidence.backend_version,
                text_channel="PYMUPDF_SORTED",
                channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
                front_matter_status=evidence.text_status,
                reference_status=None if evidence.references is None else evidence.references.confidence,
                quality_notes=args.quality_notes,
            )
            spans = [
                {"kind": span.kind, "page_index": span.page_index, "text": span.text, "bbox": span.bbox}
                for span in (*evidence.affiliation_candidates, *evidence.correspondence_candidates)
            ]
            persisted_spans = persist_evidence_spans(
                session,
                document.document_id,
                attempt,
                spans,
                acceptance_status="CANDIDATE",
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
                    acceptance_status="CANDIDATE",
                    text_source="PDF_NATIVE",
                )
            record_extraction_review(
                session,
                attempt,
                reviewer_type=args.reviewer,
                decision=args.review_decision,
                quality_notes=args.quality_notes,
                reviewer_runtime="Paperazzi-rebuild-document-evidence",
            )
            if args.review_decision in ("PASS", "ACCEPT_PARTIAL"):
                accept_attempt(session, run, attempt, args.review_decision)
                authorship_result = propose_authorship_evidence(session, document.paper_id)
            else:
                finalize_unaccepted_attempt(session, run, attempt)
                authorship_result = {
                    "corresponding_accepted": 0,
                    "affiliation_candidates": 0,
                    "unresolved": 0,
                }
            session.commit()
            payload.update(
                {
                    "dry_run": False,
                    "applied": True,
                    "extraction_run_id": run.extraction_run_id,
                    "attempt_id": attempt.attempt_id,
                    "review_decision": args.review_decision,
                    "persisted_front_matter_spans": persisted_spans,
                    "authorship_projection": authorship_result,
                }
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
