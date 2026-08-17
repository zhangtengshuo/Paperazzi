#!/usr/bin/env python3
"""Inspect document provenance and explicitly apply role/retraction corrections.

This tool writes only the Paperazzi-owned database.  Mutating commands require
``--apply``; without it they print the proposed action and exit without a transaction.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionRun,
    Paper,
    PaperDocument,
    PaperReference,
    PaperReferenceSection,
)
from paperazzi.identity.models import AuthorshipEvidence  # noqa: E402
from paperazzi.provenance.models import DocumentRole, RetractionEvent, RetractionImpact  # noqa: E402
from paperazzi.provenance.service import (  # noqa: E402
    effective_document_role,
    retract_extraction_attempt,
    select_primary_document,
    set_document_role,
)


def _session(db_path: Path):
    engine = create_paperazzi_engine(db_path)
    return engine, sa.orm.sessionmaker(bind=engine)()


def _document_payload(session, document: PaperDocument) -> dict:
    role = effective_document_role(session, document)
    return {
        "document_id": document.document_id,
        "paper_id": document.paper_id,
        "file_name": Path(document.local_path).name if document.local_path else None,
        "availability_status": document.availability_status,
        "present_in_last_scan": bool(document.present_in_last_scan),
        "effective_role": role.role,
        "role_source": role.source,
        "role_confidence": role.confidence,
        "role_reason_code": role.reason_code,
        "current_extraction_run_id": document.current_extraction_run_id,
        "extraction_runs": session.query(DocumentExtractionRun).filter_by(document_id=document.document_id).count(),
        "evidence_spans": session.query(DocumentEvidenceSpan).filter_by(document_id=document.document_id).count(),
        "accepted_evidence_spans": session.query(DocumentEvidenceSpan).filter_by(
            document_id=document.document_id, acceptance_status="ACCEPTED"
        ).count(),
        "reference_sections": session.query(PaperReferenceSection).filter_by(document_id=document.document_id).count(),
        "references": session.query(PaperReference).filter_by(document_id=document.document_id).count(),
    }


def inspect_paper(session, paper_id: int) -> dict:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise KeyError(f"paper_id={paper_id} does not exist")
    documents = session.query(PaperDocument).filter_by(paper_id=paper_id).order_by(PaperDocument.document_id).all()
    primary = select_primary_document(session, paper_id)
    return {
        "paper_id": paper_id,
        "title": paper.title,
        "selected_primary_document_id": None if primary is None else primary.document_id,
        "documents": [_document_payload(session, document) for document in documents],
    }


def inspect_attempt(session, attempt_id: int) -> dict:
    attempt = session.get(DocumentExtractionAttempt, attempt_id)
    if attempt is None:
        raise KeyError(f"attempt_id={attempt_id} does not exist")
    run = session.get(DocumentExtractionRun, attempt.extraction_run_id)
    span_ids = [
        value
        for (value,) in session.query(DocumentEvidenceSpan.evidence_span_id)
        .filter_by(attempt_id=attempt_id)
        .all()
    ]
    downstream = 0
    if span_ids:
        downstream = session.query(AuthorshipEvidence).filter(
            AuthorshipEvidence.evidence_span_id.in_(span_ids)
        ).count()
    return {
        "attempt_id": attempt_id,
        "extraction_run_id": attempt.extraction_run_id,
        "document_id": None if run is None else run.document_id,
        "decision": attempt.decision,
        "accepted_by_run": bool(run and run.accepted_attempt_id == attempt_id),
        "evidence_span_ids": span_ids,
        "downstream_authorship_evidence_rows": downstream,
        "reference_rows": session.query(PaperReference).filter_by(originating_attempt_id=attempt_id).count(),
    }


def _event_payload(session, event: RetractionEvent) -> dict:
    impacts = session.query(RetractionImpact).filter_by(retraction_id=event.retraction_id).order_by(
        RetractionImpact.impact_id
    ).all()
    return {
        "retraction_id": event.retraction_id,
        "root_type": event.root_type,
        "root_id": event.root_id,
        "scope": event.scope,
        "reason_code": event.reason_code,
        "impact_count": len(impacts),
        "impacts": [
            {
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "action": row.action,
            }
            for row in impacts
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    paper = sub.add_parser("inspect-paper")
    paper.add_argument("--paper-id", type=int, required=True)

    attempt = sub.add_parser("inspect-attempt")
    attempt.add_argument("--attempt-id", type=int, required=True)

    role = sub.add_parser("set-document-role")
    role.add_argument("--document-id", type=int, required=True)
    role.add_argument("--role", choices=["PRIMARY_ARTICLE", "SUPPLEMENTARY", "UNKNOWN"], required=True)
    role.add_argument("--source", choices=["LOCAL_AI", "MANUAL"], required=True)
    role.add_argument("--reason-code", required=True)
    role.add_argument("--notes")
    role.add_argument("--apply", action="store_true")

    retract = sub.add_parser("retract-attempt")
    retract.add_argument("--attempt-id", type=int, required=True)
    retract.add_argument("--reason-code", required=True)
    retract.add_argument("--reason-text")
    retract.add_argument("--actor", choices=["LOCAL_AI", "MANUAL"], required=True)
    retract.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.db_path.is_file():
        print(json.dumps({"error": f"database does not exist: {args.db_path}"}))
        return 2
    engine, session = _session(args.db_path)
    try:
        if args.command == "inspect-paper":
            payload = inspect_paper(session, args.paper_id)
        elif args.command == "inspect-attempt":
            payload = inspect_attempt(session, args.attempt_id)
        elif args.command == "set-document-role":
            proposal = {
                "command": args.command,
                "document_id": args.document_id,
                "role": args.role,
                "source": args.source,
                "reason_code": args.reason_code,
                "notes": args.notes,
            }
            if not args.apply:
                payload = {"dry_run": True, "proposal": proposal}
            else:
                row = set_document_role(
                    session,
                    args.document_id,
                    args.role,
                    source=args.source,
                    reason_code=args.reason_code,
                    notes=args.notes,
                    actor=args.source,
                )
                session.commit()
                event = session.query(RetractionEvent).filter_by(
                    root_type="DOCUMENT", root_id=str(args.document_id)
                ).order_by(RetractionEvent.retraction_id.desc()).first()
                payload = {
                    "applied": True,
                    "document_id": row.document_id,
                    "role": row.role,
                    "retraction": None if event is None else _event_payload(session, event),
                }
        else:
            proposal = {
                "command": args.command,
                "attempt_id": args.attempt_id,
                "reason_code": args.reason_code,
                "reason_text": args.reason_text,
                "actor": args.actor,
            }
            if not args.apply:
                payload = {"dry_run": True, "proposal": proposal, "attempt": inspect_attempt(session, args.attempt_id)}
            else:
                event = retract_extraction_attempt(
                    session,
                    args.attempt_id,
                    reason_code=args.reason_code,
                    reason_text=args.reason_text,
                    actor=args.actor,
                )
                session.commit()
                payload = {"applied": True, "retraction": _event_payload(session, event)}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
