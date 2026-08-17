"""Map accepted local PDF evidence to paper-scoped authorship roles.

Candidate/unreviewed evidence is never authoritative. Clear correspondence spans may
be mapped deterministically when an explicit correspondence marker and a unique author
name/email mapping are present; affiliation mappings remain candidates unless
explicitly reviewed. Supplementary documents cannot establish paper-level authorship
roles.
"""

from __future__ import annotations

import re
from typing import Any

from paperazzi.database.models import DocumentEvidenceSpan, PaperCreatorMention, PaperDocument
from paperazzi.provenance.service import effective_document_role

from .models import Authorship, AuthorshipEvidence
from .normalization import normalize_search_text
from .review import enqueue_review

RESOLVER_VERSION = "phase4-authorship-evidence-v2-document-role-email"
_CORRESPONDENCE_MARKER = re.compile(
    r"\b(corresponding\s+author|correspondence|corresponding\s+authors?)\b", re.I
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PUBLISHER_NOISE = re.compile(
    r"\b(publisher|editorial\s+office|customer\s+service|support\s+team|permissions?)\b",
    re.I,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+", re.I)


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


def _compact(value: str | None) -> str:
    return _NON_ALNUM_RE.sub("", normalize_search_text(value)).casefold()


def _email_author_matches(
    rows: list[tuple[Authorship, PaperCreatorMention]], raw_text: str
) -> list[tuple[Authorship, PaperCreatorMention]]:
    """Return only unique paper-author matches supported by email local parts.

    Prefix matching intentionally requires both given and family components. It handles
    addresses such as ``marc.illasubina`` for author ``Marc Illa`` while refusing to
    auto-map an email when multiple paper authors satisfy the same prefix.
    """
    matched: dict[int, tuple[Authorship, PaperCreatorMention]] = {}
    for email in _EMAIL_RE.findall(raw_text):
        local = _compact(email.split("@", 1)[0])
        if not local:
            continue
        candidates: list[tuple[Authorship, PaperCreatorMention]] = []
        for authorship, mention in rows:
            given = _compact(mention.first_name)
            family = _compact(mention.last_name)
            if not given or not family:
                continue
            forms = (given + family, family + given, given[:1] + family, family + given[:1])
            if any(len(form) >= 3 and local.startswith(form) for form in forms):
                candidates.append((authorship, mention))
        if len(candidates) == 1:
            row = candidates[0]
            matched[row[0].authorship_id] = row
    return list(matched.values())


def _find_authors_in_text(
    session: Any, paper_id: int, raw_text: str
) -> list[tuple[Authorship, PaperCreatorMention]]:
    normalized = normalize_search_text(raw_text)
    rows = _active_authorships(session, paper_id)
    matches: list[tuple[Authorship, PaperCreatorMention]] = []
    for authorship, mention in rows:
        family = normalize_search_text(mention.last_name)
        display = normalize_search_text(mention.display_name)
        if display and display in normalized:
            matches.append((authorship, mention))
        elif family and re.search(rf"\b{re.escape(family)}\b", normalized):
            matches.append((authorship, mention))
    matches.extend(_email_author_matches(rows, raw_text))
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


def _eligible_document_ids(session: Any, paper_id: int) -> list[int]:
    documents = session.query(PaperDocument).filter_by(paper_id=paper_id).all()
    return [
        document.document_id
        for document in documents
        if effective_document_role(session, document).role != "SUPPLEMENTARY"
    ]


def propose_authorship_evidence(session: Any, paper_id: int) -> dict[str, int]:
    document_ids = _eligible_document_ids(session, paper_id)
    if not document_ids:
        return {"corresponding_accepted": 0, "affiliation_candidates": 0, "unresolved": 0}

    spans = (
        session.query(DocumentEvidenceSpan)
        .filter(
            DocumentEvidenceSpan.document_id.in_(document_ids),
            DocumentEvidenceSpan.acceptance_status == "ACCEPTED",
            DocumentEvidenceSpan.kind.in_(
                ("correspondence", "correspondence-candidate", "affiliation", "affiliation-candidate")
            ),
        )
        .all()
    )
    counts = {"corresponding_accepted": 0, "affiliation_candidates": 0, "unresolved": 0}
    for span in spans:
        mapped_paper_id = _paper_for_span(session, span)
        if mapped_paper_id != paper_id:
            continue
        matches = _find_authors_in_text(session, paper_id, span.raw_text)
        is_correspondence = span.kind in ("correspondence", "correspondence-candidate")
        is_affiliation = span.kind in ("affiliation", "affiliation-candidate")

        if is_correspondence:
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

        elif is_affiliation and matches:
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
        document = session.get(PaperDocument, span.document_id)
        if document is not None and effective_document_role(session, document).role == "SUPPLEMENTARY":
            raise ValueError("supplementary PDF evidence cannot establish paper-level authorship roles")
    row.status = "ACCEPTED"
    row.resolver = reviewer
    authorship = session.get(Authorship, row.authorship_id)
    if row.evidence_type == "CORRESPONDING_AUTHOR":
        authorship.is_corresponding_author = True
        authorship.corresponding_status = "ACCEPTED"
    session.flush()
    return row
