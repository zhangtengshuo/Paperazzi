#!/usr/bin/env python3
"""Build a parser-blind full-library correspondence review queue.

The input is the deterministic full-library audit JSONL.  The output deliberately
removes every parser-derived correspondence hint.  A reviewer receives only source
bibliographic identity, source-author names, and the exact PDF it must inspect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "correspondence-blind-review-v1"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(value)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    source_rows = _load_jsonl(args.audit_jsonl)
    seen: set[int] = set()
    queue: list[dict[str, Any]] = []
    missing_paths: list[int] = []

    for source in source_rows:
        if not source.get("requires_pdf_review"):
            continue
        paper_id = int(source["paper_id"])
        if paper_id in seen:
            raise ValueError(f"duplicate paper_id={paper_id} in audit input")
        seen.add(paper_id)

        raw_path = source.get("selected_pdf_path")
        pdf_path = Path(str(raw_path)) if raw_path else None
        exists = bool(pdf_path and pdf_path.is_file())
        digest = _sha256(pdf_path) if exists and pdf_path is not None else None
        if not exists:
            missing_paths.append(paper_id)

        # IMPORTANT: do not add machine predictions, correspondence candidates,
        # contact candidates, author markers, risk flags, or extracted front matter.
        queue.append(
            {
                "schema_version": SCHEMA_VERSION,
                "paper_id": paper_id,
                "title": source.get("title"),
                "doi": source.get("doi"),
                "venue": source.get("venue"),
                "publication_year": source.get("publication_year"),
                "source_authors": list(source.get("source_authors") or []),
                "selected_document_id": source.get("selected_document_id"),
                "selected_pdf_path": raw_path,
                "selected_pdf_exists": exists,
                "selected_pdf_sha256": digest,
                "page_count": source.get("page_count"),
            }
        )

    # Do not preserve risk ordering from the diagnostic audit: paper_id order avoids
    # leaking which cases the production parser considers suspicious.
    queue.sort(key=lambda row: int(row["paper_id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in queue:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "queue_rows": len(queue),
        "pdfs_present": sum(bool(row["selected_pdf_exists"]) for row in queue),
        "missing_pdf_ids": missing_paths,
        "blind_fields_excluded": [
            "machine_predicted_corresponding_authors",
            "role_candidates",
            "contact_candidates",
            "author_marker_candidates",
            "front_matter_preview",
            "flags",
            "risk_score",
            "severity",
        ],
    }
    summary_path = args.summary or args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not missing_paths else 2


if __name__ == "__main__":
    raise SystemExit(main())
