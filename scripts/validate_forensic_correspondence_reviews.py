#!/usr/bin/env python3
"""Enforce the direct-PDF evidence contract for blind correspondence review.

This is intentionally stricter than the metric scorer.  It does not decide who the
corresponding author is; it proves that each claimed judgment carries per-PDF evidence
and was made against the exact file placed in the blind queue.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from pathlib import Path
from typing import Any

REVIEWED = "REVIEWED"
UNRESOLVED = "UNRESOLVED"
CORR_STATUSES = {"EXPLICIT", "NONE_EXPLICIT", "UNCERTAIN"}
NEGATIVE_CHECKS = {
    "CORRESPONDENCE_WORDING",
    "EMAIL_CONTACT",
    "AUTHOR_MARKERS",
    "FOOTNOTE_LINKS",
}
EVIDENCE_TYPES = {
    "EXPLICIT_WORDING",
    "ROLE_MARKER_LINK",
    "CONTACT_ROLE_BLOCK",
    "OTHER_EXPLICIT",
}
_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected one JSON object")
            rows.append(value)
    return rows


def _index(rows: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        if "paper_id" not in row:
            raise ValueError(f"{label}: missing paper_id")
        paper_id = int(row["paper_id"])
        if paper_id in result:
            raise ValueError(f"{label}: duplicate paper_id={paper_id}")
        result[paper_id] = row
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized(value: str | None) -> str:
    return " ".join(_WORD_RE.findall((value or "").casefold()))


def _meaningful(value: Any, minimum: int = 12) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def _load_pdf_page_text(path: Path, page_number: int) -> str | None:
    try:
        pymupdf = importlib.import_module("pymupdf")
    except ImportError:
        try:
            pymupdf = importlib.import_module("fitz")
        except ImportError:
            return None
    try:
        with pymupdf.open(path) as document:
            if page_number < 1 or page_number > len(document):
                return ""
            return document[page_number - 1].get_text("text") or ""
    except Exception:
        return None


def _validate_one(
    queue: dict[str, Any], review: dict[str, Any], expected_sequence: int
) -> list[str]:
    paper_id = int(queue["paper_id"])
    prefix = f"paper {paper_id}: "
    errors: list[str] = []

    if review.get("review_sequence") != expected_sequence:
        errors.append(prefix + f"review_sequence must be {expected_sequence}")
    if review.get("review_mode") != "DIRECT_PDF_INSPECTION":
        errors.append(prefix + "review_mode must be DIRECT_PDF_INSPECTION")
    if review.get("parser_prediction_used_for_decision") is not False:
        errors.append(prefix + "parser_prediction_used_for_decision must be false")

    raw_path = queue.get("selected_pdf_path")
    pdf = Path(str(raw_path)) if raw_path else None
    if not pdf or not pdf.is_file():
        if review.get("review_status") != UNRESOLVED:
            errors.append(prefix + "selected PDF is unavailable; review must be UNRESOLVED")
        if not _meaningful(review.get("notes"), 8):
            errors.append(prefix + "unavailable PDF requires an explanatory notes field")
        return errors

    expected_sha = str(queue.get("selected_pdf_sha256") or "")
    actual_sha = _sha256(pdf)
    if not expected_sha:
        errors.append(prefix + "blind queue is missing selected_pdf_sha256")
    elif actual_sha != expected_sha:
        errors.append(prefix + "selected PDF changed after blind queue creation (SHA-256 mismatch)")
    if review.get("reviewed_pdf_sha256") != expected_sha:
        errors.append(prefix + "reviewed_pdf_sha256 must exactly match the blind queue")

    status = review.get("review_status")
    if status not in {REVIEWED, UNRESOLVED}:
        errors.append(prefix + f"invalid review_status={status!r}")

    pages_raw = review.get("pages_inspected")
    if not isinstance(pages_raw, list) or not pages_raw or any(
        not isinstance(page, int) or page < 1 for page in pages_raw
    ):
        errors.append(prefix + "pages_inspected must be a non-empty list of positive page numbers")
        pages: list[int] = []
    else:
        pages = sorted(set(pages_raw))
        if pages != pages_raw:
            errors.append(prefix + "pages_inspected must be sorted and contain no duplicates")
    if 1 not in pages:
        errors.append(prefix + "page 1 must be inspected for every reachable PDF")

    page_count = int(queue.get("page_count") or 0)
    if page_count and any(page > page_count for page in pages):
        errors.append(prefix + "pages_inspected contains a page beyond page_count")

    if not _meaningful(review.get("author_header_observation"), 12):
        errors.append(prefix + "author_header_observation must describe what was actually seen")
    if not _meaningful(review.get("contact_footnote_observation"), 12):
        errors.append(prefix + "contact_footnote_observation must describe the inspected contact/footnote area")
    if not _meaningful(review.get("decision_rationale"), 20):
        errors.append(prefix + "decision_rationale is too short to demonstrate an independent judgment")

    corr_status = review.get("ground_truth_correspondence_status")
    if corr_status not in CORR_STATUSES:
        errors.append(prefix + f"invalid ground_truth_correspondence_status={corr_status!r}")

    gt = review.get("ground_truth_corresponding_authors")
    if not isinstance(gt, list) or not all(isinstance(name, str) for name in gt):
        errors.append(prefix + "ground_truth_corresponding_authors must be a string list")
        gt = []
    source_map = {
        _normalized(name): name
        for name in queue.get("source_authors", [])
        if isinstance(name, str)
    }
    gt_keys: set[str] = set()
    for name in gt:
        key = _normalized(name)
        if key not in source_map:
            errors.append(prefix + f"ground-truth author {name!r} is not in source_authors")
        gt_keys.add(key)

    if status == UNRESOLVED:
        if corr_status != "UNCERTAIN":
            errors.append(prefix + "UNRESOLVED review must use correspondence status UNCERTAIN")
        if gt:
            errors.append(prefix + "UNRESOLVED review must not assert corresponding-author names")
        if not _meaningful(review.get("notes"), 12):
            errors.append(prefix + "UNRESOLVED review requires a concrete reason in notes")
        return errors

    if corr_status == "EXPLICIT":
        if not gt:
            errors.append(prefix + "EXPLICIT requires at least one corresponding author")
        evidence = review.get("correspondence_evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(prefix + "EXPLICIT requires correspondence_evidence")
            evidence = []
        evidence_mapped: set[str] = set()
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                errors.append(prefix + f"evidence #{index} must be an object")
                continue
            page = item.get("page")
            quote = item.get("quote")
            evidence_type = item.get("evidence_type")
            mapped = item.get("mapped_source_authors")
            if not isinstance(page, int) or page not in pages:
                errors.append(prefix + f"evidence #{index} page must occur in pages_inspected")
                continue
            if evidence_type not in EVIDENCE_TYPES:
                errors.append(prefix + f"evidence #{index} has invalid evidence_type={evidence_type!r}")
            if not _meaningful(quote, 5):
                errors.append(prefix + f"evidence #{index} requires an exact visible quote")
            if not isinstance(mapped, list) or not mapped:
                errors.append(prefix + f"evidence #{index} must map to at least one source author")
                mapped = []
            for name in mapped:
                key = _normalized(name if isinstance(name, str) else "")
                if key not in source_map:
                    errors.append(prefix + f"evidence #{index} maps unknown source author {name!r}")
                else:
                    evidence_mapped.add(key)

            # Strong anti-hallucination check: when native PDF text is available,
            # require the claimed quote to occur on the claimed page.
            page_text = _load_pdf_page_text(pdf, page)
            if page_text is not None and _meaningful(quote, 5):
                if _normalized(str(quote)) not in _normalized(page_text):
                    errors.append(
                        prefix
                        + f"evidence #{index} quote not found in native text of PDF page {page}; "
                        "if the page is image-only/garbled, mark the case UNRESOLVED instead of inventing evidence"
                    )
        if gt_keys - evidence_mapped:
            missing = [source_map[key] for key in sorted(gt_keys - evidence_mapped) if key in source_map]
            errors.append(prefix + f"correspondence_evidence does not support all asserted authors: {missing}")

    elif corr_status == "NONE_EXPLICIT":
        if gt:
            errors.append(prefix + "NONE_EXPLICIT requires an empty corresponding-author list")
        checks = review.get("negative_checks")
        if not isinstance(checks, list):
            checks_set: set[str] = set()
        else:
            checks_set = {str(value) for value in checks}
        if checks_set != NEGATIVE_CHECKS:
            errors.append(
                prefix
                + "NONE_EXPLICIT requires exactly these negative_checks: "
                + ", ".join(sorted(NEGATIVE_CHECKS))
            )
        # A negative decision is more dangerous than a positive one because it can hide
        # silent false negatives. Force inspection of page 2 whenever it exists.
        if page_count >= 2 and 2 not in pages:
            errors.append(prefix + "NONE_EXPLICIT requires inspection of pages 1 and 2 when page 2 exists")
        evidence = review.get("correspondence_evidence")
        if evidence not in (None, []):
            errors.append(prefix + "NONE_EXPLICIT must not contain positive correspondence_evidence")

    elif corr_status == "UNCERTAIN":
        errors.append(prefix + "REVIEWED cannot use UNCERTAIN; use review_status UNRESOLVED")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-queue", type=Path, required=True)
    parser.add_argument("--reviews-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()

    queue_rows = _load_jsonl(args.blind_queue)
    review_rows = _load_jsonl(args.reviews_jsonl)
    queue = _index(queue_rows, "blind queue")
    reviews = _index(review_rows, "reviews")

    ordered_ids = [int(row["paper_id"]) for row in queue_rows]
    expected_sequence = {paper_id: index for index, paper_id in enumerate(ordered_ids, 1)}
    missing = [paper_id for paper_id in ordered_ids if paper_id not in reviews]
    unexpected = sorted(set(reviews) - set(queue))
    errors: list[str] = []
    for paper_id in ordered_ids:
        if paper_id not in reviews:
            continue
        errors.extend(_validate_one(queue[paper_id], reviews[paper_id], expected_sequence[paper_id]))
    if unexpected:
        errors.append(f"reviews contain paper IDs not present in blind queue: {unexpected}")
    if args.require_all and missing:
        errors.append(f"missing required reviews: {missing}")

    payload = {
        "queue_rows": len(queue_rows),
        "review_rows": len(review_rows),
        "missing_review_ids": missing,
        "unexpected_review_ids": unexpected,
        "evidence_contract_errors": errors,
        "pass": not errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
