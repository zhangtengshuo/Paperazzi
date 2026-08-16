#!/usr/bin/env python3
"""Apply explicit Phase 4 PDF anchor reviews through Paperazzi repository APIs.

The review JSON must be produced after inspecting the actual local PDF/Attempt under
PDF_EVIDENCE_AGENT.md. This importer does not infer quality from DOI hits or parser
confidence. PASS/ACCEPT_PARTIAL accepts evidence; NEEDS_OCR/UNRESOLVED completes the
run without accepting evidence.
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

import sqlalchemy as sa  # noqa: E402

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentExtractionAttempt,
    DocumentExtractionReview,
    DocumentExtractionRun,
)
from paperazzi.database.repositories import (  # noqa: E402
    accept_attempt,
    finalize_unaccepted_attempt,
    record_extraction_review,
)

DEFAULT_DB = REPO_ROOT / "data" / "phase4-validation" / "paperazzi.sqlite3"

TERMINAL_ACCEPTED = {"PASS", "ACCEPT_PARTIAL"}
TERMINAL_UNACCEPTED = {"UNRESOLVED", "NEEDS_OCR"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_json", type=Path)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    return parser.parse_args()


def validate_review(review: dict) -> None:
    required = {"attempt_id", "reviewer_type", "decision"}
    missing = required - review.keys()
    if missing:
        raise ValueError(f"review missing fields: {sorted(missing)}")
    if review["reviewer_type"] not in {"LOCAL_AI", "MANUAL"}:
        raise ValueError("reviewer_type must be LOCAL_AI or MANUAL")
    if review["decision"] not in TERMINAL_ACCEPTED | TERMINAL_UNACCEPTED:
        raise ValueError(
            "anchor importer accepts only terminal decisions; RETRY must be handled "
            "by the adaptive extraction workflow or the anchor should be replaced"
        )


def main() -> int:
    args = parse_args()
    if not args.db_path.is_file():
        raise FileNotFoundError(args.db_path)
    payload = json.loads(args.review_json.read_text(encoding="utf-8"))
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        raise ValueError("review JSON requires a non-empty reviews array")
    for review in reviews:
        validate_review(review)

    engine = create_paperazzi_engine(args.db_path)
    sf = sa.orm.sessionmaker(bind=engine)
    result = {"accepted": 0, "terminal_unaccepted": 0, "already_applied": 0}

    with sf() as session:
        for review_payload in reviews:
            attempt_id = int(review_payload["attempt_id"])
            attempt = session.get(DocumentExtractionAttempt, attempt_id)
            if attempt is None:
                raise ValueError(f"attempt_id={attempt_id} does not exist")
            run = session.get(DocumentExtractionRun, attempt.extraction_run_id)
            if run is None:
                raise ValueError(f"run for attempt_id={attempt_id} does not exist")

            latest = (
                session.query(DocumentExtractionReview)
                .filter_by(attempt_id=attempt_id)
                .order_by(DocumentExtractionReview.review_id.desc())
                .first()
            )
            if run.status == "COMPLETED":
                if latest is not None and latest.decision == review_payload["decision"]:
                    result["already_applied"] += 1
                    continue
                raise ValueError(
                    f"attempt_id={attempt_id} belongs to an already completed run "
                    "with different review state"
                )
            if latest is not None:
                raise ValueError(
                    f"attempt_id={attempt_id} already has review_id={latest.review_id}; "
                    "anchor importer does not overwrite review history"
                )

            review = record_extraction_review(
                session,
                attempt,
                reviewer_type=review_payload["reviewer_type"],
                decision=review_payload["decision"],
                problem_codes=list(review_payload.get("problem_codes") or []),
                quality_notes=review_payload.get("quality_notes"),
                section_confidence=review_payload.get("section_confidence"),
                segmentation_confidence=review_payload.get("segmentation_confidence"),
                entry_text_quality=review_payload.get("entry_text_quality"),
                review_output_hash=review_payload.get("review_output_hash"),
                reviewer_runtime=review_payload.get("reviewer_runtime"),
            )
            if review.decision in TERMINAL_ACCEPTED:
                accept_attempt(session, run, attempt)
                result["accepted"] += 1
            else:
                finalize_unaccepted_attempt(session, run, attempt)
                result["terminal_unaccepted"] += 1
        session.commit()

    print(json.dumps(result, indent=2))
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
