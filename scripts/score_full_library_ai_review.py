#!/usr/bin/env python3
"""Validate and score local-AI full-library review annotations."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
ALLOWED_REVIEW_STATUS = {"REVIEWED", "UNRESOLVED"}
ALLOWED_CORRESPONDENCE_STATUS = {"EXPLICIT", "NONE_EXPLICIT", "UNCERTAIN"}
ALLOWED_TRIAGE_STATUS = {"OK", "BAD", "NOT_APPLICABLE", "UNCERTAIN"}


def _normalize_name(value: str) -> str:
    return "".join(_WORD_RE.findall((value or "").casefold()))


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
                raise ValueError(f"{path}:{line_number}: expected one JSON object per line")
            rows.append(value)
    return rows


def _index_unique(rows: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in rows:
        if "paper_id" not in row:
            raise ValueError(f"{label}: row missing paper_id")
        paper_id = int(row["paper_id"])
        if paper_id in indexed:
            raise ValueError(f"{label}: duplicate paper_id={paper_id}")
        indexed[paper_id] = row
    return indexed


def _validate_review(review: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paper_id = int(audit["paper_id"])
    status = review.get("review_status")
    if status not in ALLOWED_REVIEW_STATUS:
        errors.append(f"paper {paper_id}: invalid review_status={status!r}")
    if status == "UNRESOLVED":
        return errors

    correspondence_status = review.get("ground_truth_correspondence_status")
    if correspondence_status not in ALLOWED_CORRESPONDENCE_STATUS:
        errors.append(
            f"paper {paper_id}: invalid ground_truth_correspondence_status={correspondence_status!r}"
        )
    gt_names = review.get("ground_truth_corresponding_authors")
    if not isinstance(gt_names, list) or not all(isinstance(name, str) for name in gt_names):
        errors.append(f"paper {paper_id}: ground_truth_corresponding_authors must be a string list")
        gt_names = []
    if correspondence_status == "NONE_EXPLICIT" and gt_names:
        errors.append(f"paper {paper_id}: NONE_EXPLICIT must have an empty ground-truth list")
    if correspondence_status == "EXPLICIT" and not gt_names:
        errors.append(f"paper {paper_id}: EXPLICIT must name at least one source author")

    source_names = {
        _normalize_name(name): name
        for name in audit.get("source_authors", [])
        if isinstance(name, str)
    }
    for name in gt_names:
        if _normalize_name(name) not in source_names:
            errors.append(
                f"paper {paper_id}: ground-truth author {name!r} is not an exact normalized source-author name; "
                "copy the source_authors spelling from the audit row"
            )

    for field in (
        "primary_document_status",
        "text_extraction_status",
        "author_header_status",
        "reference_section_status",
    ):
        value = review.get(field)
        if value not in ALLOWED_TRIAGE_STATUS:
            errors.append(f"paper {paper_id}: invalid {field}={value!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--reviews-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-all-reviewed", action="store_true")
    parser.add_argument("--fail-on-fp", action="store_true")
    parser.add_argument("--min-recall", type=float, default=0.0)
    args = parser.parse_args()

    audits = _index_unique(_load_jsonl(args.audit_jsonl), "audit")
    reviews = _index_unique(_load_jsonl(args.reviews_jsonl), "review")
    required_ids = {
        paper_id for paper_id, row in audits.items() if row.get("requires_pdf_review")
    }
    missing = sorted(required_ids - set(reviews))
    unexpected = sorted(set(reviews) - set(audits))
    validation_errors: list[str] = []
    for paper_id in sorted(set(audits) & set(reviews)):
        validation_errors.extend(_validate_review(reviews[paper_id], audits[paper_id]))

    tp = fp = fn = 0
    scored_papers = 0
    unresolved = 0
    disagreements: list[dict[str, Any]] = []
    quality_counts: dict[str, Counter[str]] = {
        "primary_document_status": Counter(),
        "text_extraction_status": Counter(),
        "author_header_status": Counter(),
        "reference_section_status": Counter(),
    }

    for paper_id in sorted(required_ids & set(reviews)):
        audit = audits[paper_id]
        review = reviews[paper_id]
        if review.get("review_status") == "UNRESOLVED":
            unresolved += 1
            continue
        for field, counter in quality_counts.items():
            counter[str(review.get(field))] += 1

        gt_status = review.get("ground_truth_correspondence_status")
        if gt_status == "UNCERTAIN":
            continue
        predicted = {
            _normalize_name(name): name
            for name in audit.get("machine_predicted_corresponding_authors", [])
            if isinstance(name, str)
        }
        ground_truth = {
            _normalize_name(name): name
            for name in review.get("ground_truth_corresponding_authors", [])
            if isinstance(name, str)
        }
        predicted_keys = set(predicted)
        gt_keys = set(ground_truth)
        this_tp = len(predicted_keys & gt_keys)
        this_fp = len(predicted_keys - gt_keys)
        this_fn = len(gt_keys - predicted_keys)
        tp += this_tp
        fp += this_fp
        fn += this_fn
        scored_papers += 1
        if this_fp or this_fn:
            disagreements.append(
                {
                    "paper_id": paper_id,
                    "title": audit.get("title"),
                    "pdf_path": audit.get("selected_pdf_path"),
                    "predicted": list(predicted.values()),
                    "ground_truth": list(ground_truth.values()),
                    "fp": [predicted[key] for key in sorted(predicted_keys - gt_keys)],
                    "fn": [ground_truth[key] for key in sorted(gt_keys - predicted_keys)],
                    "flags": audit.get("flags", []),
                    "review_notes": review.get("notes", ""),
                }
            )

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    payload = {
        "audit_rows": len(audits),
        "review_required": len(required_ids),
        "reviews_present": len(reviews),
        "missing_review_ids": missing,
        "unexpected_review_ids": unexpected,
        "unresolved_reviews": unresolved,
        "validation_errors": validation_errors,
        "correspondence": {
            "scored_papers": scored_papers,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "false_positive_zero": fp == 0,
        },
        "other_quality_checks": {
            field: dict(sorted(counter.items())) for field, counter in quality_counts.items()
        },
        "disagreements": disagreements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    failed = bool(validation_errors or unexpected)
    if args.require_all_reviewed and missing:
        failed = True
    if args.fail_on_fp and fp:
        failed = True
    if recall < args.min_recall:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
