#!/usr/bin/env python3
"""Read-only full-library QA inventory for local-AI review.

This script never writes Paperazzi or Zotero. It traverses active Paperazzi papers,
selects the currently preferred primary PDF, runs the production PDF extractor, and
emits a deterministic JSONL review queue plus machine-readable diagnostics.

The queue is intentionally suitable for a local AI agent: every selected primary PDF
is included, not just heuristic failures, so unknown publisher layouts can be found
instead of being hidden by the current parser.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.models import Paper, PaperCreatorMention, PaperDocument  # noqa: E402
from paperazzi.identity.authorship_evidence import _find_mentions_in_text  # noqa: E402
from paperazzi.local_evidence.correspondence import classify_correspondence_text  # noqa: E402
from paperazzi.local_evidence.pdf import extract_dois, extract_pdf_evidence  # noqa: E402
from paperazzi.provenance.service import effective_document_role, select_primary_document  # noqa: E402

AUDIT_VERSION = "full-library-local-ai-v1"
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_STOPWORDS = {
    "about", "after", "among", "and", "are", "based", "between", "from", "into",
    "over", "study", "the", "their", "through", "toward", "towards", "using", "via",
    "with", "without",
}


def _readonly_engine(db_path: Path) -> sa.Engine:
    resolved = db_path.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro"

    def _creator() -> sqlite3.Connection:
        return sqlite3.connect(uri, uri=True)

    engine = sa.create_engine("sqlite://", creator=_creator)

    @event.listens_for(engine, "connect")
    def _query_only(dbapi_connection: sqlite3.Connection, _connection_record: Any) -> None:
        dbapi_connection.execute("PRAGMA query_only=ON")
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _source_name(mention: PaperCreatorMention) -> str:
    return (
        mention.display_name
        or " ".join(part for part in (mention.first_name, mention.last_name) if part)
        or f"<creator_mention:{mention.creator_mention_id}>"
    )


def _normalize(value: str | None) -> str:
    return " ".join(_WORD_RE.findall((value or "").casefold()))


def _title_overlap(title: str | None, front_matter: str) -> float | None:
    title_tokens = {
        token
        for token in _WORD_RE.findall((title or "").casefold())
        if len(token) >= 4 and token not in _STOPWORDS
    }
    if not title_tokens:
        return None
    front_tokens = set(_WORD_RE.findall((front_matter or "").casefold()))
    return round(len(title_tokens & front_tokens) / len(title_tokens), 4)


def _author_surname_coverage(
    mentions: Iterable[PaperCreatorMention], front_matter: str
) -> tuple[float | None, list[str]]:
    normalized_front = f" {_normalize(front_matter)} "
    tested: list[str] = []
    missing: list[str] = []
    for mention in mentions:
        surname = _normalize(mention.last_name)
        if len(surname) < 3:
            continue
        tested.append(surname)
        if f" {surname} " not in normalized_front:
            missing.append(_source_name(mention))
    if not tested:
        return None, missing
    return round((len(tested) - len(missing)) / len(tested), 4), missing


def _role_span_payload(span: Any) -> dict[str, Any]:
    classified = classify_correspondence_text(span.text)
    return {
        "page": int(span.page_index) + 1,
        "kind": span.kind,
        "semantic_kind": classified.kind,
        "emails": list(classified.emails),
        "text": " ".join((span.text or "").split())[:1600],
    }


def _span_payload(span: Any) -> dict[str, Any]:
    return {
        "page": int(span.page_index) + 1,
        "kind": span.kind,
        "text": " ".join((span.text or "").split())[:1600],
    }


def _risk(flags: list[str]) -> tuple[int, str]:
    weights = {
        "NO_AVAILABLE_PRIMARY_PDF": 100,
        "SELECTED_SUPPLEMENTARY_DOCUMENT": 100,
        "PDF_PARSE_ERROR": 100,
        "FRONT_MATTER_DOI_CONFLICT": 95,
        "ROLE_SIGNAL_UNMAPPED_TO_SOURCE_AUTHOR": 90,
        "NO_USABLE_FRONT_MATTER_TEXT": 85,
        "MULTIPLE_PRIMARY_CANDIDATES": 70,
        "LOW_SOURCE_AUTHOR_HEADER_COVERAGE": 65,
        "LOW_TITLE_FRONT_MATTER_OVERLAP": 60,
        "ROLE_EMAIL_AUTHOR_COUNT_MISMATCH": 55,
        "AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL": 45,
        "ROLE_SIGNAL_WITHOUT_EMAIL": 35,
        "CONTACT_WITHOUT_ROLE_SIGNAL": 20,
        "NO_REFERENCE_SECTION": 10,
    }
    score = min(100, sum(weights.get(flag, 10) for flag in set(flags)))
    if score >= 85:
        severity = "P0"
    elif score >= 60:
        severity = "P1"
    elif score >= 30:
        severity = "P2"
    else:
        severity = "P3"
    return score, severity


def _document_rows(session: Any, paper_id: int) -> list[PaperDocument]:
    return (
        session.query(PaperDocument)
        .filter(
            PaperDocument.paper_id == paper_id,
            PaperDocument.present_in_last_scan.is_(True),
        )
        .order_by(PaperDocument.document_id)
        .all()
    )


def _reachable_documents(session: Any, paper_id: int) -> list[tuple[PaperDocument, Any]]:
    rows: list[tuple[PaperDocument, Any]] = []
    for document in _document_rows(session, paper_id):
        if (
            document.availability_status == "PDF_AVAILABLE"
            and document.local_path
            and Path(document.local_path).is_file()
        ):
            rows.append((document, effective_document_role(session, document)))
    return rows


def _audit_paper(session: Any, paper: Paper) -> dict[str, Any]:
    mentions = (
        session.query(PaperCreatorMention)
        .filter_by(paper_id=paper.paper_id, creator_type="author")
        .order_by(PaperCreatorMention.order_index, PaperCreatorMention.creator_mention_id)
        .all()
    )
    source_authors = [_source_name(row) for row in mentions]
    reachable = _reachable_documents(session, paper.paper_id)
    selected = select_primary_document(session, paper.paper_id)
    flags: list[str] = []

    document_inventory = [
        {
            "document_id": document.document_id,
            "path": document.local_path,
            "role": role.role,
            "role_source": role.source,
            "role_confidence": role.confidence,
            "role_reason_code": role.reason_code,
        }
        for document, role in reachable
    ]
    primary_candidates = [row for row in document_inventory if row["role"] == "PRIMARY_ARTICLE"]
    if len(primary_candidates) > 1:
        flags.append("MULTIPLE_PRIMARY_CANDIDATES")

    base: dict[str, Any] = {
        "schema_version": AUDIT_VERSION,
        "paper_id": paper.paper_id,
        "title": paper.title,
        "doi": paper.doi,
        "venue": paper.venue,
        "publication_year": paper.publication_year,
        "source_authors": source_authors,
        "reachable_documents": document_inventory,
        "selected_document_id": None,
        "selected_pdf_path": None,
        "selected_document_role": None,
        "machine_predicted_corresponding_authors": [],
        "role_candidates": [],
        "contact_candidates": [],
        "author_marker_candidates": [],
        "front_matter_preview": "",
        "text_status": None,
        "page_count": None,
        "reference_status": None,
        "title_front_matter_overlap": None,
        "source_author_header_coverage": None,
        "source_authors_missing_from_header": [],
        "front_matter_dois": [],
        "flags": flags,
        "risk_score": 0,
        "severity": "P3",
        "requires_pdf_review": False,
    }

    if selected is None:
        flags.append("NO_AVAILABLE_PRIMARY_PDF")
        score, severity = _risk(flags)
        base.update(
            {
                "flags": sorted(set(flags)),
                "risk_score": score,
                "severity": severity,
                "requires_pdf_review": False,
            }
        )
        return base

    role = effective_document_role(session, selected)
    base["selected_document_id"] = selected.document_id
    base["selected_pdf_path"] = selected.local_path
    base["selected_document_role"] = {
        "role": role.role,
        "source": role.source,
        "confidence": role.confidence,
        "reason_code": role.reason_code,
    }
    base["requires_pdf_review"] = True
    if role.role == "SUPPLEMENTARY":
        flags.append("SELECTED_SUPPLEMENTARY_DOCUMENT")

    evidence = extract_pdf_evidence(selected.local_path)
    base["page_count"] = evidence.page_count
    base["text_status"] = evidence.text_status
    if evidence.error:
        flags.append("PDF_PARSE_ERROR")
        base["parse_error"] = evidence.error
        score, severity = _risk(flags)
        base.update({"flags": sorted(set(flags)), "risk_score": score, "severity": severity})
        return base

    base["front_matter_preview"] = " ".join(evidence.front_matter_text.split())[:4000]
    base["role_candidates"] = [_role_span_payload(span) for span in evidence.correspondence_candidates]
    base["contact_candidates"] = [_span_payload(span) for span in evidence.contact_candidates]
    base["author_marker_candidates"] = [_span_payload(span) for span in evidence.author_marker_candidates]

    if len(evidence.front_matter_text.strip()) < 80:
        flags.append("NO_USABLE_FRONT_MATTER_TEXT")

    title_overlap = _title_overlap(paper.title, evidence.front_matter_text)
    base["title_front_matter_overlap"] = title_overlap
    if title_overlap is not None and len(_normalize(paper.title)) >= 20 and title_overlap < 0.20:
        flags.append("LOW_TITLE_FRONT_MATTER_OVERLAP")

    author_coverage, missing_authors = _author_surname_coverage(mentions, evidence.front_matter_text)
    base["source_author_header_coverage"] = author_coverage
    base["source_authors_missing_from_header"] = missing_authors
    if author_coverage is not None and len(mentions) >= 2 and author_coverage < 0.50:
        flags.append("LOW_SOURCE_AUTHOR_HEADER_COVERAGE")

    front_dois = list(extract_dois(evidence.front_matter_text))
    base["front_matter_dois"] = front_dois
    metadata_doi = (paper.doi or "").strip().casefold()
    if metadata_doi and front_dois and metadata_doi not in {row.casefold() for row in front_dois}:
        flags.append("FRONT_MATTER_DOI_CONFLICT")

    predicted: dict[int, str] = {}
    role_email_count = 0
    for span in evidence.correspondence_candidates:
        classified = classify_correspondence_text(span.text)
        role_email_count += len(classified.emails)
        for mention in _find_mentions_in_text(session, paper.paper_id, span.text):
            predicted[mention.creator_mention_id] = _source_name(mention)

    base["machine_predicted_corresponding_authors"] = list(predicted.values())
    if evidence.correspondence_candidates and not predicted:
        flags.append("ROLE_SIGNAL_UNMAPPED_TO_SOURCE_AUTHOR")
    if role_email_count and len(predicted) < role_email_count:
        flags.append("ROLE_EMAIL_AUTHOR_COUNT_MISMATCH")
    if evidence.correspondence_candidates and role_email_count == 0:
        flags.append("ROLE_SIGNAL_WITHOUT_EMAIL")
    if evidence.contact_candidates and not evidence.correspondence_candidates:
        flags.append("CONTACT_WITHOUT_ROLE_SIGNAL")
    if evidence.author_marker_candidates and not evidence.correspondence_candidates:
        flags.append("AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL")

    references = evidence.references
    if references is None:
        base["reference_status"] = {
            "present": False,
            "heading": None,
            "confidence": None,
            "method": None,
            "entry_count": 0,
        }
        if evidence.page_count >= 4:
            flags.append("NO_REFERENCE_SECTION")
    else:
        base["reference_status"] = {
            "present": True,
            "heading": references.heading,
            "confidence": references.confidence,
            "method": references.method,
            "entry_count": len(references.entries),
            "start_page": references.start_page + 1,
            "end_page": references.end_page + 1,
        }

    score, severity = _risk(flags)
    base.update({"flags": sorted(set(flags)), "risk_score": score, "severity": severity})
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "phase5-validation" / "full-library-local-ai-audit",
    )
    parser.add_argument("--start-after-paper-id", type=int, default=0)
    parser.add_argument("--max-papers", type=int)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()

    if not args.db_path.is_file():
        parser.error(f"database not found: {args.db_path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "all_papers.jsonl"
    queue_path = args.output_dir / "ai_review_queue.jsonl"
    summary_path = args.output_dir / "summary.json"

    engine = _readonly_engine(args.db_path)
    Session = sessionmaker(bind=engine)
    rows: list[dict[str, Any]] = []
    try:
        with Session() as session:
            query = (
                session.query(Paper)
                .filter(
                    Paper.active_in_zotero.is_(True),
                    Paper.paper_id > args.start_after_paper_id,
                )
                .order_by(Paper.paper_id)
            )
            if args.max_papers is not None:
                query = query.limit(max(0, args.max_papers))
            papers = query.all()
            for index, paper in enumerate(papers, 1):
                row = _audit_paper(session, paper)
                rows.append(row)
                if args.progress_every > 0 and index % args.progress_every == 0:
                    print(
                        json.dumps(
                            {
                                "progress": index,
                                "paper_id": paper.paper_id,
                                "p0": sum(item["severity"] == "P0" for item in rows),
                                "pdf_reviewable": sum(item["requires_pdf_review"] for item in rows),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
    finally:
        engine.dispose()

    with audit_path.open("w", encoding="utf-8") as handle:
        for row in sorted(rows, key=lambda item: item["paper_id"]):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Every reachable selected primary PDF goes to the AI queue. Risk only controls order.
    review_rows = [row for row in rows if row["requires_pdf_review"]]
    review_rows.sort(key=lambda item: (-item["risk_score"], item["paper_id"]))
    with queue_path.open("w", encoding="utf-8") as handle:
        for row in review_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    flag_counts = Counter(flag for row in rows for flag in row["flags"])
    severity_counts = Counter(row["severity"] for row in rows)
    summary = {
        "schema_version": AUDIT_VERSION,
        "database": str(args.db_path.resolve()),
        "papers_scanned": len(rows),
        "pdfs_queued_for_ai_review": len(review_rows),
        "papers_without_reviewable_primary_pdf": sum(
            not row["requires_pdf_review"] for row in rows
        ),
        "severity_counts": dict(sorted(severity_counts.items())),
        "flag_counts": dict(sorted(flag_counts.items())),
        "role_signal_papers": sum(bool(row["role_candidates"]) for row in rows),
        "contact_only_papers": sum(
            bool(row["contact_candidates"]) and not row["role_candidates"] for row in rows
        ),
        "machine_correspondence_nonempty": sum(
            bool(row["machine_predicted_corresponding_authors"]) for row in rows
        ),
        "outputs": {
            "all_papers": str(audit_path),
            "ai_review_queue": str(queue_path),
            "summary": str(summary_path),
        },
        "safety": {
            "database_open_mode": "read-only",
            "paperazzi_writes": False,
            "zotero_writes": False,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
