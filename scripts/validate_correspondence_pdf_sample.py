#!/usr/bin/env python3
"""Regression gate over the tracked 100-PDF correspondence-layout fixture.

The full sample is parsed on every run; selected papers pin publisher/layout semantics
that previously caused false positives or false negatives.  This is an extraction gate,
not a replacement for the manually reviewed person-level precision/recall benchmark.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.local_evidence.correspondence import classify_correspondence_text  # noqa: E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa: E402

DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "phase5_5_correspondence_pdf_sample_100"

# paper_id: (must_have_role_candidate, minimum role e-mails, must_have_author_marker)
EXPECTATIONS = {
    198: (True, 1, False),   # Elsevier explicit Corresponding author
    391: (True, 1, False),   # JCP Author to whom correspondence should be addressed
    454: (False, 0, False),  # bare Electronic mail is contact only
    463: (True, 1, False),   # role sentence + e-mail split over adjacent blocks
    466: (False, 0, False),  # multiple bare Electronic mail contacts
    523: (True, 1, False),   # JCTC explicit Corresponding author
    738: (True, 2, False),   # explicit plural, two e-mails
    1053: (True, 1, True),   # MDPI: author * plus Correspondence label
    1666: (True, 1, False),  # PLOS star + bare role e-mail convention
    1713: (True, 2, True),   # Nature envelope marker, two e-mails
    1785: (True, 2, False),  # explicit Correspondence to: two named authors
    1969: (True, 1, False),  # star + name + e-mail footnote
    2002: (True, 1, True),   # MDPI affiliation e-mails + one explicit correspondence e-mail
    2012: (True, 2, False),  # explicit plural, two e-mails
    2204: (True, 0, True),   # old ACS star footnote, no e-mail in role note
    2278: (False, 0, True),  # RSC affiliation contacts; role requires author-star conjunction
    2429: (True, 1, True),   # ACS explicit star Corresponding author
    2451: (True, 2, False),  # Taylor & Francis CONTACT convention
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()

    manifest = json.loads((args.fixture_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    rows = {int(row["paper_id"]): row for row in manifest["files"]}
    failures: list[dict[str, object]] = []
    summary = {
        "pdfs": 0,
        "parse_errors": 0,
        "with_role_candidate": 0,
        "with_contact": 0,
        "with_author_marker": 0,
        "role_candidates": 0,
        "contact_candidates": 0,
    }

    extracted: dict[int, object] = {}
    for paper_id, row in sorted(rows.items()):
        path = args.fixture_dir / row["file"]
        evidence = extract_pdf_evidence(path)
        extracted[paper_id] = evidence
        summary["pdfs"] += 1
        if evidence.error:
            summary["parse_errors"] += 1
            failures.append({"paper_id": paper_id, "reason": "PARSE_ERROR", "error": evidence.error})
            continue
        summary["with_role_candidate"] += bool(evidence.correspondence_candidates)
        summary["with_contact"] += bool(evidence.contact_candidates)
        summary["with_author_marker"] += bool(evidence.author_marker_candidates)
        summary["role_candidates"] += len(evidence.correspondence_candidates)
        summary["contact_candidates"] += len(evidence.contact_candidates)
        for span in evidence.correspondence_candidates:
            classification = classify_correspondence_text(span.text)
            if not classification.is_role_signal:
                failures.append(
                    {
                        "paper_id": paper_id,
                        "reason": "NON_ROLE_LEAKED_INTO_CORRESPONDENCE_CANDIDATES",
                        "text": span.text[:500],
                        "classification": classification.kind,
                    }
                )

    for paper_id, (needs_role, minimum_emails, needs_marker) in EXPECTATIONS.items():
        evidence = extracted.get(paper_id)
        if evidence is None or getattr(evidence, "error", None):
            continue
        role_spans = list(evidence.correspondence_candidates)
        role_emails = {
            email
            for span in role_spans
            for email in classify_correspondence_text(span.text).emails
        }
        if bool(role_spans) != needs_role:
            failures.append(
                {
                    "paper_id": paper_id,
                    "reason": "ROLE_CANDIDATE_EXPECTATION",
                    "expected": needs_role,
                    "actual": bool(role_spans),
                    "role_texts": [span.text[:500] for span in role_spans],
                }
            )
        if len(role_emails) < minimum_emails:
            failures.append(
                {
                    "paper_id": paper_id,
                    "reason": "ROLE_EMAIL_COUNT",
                    "expected_minimum": minimum_emails,
                    "actual": len(role_emails),
                    "emails": sorted(role_emails),
                }
            )
        if needs_marker and not evidence.author_marker_candidates:
            failures.append(
                {
                    "paper_id": paper_id,
                    "reason": "AUTHOR_MARKER_CONTEXT_MISSING",
                }
            )

    payload = {"summary": summary, "failures": failures}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not failures and summary["pdfs"] == 100 and summary["parse_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
