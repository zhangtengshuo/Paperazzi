#!/usr/bin/env python3
"""Score production correspondence predictions against frozen forensic reviews.

This scorer refuses to run as authoritative when the forensic evidence validator did
not pass.  It never rewrites review truth and does not require conversion to the older
AI-review schema.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

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
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(value)
    return rows


def _index(rows: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        paper_id = int(row["paper_id"])
        if paper_id in result:
            raise ValueError(f"{label}: duplicate paper_id={paper_id}")
        result[paper_id] = row
    return result


def _name(value: str) -> str:
    return " ".join(_WORD_RE.findall((value or "").casefold()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--forensic-reviews", type=Path, required=True)
    parser.add_argument("--forensic-validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fail-on-fp", action="store_true")
    parser.add_argument("--min-recall", type=float, default=0.0)
    args = parser.parse_args()

    validation = json.loads(args.forensic_validation.read_text(encoding="utf-8"))
    if validation.get("pass") is not True:
        raise SystemExit(
            "forensic evidence validation did not pass; refusing to score unverified ground truth"
        )
    if validation.get("missing_review_ids"):
        raise SystemExit("forensic validation still contains missing review IDs")
    if validation.get("evidence_contract_errors"):
        raise SystemExit("forensic validation still contains evidence-contract errors")

    audits = _index(_load_jsonl(args.audit_jsonl), "audit")
    reviews = _index(_load_jsonl(args.forensic_reviews), "forensic review")

    required = {
        paper_id for paper_id, row in audits.items() if row.get("requires_pdf_review")
    }
    if required != set(reviews):
        missing = sorted(required - set(reviews))
        unexpected = sorted(set(reviews) - required)
        raise SystemExit(
            f"forensic reviews do not exactly cover reviewable audit corpus; "
            f"missing={missing}, unexpected={unexpected}"
        )

    tp = fp = fn = 0
    scored_papers = 0
    unresolved = 0
    disagreements: list[dict[str, Any]] = []

    for paper_id in sorted(required):
        audit = audits[paper_id]
        review = reviews[paper_id]
        if review.get("review_status") == "UNRESOLVED":
            unresolved += 1
            continue
        if review.get("ground_truth_correspondence_status") == "UNCERTAIN":
            unresolved += 1
            continue

        predicted = {
            _name(value): value
            for value in audit.get("machine_predicted_corresponding_authors", [])
            if isinstance(value, str)
        }
        ground_truth = {
            _name(value): value
            for value in review.get("ground_truth_corresponding_authors", [])
            if isinstance(value, str)
        }
        pk = set(predicted)
        gk = set(ground_truth)
        row_tp = len(pk & gk)
        row_fp = len(pk - gk)
        row_fn = len(gk - pk)
        tp += row_tp
        fp += row_fp
        fn += row_fn
        scored_papers += 1

        if row_fp or row_fn:
            disagreements.append(
                {
                    "paper_id": paper_id,
                    "title": audit.get("title"),
                    "venue": audit.get("venue"),
                    "pdf_path": audit.get("selected_pdf_path"),
                    "predicted": list(predicted.values()),
                    "ground_truth": list(ground_truth.values()),
                    "false_positive_authors": [
                        predicted[key] for key in sorted(pk - gk)
                    ],
                    "false_negative_authors": [
                        ground_truth[key] for key in sorted(gk - pk)
                    ],
                    "forensic_pages_inspected": review.get("pages_inspected", []),
                    "forensic_correspondence_evidence": review.get(
                        "correspondence_evidence", []
                    ),
                    "forensic_rationale": review.get("decision_rationale"),
                    "parser_flags": audit.get("flags", []),
                }
            )

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    payload = {
        "ground_truth_contract": "FORENSIC_VALIDATOR_PASS_REQUIRED",
        "audit_rows": len(audits),
        "review_required": len(required),
        "forensic_review_rows": len(reviews),
        "unresolved_reviews": unresolved,
        "correspondence": {
            "scored_papers": scored_papers,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "false_positive_zero": fp == 0,
        },
        "disagreements": disagreements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    failed = False
    if args.fail_on_fp and fp:
        failed = True
    if recall < args.min_recall:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
