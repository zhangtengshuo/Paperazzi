"""Map accepted local PDF evidence to paper-scoped authorship roles.

Candidate/unreviewed evidence is never authoritative. Clear correspondence spans may
be mapped deterministically when an explicit correspondence marker and a unique author
name are both present; affiliation mappings remain candidates unless explicitly
reviewed.
"""

from __future__ import annotations

import re
from typing import Any

from paperazzi.database.models import DocumentEvidenceSpan, PaperCreatorMention, PaperDocument

from .models import Authorship, AuthorshipEvidence
from .normalization import normalize_search_text
from .review import enqueue_review

RESOLVER_VERSION = "phase4-authorship-evidence-v1"
_CORRESPONDENCE_MARKER = re.compile(
    r"\b(corresponding\s+author|correspondence|corresponding\s+authors?)\b", re.I
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PUBLISHER_NOISE = re.compile(
    r"\b(publisher|editorial\s+office|customer\s+service|support\s+team|permissions?)\b",
    re.I,
)


def _active_authorships(session: Any, paper_id: int) -> list[tuple[Authorship, PaperCreatorMention]]:
    rows = (
        session.query(Authorship, PaperCreatorMention)
        .join(
            PaperCreatorMention,
            PaperCreatorMention.creator_mention_id == Authorship.creator_mention_id,
        )
        .filter(Authorship.paper_id == paper_id, Authorship.status == "ACTIVE")
        .all()
    )
    return rows


def _paper_for_span(session: Any, span: DocumentEvidenceSpan) -> int | None:
    document = session.get(PaperDocument, span.document_id)
    return None if document is None else document.paper_id


def _find_authors_in_text(
    session: Any, paper_id: int, raw_text: str
) -> list[tuple[Authorship, PaperCreatorMention]]:
    normalized = normalize_search_text(raw_text)
    matches: list[tuple[Authorship, PaperCreatorMention]] = []
    for authorship, mention in _active_authorships(session, paper_id):
        family = normalize_search_text(mention.last_name)
        display = normalize_search_text(mention.display_name)
        if display and display in normalized:
            matches.append((authorship, mention))
        elif family and re.search(rf"\b{re.escape(family)}\b", normalized):
            matches.append((authorship, mention))
    # Deduplicate by authorship id while preserving paper order.
    unique = {row[0].authorship_id: row for row in matches}
    return sorted(unique.values(), key=lambda row: row[0].order_index)


def _upsert_evidence(
    session: Any,
    *,
    authorship: Authorship,
    span: DocumentEvidenceSpan,
    evidence_type: str,
    status: str,
    score: float,
) -> AuthorshipEvidence:
    row = (
        session.query(AuthorshipEvidence)
        .filter_by(
            authorship_id=authorship.authorship_id,
            evidence_span_id=span.evidence_span_id,
            evidence_type=evidence_type,
        )
        .first()
    )
    if row is None:
        row = AuthorshipEvidence(
            authorship_id=authorship.authorship_id,
            evidence_span_id=span.evidence_span_id,
            evidence_type=evidence_type,
            status=status,
            raw_value=span.raw_text,
            normalized_value=normalize_search_text(span.raw_text),
            resolver=RESOLVER_VERSION,
            score=score,
        )
        session.add(row)
    else:
        row.status = status
        row.score = score
        row.raw_value = span.raw_text
        row.normalized_value = normalize_search_text(span.raw_text)
        row.resolver = RESOLVER_VERSION
    session.flush()
    return row


def propose_authorship_evidence(session: Any, paper_id: int) -> dict[str, int]:
    document_ids = [
        document_id
        for (document_id,) in session.query(PaperDocument.document_id)
        .filter_by(paper_id=paper_id)
        .all()
    ]
    if not document_ids:
        return {"corresponding_accepted": 0, "affiliation_candidates": 0, "unresolved": 0}

    spans = (
        session.query(DocumentEvidenceSpan)
        .filter(
            DocumentEvidenceSpan.document_id.in_(document_ids),
            DocumentEvidenceSpan.acceptance_status == "ACCEPTED",
            DocumentEvidenceSpan.kind.in_(("correspondence", "affiliation")),
        )
        .all()
    )
    counts = {"corresponding_accepted": 0, "affiliation_candidates": 0, "unresolved": 0}
    for span in spans:
        mapped_paper_id = _paper_for_span(session, span)
        if mapped_paper_id != paper_id:
            continue
        matches = _find_authors_in_text(session, paper_id, span.raw_text)

        if span.kind == "correspondence":
            explicit = bool(_CORRESPONDENCE_MARKER.search(span.raw_text))
            emails = _EMAIL_RE.findall(span.raw_text)
            noisy = bool(_PUBLISHER_NOISE.search(span.raw_text))
            if explicit and matches and not noisy:
                for authorship, _mention in matches:
                    _upsert_evidence(
                        session,
                        authorship=authorship,
                        span=span,
                        evidence_type="CORRESPONDING_AUTHOR",
                        status="ACCEPTED",
                        score=1.0 if emails else 0.9,
                    )
                    authorship.is_corresponding_author = True
                    authorship.corresponding_status = "ACCEPTED"
                    counts["corresponding_accepted"] += 1
            else:
                if noisy:
                    for authorship, _mention in matches:
                        _upsert_evidence(
                            session,
                            authorship=authorship,
                            span=span,
                            evidence_type="CORRESPONDING_AUTHOR",
                            status="REJECTED",
                            score=0.0,
                        )
                else:
                    enqueue_review(
                        session,
                        queue_type="UNRESOLVED_CORRESPONDING_AUTHOR",
                        subject_type="evidence_span",
                        subject_id=span.evidence_span_id,
                        reason_code=(
                            "NO_AUTHOR_NAME_MAPPING"
                            if not matches
                            else "CORRESPONDENCE_MARKER_NOT_EXPLICIT"
                        ),
                        payload={"emails": emails, "matched_authorships": [a.authorship_id for a, _ in matches]},
                        priority=75,
                    )
                    counts["unresolved"] += 1

        elif span.kind == "affiliation" and matches:
            status = "CANDIDATE"
            score = 0.7 if len(matches) == 1 else 0.4
            for authorship, _mention in matches:
                _upsert_evidence(
                    session,
                    authorship=authorship,
                    span=span,
                    evidence_type="AFFILIATION",
                    status=status,
                    score=score,
                )
                counts["affiliation_candidates"] += 1

    session.flush()
    return counts


def accept_authorship_evidence(
    session: Any,
    authorship_evidence_id: int,
    *,
    reviewer: str = "MANUAL",
) -> AuthorshipEvidence:
    row = session.get(AuthorshipEvidence, authorship_evidence_id)
    if row is None:
        raise KeyError(f"authorship_evidence_id={authorship_evidence_id} does not exist")
    if row.evidence_span_id is not None:
        span = session.get(DocumentEvidenceSpan, row.evidence_span_id)
        if span is None or span.acceptance_status != "ACCEPTED":
            raise ValueError("authorship evidence cannot be accepted from an unaccepted PDF span")
    row.status = "ACCEPTED"
    row.resolver = reviewer
    authorship = session.get(Authorship, row.authorship_id)
    if row.evidence_type == "CORRESPONDING_AUTHOR":
        authorship.is_corresponding_author = True
        authorship.corresponding_status = "ACCEPTED"
    session.flush()
    return row
