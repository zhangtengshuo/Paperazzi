"""Map accepted local PDF evidence to source mentions, then canonical authorships.

Corresponding-author status is a paper-scoped role.  PDF role evidence is therefore
attached first to the immutable ``PaperCreatorMention`` and projected to canonical
``Authorship`` only when identity resolution is available.  Contact information alone
is never treated as a corresponding-author declaration.
"""

from __future__ import annotations

import re
from typing import Any

from paperazzi.database.models import DocumentEvidenceSpan, PaperCreatorMention, PaperDocument
from paperazzi.local_evidence.correspondence import (
    EMAIL_RE,
    classify_correspondence_text,
    extract_leading_marker,
)
from paperazzi.provenance.service import effective_document_role

from .models import Authorship, AuthorshipEvidence, CreatorMentionRoleEvidence
from .normalization import normalize_search_text
from .review import enqueue_review

RESOLVER_VERSION = "phase5-correspondence-v3-source-mention-role"
_PUBLISHER_NOISE = re.compile(
    r"\b(publisher|editorial\s+office|customer\s+service|support\s+team|permissions?)\b",
    re.I,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+", re.I)
_STRONG_AUTHOR_MARKERS = ("*", "✉")


def _paper_mentions(session: Any, paper_id: int) -> list[PaperCreatorMention]:
    return (
        session.query(PaperCreatorMention)
        .filter_by(paper_id=paper_id, creator_type="author")
        .order_by(PaperCreatorMention.order_index, PaperCreatorMention.creator_mention_id)
        .all()
    )


def _active_authorships(session: Any, paper_id: int) -> list[tuple[Authorship, PaperCreatorMention]]:
    return (
        session.query(Authorship, PaperCreatorMention)
        .join(PaperCreatorMention, PaperCreatorMention.creator_mention_id == Authorship.creator_mention_id)
        .filter(Authorship.paper_id == paper_id, Authorship.status == "ACTIVE")
        .order_by(Authorship.order_index)
        .all()
    )


def _paper_for_span(session: Any, span: DocumentEvidenceSpan) -> int | None:
    document = session.get(PaperDocument, span.document_id)
    return None if document is None else document.paper_id


def _compact(value: str | None) -> str:
    return _NON_ALNUM_RE.sub("", normalize_search_text(value)).casefold()


def _surface_forms(mention: PaperCreatorMention) -> tuple[str, ...]:
    forms: list[str] = []
    for value in (
        mention.display_name,
        " ".join(part for part in (mention.first_name, mention.last_name) if part),
    ):
        normalized = normalize_search_text(value)
        if normalized and normalized not in forms:
            forms.append(normalized)
    given = normalize_search_text(mention.first_name)
    family = normalize_search_text(mention.last_name)
    if given and family:
        reversed_name = f"{family} {given}"
        initial_family = f"{given[:1]} {family}"
        family_initial = f"{family} {given[:1]}"
        for value in (reversed_name, initial_family, family_initial):
            if value not in forms:
                forms.append(value)
    return tuple(forms)


def _email_mention_matches(
    mentions: list[PaperCreatorMention], raw_text: str
) -> list[PaperCreatorMention]:
    """Map e-mail local parts conservatively to unique source author mentions."""
    matched: dict[int, PaperCreatorMention] = {}
    family_counts: dict[str, int] = {}
    for mention in mentions:
        family = _compact(mention.last_name)
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1

    for email in EMAIL_RE.findall(raw_text or ""):
        # ``EMAIL_RE`` has one capture group in the local-evidence module.
        email_value = email if isinstance(email, str) else email[0]
        local_raw = email_value.split("@", 1)[0]
        local = _compact(local_raw)
        if not local:
            continue
        local_parts = tuple(
            _compact(part)
            for part in re.split(r"[^A-Za-z0-9]+", local_raw)
            if _compact(part)
        )
        candidates: list[PaperCreatorMention] = []
        for mention in mentions:
            given = _compact(mention.first_name)
            family = _compact(mention.last_name)
            if not family:
                continue
            forms: tuple[str, ...] = ()
            if given:
                forms = (
                    given + family,
                    family + given,
                    given[:1] + family,
                    family + given[:1],
                )
            compact_match = any(len(form) >= 3 and local.startswith(form) for form in forms)
            token_match = bool(
                given
                and len(local_parts) >= 2
                and (
                    (local_parts[0].startswith(given) and local_parts[1].startswith(family))
                    or (local_parts[1].startswith(given) and local_parts[0].startswith(family))
                )
            )
            # Publisher front matter frequently uses surname-only local parts.  Accept
            # this only when the surname is unique on the paper and sufficiently long.
            family_only = (
                len(family) >= 5
                and family_counts.get(family, 0) == 1
                and (local == family or local.startswith(family))
            )
            if compact_match or token_match or family_only:
                candidates.append(mention)
        if len(candidates) == 1:
            row = candidates[0]
            matched[row.creator_mention_id] = row
    return sorted(matched.values(), key=lambda row: row.order_index)


def _direct_name_matches(mentions: list[PaperCreatorMention], raw_text: str) -> list[PaperCreatorMention]:
    normalized = normalize_search_text(raw_text)
    if not normalized:
        return []
    matches: dict[int, PaperCreatorMention] = {}
    for mention in mentions:
        forms = _surface_forms(mention)
        # Prefer full/reversed names.  Initial+family is allowed only when the family is
        # unique among direct candidates below; family-name-only matching is forbidden.
        for form in forms:
            if len(form) < 3:
                continue
            if re.search(rf"(?<!\w){re.escape(form)}(?!\w)", normalized):
                matches[mention.creator_mention_id] = mention
                break
    return sorted(matches.values(), key=lambda row: row.order_index)


def _find_mentions_in_text(
    session: Any, paper_id: int, raw_text: str
) -> list[PaperCreatorMention]:
    mentions = _paper_mentions(session, paper_id)
    emails = list(EMAIL_RE.findall(raw_text or ""))
    email_matches = _email_mention_matches(mentions, raw_text)
    direct = _direct_name_matches(mentions, raw_text)
    if emails:
        # E-mail matching is the strongest discriminator.  Direct names may fill an
        # unmapped e-mail only when the count cannot exceed the number of contact
        # addresses.  This blocks grouped-affiliation overmapping (e.g. 4 names around
        # 3 role e-mails) while retaining multi-corresponding-author recall.
        if direct and len(direct) <= len(emails):
            merged = {row.creator_mention_id: row for row in email_matches}
            merged.update({row.creator_mention_id: row for row in direct})
            return sorted(merged.values(), key=lambda row: row.order_index)
        return email_matches
    return direct


def _marker_forms(marker: str) -> tuple[str, ...]:
    marker = (marker or "").strip()
    if not marker:
        return ()
    if marker in {"*", "✉", "†", "‡", "§", "¶", "#"}:
        return (marker,)
    letter = marker.strip("() ").rstrip(")").casefold()
    if len(letter) == 1 and letter.isalpha():
        return (letter, f"{letter})", f"({letter})")
    return (marker,)


def _mention_has_marker(mention: PaperCreatorMention, text: str, marker: str) -> bool:
    raw = (text or "").casefold()
    marker_forms = _marker_forms(marker)
    if not raw or not marker_forms:
        return False
    surface_values = [
        mention.display_name,
        " ".join(part for part in (mention.first_name, mention.last_name) if part),
    ]
    for surface in surface_values:
        if not surface:
            continue
        pattern = re.compile(r"\s+".join(re.escape(part.casefold()) for part in surface.split()))
        for match in pattern.finditer(raw):
            trailer = raw[match.end() : match.end() + 28]
            for form in marker_forms:
                marker_index = trailer.find(form.casefold())
                if marker_index < 0:
                    continue
                between = trailer[:marker_index]
                # A role marker belongs to this author only when it is locally adjacent.
                # Punctuation, whitespace and numeric affiliation labels may intervene,
                # but another alphabetic token means the marker belongs to a later name
                # (e.g. ``Alice Smith and Bob Jones*`` must not mark Alice).
                if not re.search(r"[a-z]", between, re.I):
                    return True
    return False


def _marked_mentions(
    mentions: list[PaperCreatorMention], marker_spans: list[DocumentEvidenceSpan], marker: str
) -> list[PaperCreatorMention]:
    matched: dict[int, PaperCreatorMention] = {}
    for mention in mentions:
        if any(_mention_has_marker(mention, span.raw_text, marker) for span in marker_spans):
            matched[mention.creator_mention_id] = mention
    return sorted(matched.values(), key=lambda row: row.order_index)


def _upsert_mention_role_evidence(
    session: Any,
    *,
    mention: PaperCreatorMention,
    span: DocumentEvidenceSpan,
    status: str,
    score: float,
    reason_code: str,
) -> CreatorMentionRoleEvidence:
    row = (
        session.query(CreatorMentionRoleEvidence)
        .filter_by(
            creator_mention_id=mention.creator_mention_id,
            evidence_span_id=span.evidence_span_id,
            role_type="CORRESPONDING_AUTHOR",
        )
        .one_or_none()
    )
    if row is None:
        row = CreatorMentionRoleEvidence(
            creator_mention_id=mention.creator_mention_id,
            evidence_span_id=span.evidence_span_id,
            role_type="CORRESPONDING_AUTHOR",
            status=status,
            raw_value=span.raw_text,
            normalized_value=normalize_search_text(span.raw_text),
            resolver=RESOLVER_VERSION,
            reason_code=reason_code,
            score=score,
        )
        session.add(row)
    else:
        row.status = status
        row.raw_value = span.raw_text
        row.normalized_value = normalize_search_text(span.raw_text)
        row.resolver = RESOLVER_VERSION
        row.reason_code = reason_code
        row.score = score
    session.flush()
    return row


def _upsert_authorship_evidence(
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


def _project_accepted_mention_roles(session: Any, paper_id: int) -> int:
    rows = (
        session.query(CreatorMentionRoleEvidence, PaperCreatorMention)
        .join(
            PaperCreatorMention,
            PaperCreatorMention.creator_mention_id == CreatorMentionRoleEvidence.creator_mention_id,
        )
        .filter(
            PaperCreatorMention.paper_id == paper_id,
            CreatorMentionRoleEvidence.role_type == "CORRESPONDING_AUTHOR",
            CreatorMentionRoleEvidence.status == "ACCEPTED",
        )
        .all()
    )
    projected: set[int] = set()
    for role, mention in rows:
        authorship = (
            session.query(Authorship)
            .filter_by(creator_mention_id=mention.creator_mention_id, status="ACTIVE")
            .one_or_none()
        )
        if authorship is None:
            continue
        span = session.get(DocumentEvidenceSpan, role.evidence_span_id)
        if span is None or span.acceptance_status != "ACCEPTED":
            continue
        _upsert_authorship_evidence(
            session,
            authorship=authorship,
            span=span,
            evidence_type="CORRESPONDING_AUTHOR",
            status="ACCEPTED",
            score=float(role.score or 0.0),
        )
        authorship.is_corresponding_author = True
        authorship.corresponding_status = "ACCEPTED"
        projected.add(authorship.authorship_id)
    return len(projected)


def propose_authorship_evidence(session: Any, paper_id: int) -> dict[str, int]:
    document_ids = _eligible_document_ids(session, paper_id)
    empty = {
        "mention_role_accepted": 0,
        "corresponding_accepted": 0,
        "affiliation_candidates": 0,
        "unresolved": 0,
    }
    if not document_ids:
        return empty

    spans = (
        session.query(DocumentEvidenceSpan)
        .filter(
            DocumentEvidenceSpan.document_id.in_(document_ids),
            DocumentEvidenceSpan.acceptance_status == "ACCEPTED",
            DocumentEvidenceSpan.kind.in_(
                (
                    "correspondence",
                    "correspondence-candidate",
                    "contact",
                    "contact-candidate",
                    "author-marker-candidate",
                    "affiliation",
                    "affiliation-candidate",
                )
            ),
        )
        .order_by(DocumentEvidenceSpan.document_id, DocumentEvidenceSpan.page_start, DocumentEvidenceSpan.evidence_span_id)
        .all()
    )
    counts = dict(empty)
    marker_spans = [span for span in spans if span.kind == "author-marker-candidate"]
    correspondence_spans = [
        span for span in spans if span.kind in ("correspondence", "correspondence-candidate")
    ]
    contact_spans = [span for span in spans if span.kind in ("contact", "contact-candidate")]
    mentions = _paper_mentions(session, paper_id)
    accepted_mentions: set[int] = set()

    # Phase 1: explicit role semantics.  These are authoritative independently of
    # canonical identity; evidence is attached to PaperCreatorMention first.
    for span in correspondence_spans:
        if _paper_for_span(session, span) != paper_id:
            continue
        classification = classify_correspondence_text(span.raw_text)
        if classification.kind == "NOISE":
            # Preserve an explicit negative record for legacy accepted spans containing
            # publisher/service contact noise.  New extraction will not classify these
            # as correspondence, but historical evidence remains auditable rather than
            # silently disappearing.
            matches = _find_mentions_in_text(session, paper_id, span.raw_text)
            active = {
                mention.creator_mention_id: authorship
                for authorship, mention in _active_authorships(session, paper_id)
            }
            for mention in matches:
                _upsert_mention_role_evidence(
                    session,
                    mention=mention,
                    span=span,
                    status="REJECTED",
                    score=0.0,
                    reason_code=classification.reason_code,
                )
                authorship = active.get(mention.creator_mention_id)
                if authorship is not None:
                    _upsert_authorship_evidence(
                        session,
                        authorship=authorship,
                        span=span,
                        evidence_type="CORRESPONDING_AUTHOR",
                        status="REJECTED",
                        score=0.0,
                    )
            continue
        if not classification.is_role_signal:
            # Legacy extractions used to call every e-mail block correspondence.  The
            # v3 resolver deliberately consumes those as contact-only and creates no
            # role from them.
            continue
        matches = _find_mentions_in_text(session, paper_id, span.raw_text)
        marker = classification.marker or extract_leading_marker(span.raw_text)
        if not matches and marker:
            matches = _marked_mentions(mentions, marker_spans, marker)
        if matches and not _PUBLISHER_NOISE.search(span.raw_text):
            for mention in matches:
                _upsert_mention_role_evidence(
                    session,
                    mention=mention,
                    span=span,
                    status="ACCEPTED",
                    score=classification.confidence,
                    reason_code=classification.reason_code,
                )
                accepted_mentions.add(mention.creator_mention_id)
        else:
            enqueue_review(
                session,
                queue_type="UNRESOLVED_CORRESPONDING_AUTHOR",
                subject_type="evidence_span",
                subject_id=span.evidence_span_id,
                reason_code=(
                    "NO_SOURCE_AUTHOR_MAPPING" if not matches else "PUBLISHER_CONTACT_NOISE"
                ),
                payload={
                    "emails": list(classification.emails),
                    "role_signal": classification.kind,
                    "role_reason": classification.reason_code,
                    "marker": marker,
                    "matched_creator_mentions": [m.creator_mention_id for m in matches],
                },
                priority=80,
            )
            counts["unresolved"] += 1

    # Phase 2: publisher layouts such as RSC/Angew put an e-mail in an affiliation
    # block while marking the corresponding author with '*' in the author header.  This
    # is accepted only from the conjunction of two independent source signals, and only
    # when the document contains no explicit role span (which prevents a plain contact
    # address from overriding a more specific declaration).
    has_explicit_role = any(
        classify_correspondence_text(span.raw_text).is_role_signal for span in correspondence_spans
    )
    if not has_explicit_role and marker_spans:
        starred = {
            row.creator_mention_id: row
            for marker in _STRONG_AUTHOR_MARKERS
            for row in _marked_mentions(mentions, marker_spans, marker)
        }
        for span in contact_spans:
            if _paper_for_span(session, span) != paper_id:
                continue
            classification = classify_correspondence_text(span.raw_text)
            if classification.kind != "CONTACT_ONLY":
                continue
            for mention in _email_mention_matches(mentions, span.raw_text):
                if mention.creator_mention_id not in starred:
                    continue
                _upsert_mention_role_evidence(
                    session,
                    mention=mention,
                    span=span,
                    status="ACCEPTED",
                    score=0.96,
                    reason_code="AUTHOR_ROLE_MARKER_PLUS_CONTACT",
                )
                accepted_mentions.add(mention.creator_mention_id)

    # Affiliation semantics remain non-authoritative candidates on canonical authorship.
    for span in spans:
        if span.kind not in ("affiliation", "affiliation-candidate"):
            continue
        matches = _find_mentions_in_text(session, paper_id, span.raw_text)
        active = {m.creator_mention_id: a for a, m in _active_authorships(session, paper_id)}
        for mention in matches:
            authorship = active.get(mention.creator_mention_id)
            if authorship is None:
                continue
            _upsert_authorship_evidence(
                session,
                authorship=authorship,
                span=span,
                evidence_type="AFFILIATION",
                status="CANDIDATE",
                score=0.7 if len(matches) == 1 else 0.4,
            )
            counts["affiliation_candidates"] += 1

    counts["mention_role_accepted"] = len(accepted_mentions)
    counts["corresponding_accepted"] = _project_accepted_mention_roles(session, paper_id)
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
