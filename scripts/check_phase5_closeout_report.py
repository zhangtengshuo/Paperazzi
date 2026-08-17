#!/usr/bin/env python3
"""Validate the mandatory status contract in a Phase 5 closeout report."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

STATUS_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*([A-Z0-9_|-]+)\s*$")

REQUIRED = {
    "PHASE_5_STATUS": "PASS",
    "PAPERAZZI_MICROMAMBA_ENV": "PASS",
    "EXISTING_ANACONDA_ENV_MODIFIED": "NO",
    "PHASE_5_REAL_DB_SMOKE": "PASS",
    "PRODUCT_PATH_STATUS": "PASS",
    "ASGI_HARNESS_STATUS": "PASS",
    "FULL_CORPUS_AUTHOR_PROJECTION": "PASS",
    "BROWSER_SEMANTIC_SMOKE": "PASS",
    "EXTENDED_SEARCH_VALIDATION": "PASS",
    "REAL_UNAVAILABLE_PDF_VALIDATION": "PASS",
    "IDENTITY_REVIEW_PERFORMANCE_RECHECK": "PASS",
    "MEANINGFUL_WARNINGS_REVIEWED": "PASS",
    "ZOTERO_SOURCE_MODIFIED": "NO",
}

OPTIONAL_ALLOWED = {
    "IDENTITY_PRECISION_AUDIT": {"PASS", "NOT_RUN_OPTIONAL"},
}


def parse_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        match = STATUS_RE.match(line)
        if match:
            statuses[match.group(1)] = match.group(2)
    return statuses


def validate_report(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    statuses = parse_statuses(text)
    errors: list[str] = []
    for key, expected in REQUIRED.items():
        actual = statuses.get(key)
        if actual != expected:
            errors.append(f"{key}: expected {expected}, found {actual or 'MISSING'}")
    for key, allowed in OPTIONAL_ALLOWED.items():
        actual = statuses.get(key)
        if actual not in allowed:
            errors.append(
                f"{key}: expected one of {sorted(allowed)}, found {actual or 'MISSING'}"
            )

    # Explicit contradictions invalidate a PASS even if a status line was copied.
    lowered = text.casefold()
    contradictions = {
        "browser": (
            "manual browser interaction was not run",
            "browser smoke not run",
            "browser validation not run",
        ),
        "real unavailable PDF": (
            "unavailable-pdf validation was not run",
            "real unavailable pdf not run",
        ),
    }
    for label, phrases in contradictions.items():
        for phrase in phrases:
            if phrase in lowered:
                errors.append(f"contradiction: {label} marked incomplete: {phrase!r}")
                break
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    errors = validate_report(args.report)
    if errors:
        print("PHASE 5 CLOSEOUT REPORT: FAIL")
        for error in errors:
            print(f"- {error}")
        return 2
    print("PHASE 5 CLOSEOUT REPORT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
