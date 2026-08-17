#!/usr/bin/env python3
"""Inspect the tracked 100-PDF Phase 5.5 correspondence fixture without DB writes.

The report is intentionally structural rather than a guessed ground truth.  It records
front-matter text blocks, e-mail/contact phrases, and font-span information so parser
rules can be based on observed publisher layouts.  Nothing in this script mutates a
Paperazzi database or any source PDF.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pymupdf
except ImportError:  # pragma: no cover - legacy alias
    import fitz as pymupdf

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "phase5_5_correspondence_pdf_sample_100"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
EXPLICIT_RE = re.compile(
    r"\b(?:corresponding\s+authors?|correspondence\s+(?:should|may|to|addressed)|"
    r"to\s+whom\s+correspondence)\b",
    re.I,
)
CORRESPONDENCE_WORD_RE = re.compile(r"\bcorrespond(?:ing|ence)\b", re.I)
ELECTRONIC_ADDRESS_RE = re.compile(r"\belectronic\s+(?:mail|address)\b", re.I)
EMAIL_LABEL_RE = re.compile(r"\be-?mail\s*[:.]", re.I)
MARKER_RE = re.compile(r"^[\s*†‡§¶#]+$|^[*†‡§¶#]+\d*$|^\d+[a-z]?$", re.I)
AUTHORISH_RE = re.compile(r"\b[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,3}\b")


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\u00ad", "").split())


def _block_text(block: tuple[Any, ...]) -> str:
    return _clean(str(block[4])) if len(block) >= 5 else ""


def _line_text(line: dict[str, Any]) -> str:
    return _clean("".join(str(span.get("text", "")) for span in line.get("spans", [])))


def _span_record(span: dict[str, Any], median_size: float) -> dict[str, Any]:
    text = _clean(str(span.get("text", "")))
    size = float(span.get("size") or 0.0)
    flags = int(span.get("flags") or 0)
    return {
        "text": text,
        "size": round(size, 3),
        "relative_size": round(size / median_size, 3) if median_size else None,
        "flags": flags,
        "font": span.get("font"),
        "bbox": span.get("bbox"),
        "origin": span.get("origin"),
        "marker_like": bool(MARKER_RE.fullmatch(text)) if text else False,
    }


def analyze_pdf(path: Path, *, max_front_pages: int) -> dict[str, Any]:
    case: dict[str, Any] = {
        "file": path.name,
        "page_count": 0,
        "emails": [],
        "signals": [],
        "indicator_blocks": [],
        "front_pages": [],
        "first_page_small_or_marker_spans": [],
        "error": None,
    }
    try:
        with pymupdf.open(path) as doc:
            case["page_count"] = int(doc.page_count)
            all_emails: list[str] = []
            first_page_spans: list[dict[str, Any]] = []
            for page_index in range(min(max_front_pages, doc.page_count)):
                page = doc[page_index]
                sorted_text = page.get_text("text", sort=True) or ""
                blocks = [
                    tuple(block)
                    for block in (page.get_text("blocks", sort=True) or [])
                    if len(block) < 7 or block[6] == 0
                ]
                page_dict = page.get_text("dict", sort=True) or {}
                lines: list[dict[str, Any]] = []
                for block in page_dict.get("blocks", []):
                    if block.get("type", 0) != 0:
                        continue
                    lines.extend(block.get("lines", []))
                sizes = [
                    float(span.get("size") or 0.0)
                    for line in lines
                    for span in line.get("spans", [])
                    if _clean(str(span.get("text", ""))) and float(span.get("size") or 0.0) > 0
                ]
                median_size = statistics.median(sizes) if sizes else 0.0
                line_records: list[dict[str, Any]] = []
                for line_index, line in enumerate(lines):
                    text = _line_text(line)
                    if not text:
                        continue
                    spans = [_span_record(span, median_size) for span in line.get("spans", [])]
                    rec = {
                        "line_index": line_index,
                        "text": text,
                        "bbox": line.get("bbox"),
                        "spans": spans,
                    }
                    line_records.append(rec)
                    if page_index == 0:
                        for span in spans:
                            if span["marker_like"] or (
                                span["relative_size"] is not None
                                and span["relative_size"] <= 0.72
                                and len(span["text"]) <= 8
                            ):
                                first_page_spans.append({"line": text, **span})

                page_blocks = [_block_text(block) for block in blocks]
                indicator_indices: set[int] = set()
                for index, text in enumerate(page_blocks):
                    if not text:
                        continue
                    emails = [email.lower().rstrip(".,;:)]}>\"") for email in EMAIL_RE.findall(text)]
                    all_emails.extend(emails)
                    if (
                        emails
                        or CORRESPONDENCE_WORD_RE.search(text)
                        or ELECTRONIC_ADDRESS_RE.search(text)
                        or EMAIL_LABEL_RE.search(text)
                    ):
                        indicator_indices.add(index)
                context_indices: set[int] = set()
                for index in indicator_indices:
                    context_indices.update(i for i in range(max(0, index - 2), min(len(page_blocks), index + 3)))
                for index in sorted(indicator_indices):
                    text = page_blocks[index]
                    case["indicator_blocks"].append(
                        {
                            "page": page_index,
                            "block_index": index,
                            "bbox": list(blocks[index][:4]) if len(blocks[index]) >= 4 else None,
                            "text": text,
                            "emails": [email.lower().rstrip(".,;:)]}>\"") for email in EMAIL_RE.findall(text)],
                            "explicit_correspondence": bool(EXPLICIT_RE.search(text)),
                            "correspondence_word": bool(CORRESPONDENCE_WORD_RE.search(text)),
                            "electronic_address": bool(ELECTRONIC_ADDRESS_RE.search(text)),
                            "email_label": bool(EMAIL_LABEL_RE.search(text)),
                            "context": [
                                {"block_index": i, "text": page_blocks[i]}
                                for i in sorted(context_indices)
                                if abs(i - index) <= 2
                            ],
                        }
                    )
                case["front_pages"].append(
                    {
                        "page": page_index,
                        "text": sorted_text,
                        "median_font_size": round(median_size, 3),
                        "lines": line_records,
                    }
                )

            case["emails"] = list(dict.fromkeys(all_emails))
            all_indicator_text = "\n".join(block["text"] for block in case["indicator_blocks"])
            signals: list[str] = []
            if EXPLICIT_RE.search(all_indicator_text):
                signals.append("EXPLICIT_CORRESPONDENCE")
            if CORRESPONDENCE_WORD_RE.search(all_indicator_text) and "EXPLICIT_CORRESPONDENCE" not in signals:
                signals.append("CORRESPONDENCE_WORD_ONLY")
            if ELECTRONIC_ADDRESS_RE.search(all_indicator_text):
                signals.append("ELECTRONIC_ADDRESS")
            if EMAIL_LABEL_RE.search(all_indicator_text):
                signals.append("EMAIL_LABEL")
            if case["emails"]:
                signals.append("HAS_EMAIL")
            if case["emails"] and not CORRESPONDENCE_WORD_RE.search(all_indicator_text):
                signals.append("EMAIL_WITHOUT_CORRESPONDENCE_WORD")
            if first_page_spans:
                signals.append("FIRST_PAGE_SMALL_OR_MARKER_SPANS")
            case["signals"] = signals
            case["first_page_small_or_marker_spans"] = first_page_spans[:120]
    except Exception as exc:  # diagnostics must continue across the sample
        case["error"] = f"{type(exc).__name__}: {exc}"
    return case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--max-front-pages", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.fixture_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = {row["file"]: row for row in manifest.get("files", [])}
    pdfs = sorted(args.fixture_dir.glob("*.pdf"))
    cases = []
    for path in pdfs:
        case = analyze_pdf(path, max_front_pages=max(1, args.max_front_pages))
        row = metadata.get(path.name, {})
        case.update(
            paper_id=row.get("paper_id"),
            title=row.get("title"),
            doi=row.get("doi"),
            venue=row.get("venue"),
        )
        cases.append(case)

    signal_counts = Counter(signal for case in cases for signal in case["signals"])
    venues: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        venue = (case.get("venue") or "<NO VENUE>").strip()
        for signal in case["signals"]:
            venues[venue][signal] += 1

    report = {
        "schema_version": "phase5_5_correspondence_layout_diagnostics_v1",
        "fixture_count": len(pdfs),
        "manifest_count": manifest.get("count"),
        "signal_counts": dict(signal_counts),
        "errors": sum(1 for case in cases if case["error"]),
        "venue_signal_counts": {venue: dict(counts) for venue, counts in sorted(venues.items())},
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== correspondence fixture structural diagnostics ===")
    print(json.dumps({
        "fixture_count": report["fixture_count"],
        "manifest_count": report["manifest_count"],
        "errors": report["errors"],
        "signal_counts": report["signal_counts"],
    }, indent=2, ensure_ascii=False))
    print("\n=== per-file indicator summary ===")
    for case in cases:
        fragments = []
        for block in case["indicator_blocks"][:4]:
            fragments.append(block["text"][:360])
        print(json.dumps({
            "file": case["file"],
            "paper_id": case.get("paper_id"),
            "venue": case.get("venue"),
            "signals": case["signals"],
            "emails": case["emails"],
            "fragments": fragments,
            "error": case["error"],
        }, ensure_ascii=False))
    print(f"\nFull JSON: {args.output}")
    return 0 if report["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
