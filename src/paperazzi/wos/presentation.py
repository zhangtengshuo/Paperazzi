"""Presentation-time reconciliation of Zotero source authors with WoS author roles.

This module does not rewrite Authorship or WoS data.  It computes an effective web/API
projection with explicit provenance.  A complete WoS author mapping may replace PDF-
derived correspondence labels for presentation; partial mappings only add evidence.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", text)


def _token_match(a: str, b: str) -> bool:
    return a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))


def compatible_person_name(a: str | None, b: str | None) -> bool:
    """Order-insensitive conservative name compatibility with initial expansion."""
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return False
    if sorted(left) == sorted(right):
        return True
    # Require the same token count for automatic presentation mapping.  This avoids
    # collapsing distinct people merely because they share a surname or one initial.
    if len(left) != len(right):
        return False
    used: set[int] = set()
    for token in left:
        matches = [i for i, other in enumerate(right) if i not in used and _token_match(token, other)]
        if len(matches) != 1:
            return False
        used.add(matches[0])
    return True


def _wos_corresponding_orders(record: dict[str, Any]) -> set[int]:
    authors = record.get("authors", [])
    corr = record.get("corresponding_authors", [])
    orders: set[int] = set()
    for c in corr:
        cname = c.get("full_name") or c.get("au_name") or c.get("raw_member_name")
        matches = [
            int(a["order_index"])
            for a in authors
            if compatible_person_name(cname, a.get("full_name") or a.get("au_name"))
        ]
        if len(matches) == 1:
            orders.add(matches[0])
    return orders


def apply_wos_effective_roles(
    paper_detail: dict[str, Any],
    wos_detail: dict[str, Any],
) -> dict[str, Any]:
    """Apply WoS correspondence roles to a paper API projection, with provenance."""
    authors = paper_detail.get("authors") or []
    for author in authors:
        author.setdefault("source_roles", list(author.get("roles") or []))
        if "CORRESPONDING" in (author.get("roles") or []):
            author.setdefault("corresponding_role_source", "LOCAL_PDF_OR_EXISTING_PAPERAZZI")

    paper_detail["wos"] = {
        "status": wos_detail.get("status", "WOS_NOT_CHECKED"),
        "wos_ut": wos_detail.get("wos_ut"),
        "match_method": wos_detail.get("match_method"),
        "match_score": wos_detail.get("match_score"),
    }
    if wos_detail.get("status") != "WOS_MATCHED" or not wos_detail.get("record"):
        paper_detail["correspondence_resolution"] = {
            "effective_source": "LOCAL_PDF_OR_EXISTING_PAPERAZZI",
            "wos_status": wos_detail.get("status", "WOS_NOT_CHECKED"),
            "mapping_status": "NOT_APPLICABLE",
        }
        return paper_detail

    record = wos_detail["record"]
    wos_authors = record.get("authors", [])
    full_mapping = len(authors) == len(wos_authors) and all(
        int(source.get("order_index", -1)) == int(wos.get("order_index", -2))
        and compatible_person_name(source.get("source_name"), wos.get("full_name") or wos.get("au_name"))
        for source, wos in zip(authors, wos_authors)
    )
    corr_orders = _wos_corresponding_orders(record)

    if full_mapping:
        for author in authors:
            roles = [r for r in (author.get("roles") or []) if r != "CORRESPONDING" and r != "ORDINARY"]
            if int(author.get("order_index", -1)) in corr_orders:
                roles.append("CORRESPONDING")
                author["corresponding_role_source"] = "WOS_RP"
            else:
                author["corresponding_role_source"] = "WOS_RP_NEGATIVE"
            if not roles:
                roles = ["ORDINARY"]
            author["roles"] = roles
        mapping_status = "COMPLETE"
        effective_source = "WOS_RP"
    else:
        # Partial mapping is deliberately additive: do not erase earlier PDF evidence.
        mapped = 0
        corr_names = [
            c.get("full_name") or c.get("au_name") or c.get("raw_member_name")
            for c in record.get("corresponding_authors", [])
        ]
        for author in authors:
            matches = [name for name in corr_names if compatible_person_name(author.get("source_name"), name)]
            if len(matches) == 1:
                roles = [r for r in (author.get("roles") or []) if r != "ORDINARY"]
                if "CORRESPONDING" not in roles:
                    roles.append("CORRESPONDING")
                author["roles"] = roles or ["CORRESPONDING"]
                author["corresponding_role_source"] = "WOS_RP_PARTIAL_MAP"
                mapped += 1
        mapping_status = "PARTIAL" if mapped else "UNRESOLVED"
        effective_source = "WOS_RP_PLUS_FALLBACK" if mapped else "LOCAL_PDF_OR_EXISTING_PAPERAZZI"

    paper_detail["corresponding_authors"] = [
        a.get("source_name") for a in authors if "CORRESPONDING" in (a.get("roles") or [])
    ]
    paper_detail["correspondence_resolution"] = {
        "effective_source": effective_source,
        "wos_status": "WOS_MATCHED",
        "wos_ut": wos_detail.get("wos_ut"),
        "mapping_status": mapping_status,
        "wos_corresponding_authors": [
            c.get("full_name") or c.get("au_name") or c.get("raw_member_name")
            for c in record.get("corresponding_authors", [])
        ],
    }
    return paper_detail
