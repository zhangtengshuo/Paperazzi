"""Deterministic, locale-agnostic name normalization for Phase 4 blocking.

Normalization creates search/blocking features only. It never asserts identity.
The sourced display string is retained separately from every derived blocking form.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s'-]+", re.UNICODE)


@dataclass(frozen=True)
class NameFeatures:
    raw_name: str
    normalized_name: str
    given_name: str | None
    family_name: str | None
    initials: str | None
    search_form: str
    family_given: str
    given_family: str


def _raw_component(value: str | None) -> str:
    return "" if value is None else value.strip()


def _clean_component(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).strip()
    value = _PUNCT_RE.sub(" ", value)
    value = value.replace("_", " ")
    return _SPACE_RE.sub(" ", value).strip()


def normalize_name(value: str | None) -> str:
    """Return the case-folded NFKC blocking form."""
    return _clean_component(value).casefold()


def normalize_search_text(value: str | None) -> str:
    """Return a diacritic-insensitive search form while preserving non-Latin text."""
    normalized = normalize_name(value)
    decomposed = unicodedata.normalize("NFKD", normalized)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return _SPACE_RE.sub(" ", stripped).strip()


def _initials(given_name: str) -> str:
    parts = [part for part in re.split(r"[\s'-]+", given_name) if part]
    return "".join(part[0].casefold() for part in parts if part)


def name_features(
    first_name: str | None,
    last_name: str | None,
    display_name: str | None = None,
) -> NameFeatures:
    raw_given = _raw_component(first_name)
    raw_family = _raw_component(last_name)
    raw_display = _raw_component(display_name)

    given = _clean_component(first_name)
    family = _clean_component(last_name)

    if raw_given or raw_family:
        raw = " ".join(part for part in (raw_given, raw_family) if part)
    else:
        raw = raw_display

    normalized = normalize_name(raw)
    given_norm = normalize_name(given) or None
    family_norm = normalize_name(family) or None
    initials = _initials(given_norm) if given_norm else None
    family_given = " ".join(part for part in (family_norm or "", given_norm or "") if part)
    given_family = " ".join(part for part in (given_norm or "", family_norm or "") if part)

    return NameFeatures(
        raw_name=raw,
        normalized_name=normalized,
        given_name=given_norm,
        family_name=family_norm,
        initials=initials,
        search_form=normalize_search_text(raw),
        family_given=family_given,
        given_family=given_family,
    )


def compatible_initials(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left == right or left.startswith(right) or right.startswith(left)
