"""Deterministic semantics for correspondence/contact evidence in article front matter.

An e-mail address is contact information, not by itself a corresponding-author role.
This module deliberately separates those concepts so downstream identity resolution can
preserve contact evidence without manufacturing a paper-level authorship role.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)

# These expressions state a role rather than merely providing contact information.
_EXPLICIT_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CORRESPONDING_AUTHOR", re.compile(r"\bcorresponding\s+authors?\b", re.I)),
    (
        "AUTHOR_TO_WHOM_CORRESPONDENCE",
        re.compile(
            r"\bauthors?\s+(?:to\s+whom|for)\s+correspondence(?:\s+should\s+be\s+addressed)?\b",
            re.I,
        ),
    ),
    (
        "TO_WHOM_CORRESPONDENCE",
        re.compile(r"\bto\s+whom\s+correspondence\s+should\s+be\s+addressed\b", re.I),
    ),
    (
        "CORRESPONDENCE_TO",
        re.compile(r"(?:^|[\s*†‡§¶#])correspondence\s+(?:to\b|should\s+be\s+addressed\b)", re.I),
    ),
    (
        "CORRESPONDENCE_LABEL",
        re.compile(r"(?:^|[\s*†‡§¶#])correspondence\s*:\s*", re.I),
    ),
)

# Strong publisher role markers seen in the tracked real-PDF fixture.  Unlike a bare
# asterisk in arbitrary prose, each of these is coupled to contact syntax.
_ENVELOPE_EMAIL_RE = re.compile(r"[✉✉]\s*(?:e-?mail\s*[:.]?)?", re.I)
_STAR_CONTACT_RE = re.compile(
    r"(?:^|\s)[*†‡§¶#]\s*(?:(?!present\s+address|current\s+address).){0,120}?"
    r"(?:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.I | re.S,
)
_CONTACT_HEADING_RE = re.compile(r"(?:^|\n)\s*CONTACT\s+.+?@", re.I | re.S)

_EMAIL_LABEL_RE = re.compile(r"\be-?mail\s*(?:address\s*)?[:.]", re.I)
_ELECTRONIC_MAIL_RE = re.compile(r"\belectronic\s+(?:mail|address)\s*[:.]", re.I)

_PUBLISHER_NOISE_RE = re.compile(
    r"\b(?:publisher|editorial\s+office|customer\s+service|technical\s+support|"
    r"permissions?\s+(?:department|team)|reprints?\s+department)\b",
    re.I,
)

_MARKER_PREFIX_RE = re.compile(
    r"^\s*(?P<marker>(?:[*†‡§¶#✉]+|[a-z]\)|\([a-z]\)|\d+\)))\s*",
    re.I,
)


@dataclass(frozen=True, slots=True)
class CorrespondenceClassification:
    """Semantic classification of one front-matter text span."""

    kind: str  # EXPLICIT_ROLE / ROLE_MARKER / CONTACT_ONLY / NOISE / NONE
    confidence: float
    reason_code: str
    emails: tuple[str, ...]
    marker: str | None = None

    @property
    def is_role_signal(self) -> bool:
        return self.kind in {"EXPLICIT_ROLE", "ROLE_MARKER"}


def extract_emails(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for match in EMAIL_RE.finditer(text or ""):
        value = match.group(1).lower().rstrip(".,;:)]}>\"")
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def extract_leading_marker(text: str) -> str | None:
    match = _MARKER_PREFIX_RE.match(text or "")
    return None if match is None else match.group("marker")


def classify_correspondence_text(text: str) -> CorrespondenceClassification:
    """Classify a source span without inferring person identity.

    Precision is intentionally prioritized at this layer: bare e-mail labels and AIP/JCP
    ``Electronic mail`` footnotes are contact-only unless another role statement/marker
    establishes correspondence.  A later marker-to-author linker may use such contact
    evidence in combination with independent author-header evidence.
    """
    raw = " ".join((text or "").replace("\u00ad", "").split())
    emails = extract_emails(text or "")
    marker = extract_leading_marker(text or "")
    if not raw:
        return CorrespondenceClassification("NONE", 0.0, "EMPTY", emails, marker)

    if _PUBLISHER_NOISE_RE.search(raw):
        return CorrespondenceClassification("NOISE", 0.0, "PUBLISHER_CONTACT_NOISE", emails, marker)

    for reason, pattern in _EXPLICIT_ROLE_PATTERNS:
        if pattern.search(raw):
            return CorrespondenceClassification("EXPLICIT_ROLE", 1.0, reason, emails, marker)

    if _ENVELOPE_EMAIL_RE.search(raw) and emails:
        return CorrespondenceClassification(
            "ROLE_MARKER", 0.99, "ENVELOPE_EMAIL_ROLE_MARKER", emails, "✉"
        )
    if _CONTACT_HEADING_RE.search(text or "") and emails:
        return CorrespondenceClassification(
            "ROLE_MARKER", 0.97, "PUBLISHER_CONTACT_HEADING", emails, marker
        )
    if _STAR_CONTACT_RE.search(text or "") and emails:
        return CorrespondenceClassification(
            "ROLE_MARKER", 0.96, "SYMBOL_CONTACT_ROLE_MARKER", emails, marker
        )

    if emails or _EMAIL_LABEL_RE.search(raw) or _ELECTRONIC_MAIL_RE.search(raw):
        return CorrespondenceClassification("CONTACT_ONLY", 0.0, "CONTACT_WITHOUT_ROLE", emails, marker)
    return CorrespondenceClassification("NONE", 0.0, "NO_CORRESPONDENCE_SIGNAL", emails, marker)


__all__ = [
    "CorrespondenceClassification",
    "EMAIL_RE",
    "classify_correspondence_text",
    "extract_emails",
    "extract_leading_marker",
]
