#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.local_evidence.pdf import PdfEvidence, extract_pdf_evidence
from paperazzi.zotero_sqlite.probe import create_snapshot, open_readonly, resolve_db_path
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader


YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
ANCHOR_TITLE_SUBSTRINGS = (
    "corresponding orbitals and the nonorthogonality problem",
    "qutip-bofin",
    "theory of projections with nonorthogonal basis sets",
    "on the foundations of combinatorial theory",
    "the generalized slater",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    return cleaned.strip("_") or "pdf-evidence"


def item_year(item) -> int | None:
    for key in ("date", "year"):
        value = item.fields.get(key)
        if not value:
            continue
        match = YEAR_RE.search(str(value))
        if match:
            return int(match.group(0))
    return None


def year_bucket(year: int | None) -> str:
    if year is None:
        return "unknown"
    if year < 1980:
        return "pre-1980"
    if year < 2000:
        return "1980-1999"
    if year < 2010:
        return "2000-2009"
    if year < 2020:
        return "2010-2019"
    return "2020+"


def local_pdf_records(reader: ZoteroSQLiteReader):
    records = []
    for item in reader.read_items():
        for attachment in item.attachments:
            if attachment.content_type != "application/pdf":
                continue
            if attachment.local_exists is not True or not attachment.resolved_path:
                continue
            records.append((item, attachment))
    return records


def select_records(records, limit: int | None):
    if limit is None or limit >= len(records):
        return sorted(records, key=lambda pair: (pair[0].library_id, pair[0].item_key, pair[1].item_key))

    selected = []
    selected_keys: set[tuple[int, str, str]] = set()

    def add(pair):
        item, attachment = pair
        key = (item.library_id, item.item_key, attachment.item_key)
        if key not in selected_keys:
            selected_keys.add(key)
            selected.append(pair)

    # Keep known real-world layouts from reconnaissance whenever they are present.
    for pair in records:
        title = (pair[0].title or "").casefold()
        if any(anchor in title for anchor in ANCHOR_TITLE_SUBSTRINGS):
            add(pair)

    buckets = {}
    for pair in records:
        buckets.setdefault(year_bucket(item_year(pair[0])), []).append(pair)
    for values in buckets.values():
        values.sort(key=lambda pair: (pair[0].library_id, pair[0].item_key, pair[1].item_key))

    remaining = max(0, limit - len(selected))
    bucket_names = sorted(buckets)
    per_bucket = max(1, math.ceil(remaining / max(1, len(bucket_names))))
    for bucket in bucket_names:
        for pair in buckets[bucket][:per_bucket]:
            if len(selected) >= limit:
                break
            add(pair)

    if len(selected) < limit:
        for pair in sorted(records, key=lambda pair: (pair[0].library_id, pair[0].item_key, pair[1].item_key)):
            if len(selected) >= limit:
                break
            add(pair)

    return selected[:limit]


def truncate(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def evidence_summary(item, attachment, evidence: PdfEvidence) -> dict:
    refs = evidence.references
    reference_dois = []
    reference_samples = []
    if refs is not None:
        for entry in refs.entries:
            reference_dois.extend(entry.dois)
        reference_samples = [
            {
                "ordinal": entry.ordinal,
                "text": truncate(entry.raw_text),
                "dois": list(entry.dois),
            }
            for entry in refs.entries[:3]
        ]

    return {
        "identity": item.zotero_identity,
        "item_key": item.item_key,
        "attachment_key": attachment.item_key,
        "title": item.title,
        "year": item_year(item),
        "item_type": item.item_type,
        "pdf_path": attachment.resolved_path,
        "page_count": evidence.page_count,
        "text_status": evidence.text_status,
        "error": evidence.error,
        "pdf_metadata": {
            "title": evidence.metadata.get("title"),
            "author": evidence.metadata.get("author"),
            "subject": evidence.metadata.get("subject"),
        },
        "affiliation_candidate_count": len(evidence.affiliation_candidates),
        "affiliation_samples": [truncate(span.text) for span in evidence.affiliation_candidates[:3]],
        "correspondence_candidate_count": len(evidence.correspondence_candidates),
        "correspondence_samples": [truncate(span.text) for span in evidence.correspondence_candidates[:3]],
        "emails": list(evidence.emails),
        "references": None
        if refs is None
        else {
            "heading": refs.heading,
            "start_page": refs.start_page,
            "end_page": refs.end_page,
            "method": refs.method,
            "confidence": refs.confidence,
            "entry_count": len(refs.entries),
            "doi_count": len(set(reference_dois)),
            "entry_samples": reference_samples,
        },
    }


def build_report(reader: ZoteroSQLiteReader, *, limit: int | None) -> dict:
    available = local_pdf_records(reader)
    selected = select_records(available, limit)

    text_status = Counter()
    year_buckets = Counter()
    reference_confidence = Counter()
    reference_methods = Counter()
    samples = []
    parse_errors = 0
    with_affiliation_candidates = 0
    with_correspondence_candidates = 0
    with_emails = 0
    with_reference_heading = 0
    with_segmented_references = 0
    total_segmented_entries = 0
    total_reference_dois = 0

    for item, attachment in selected:
        year_buckets[year_bucket(item_year(item))] += 1
        evidence = extract_pdf_evidence(attachment.resolved_path)
        text_status[evidence.text_status] += 1
        if evidence.error:
            parse_errors += 1
        if evidence.affiliation_candidates:
            with_affiliation_candidates += 1
        if evidence.correspondence_candidates:
            with_correspondence_candidates += 1
        if evidence.emails:
            with_emails += 1
        if evidence.references is not None:
            with_reference_heading += 1
            reference_confidence[evidence.references.confidence] += 1
            reference_methods[evidence.references.method] += 1
            if evidence.references.entries:
                with_segmented_references += 1
                total_segmented_entries += len(evidence.references.entries)
                total_reference_dois += len(
                    {doi for entry in evidence.references.entries for doi in entry.dois}
                )
        samples.append(evidence_summary(item, attachment, evidence))

    return {
        "generated_at": utc_now(),
        "adapter": reader.schema_identity.adapter_name,
        "available_local_pdf_records": len(available),
        "selected_pdf_records": len(selected),
        "selection_limit": limit,
        "selection_year_buckets": dict(sorted(year_buckets.items())),
        "counts": {
            "parse_errors": parse_errors,
            "text_status": dict(sorted(text_status.items())),
            "with_affiliation_candidates": with_affiliation_candidates,
            "with_correspondence_candidates": with_correspondence_candidates,
            "with_emails": with_emails,
            "with_reference_heading": with_reference_heading,
            "with_segmented_references": with_segmented_references,
            "reference_confidence": dict(sorted(reference_confidence.items())),
            "reference_methods": dict(sorted(reference_methods.items())),
            "total_segmented_reference_entries": total_segmented_entries,
            "total_dois_in_segmented_references": total_reference_dois,
        },
        "samples": samples,
    }


def render_markdown(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "# Local PDF evidence validation report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Adapter: `{report['adapter']}`",
        f"- Local PDF records available: **{report['available_local_pdf_records']}**",
        f"- PDFs selected for validation: **{report['selected_pdf_records']}**",
        f"- Year buckets: `{json.dumps(report['selection_year_buckets'], sort_keys=True)}`",
        "",
        "## Extraction",
        "",
        f"- Parse errors: **{counts['parse_errors']}**",
        f"- Text status: `{json.dumps(counts['text_status'], sort_keys=True)}`",
        f"- PDFs with affiliation candidates: **{counts['with_affiliation_candidates']}**",
        f"- PDFs with correspondence candidates: **{counts['with_correspondence_candidates']}**",
        f"- PDFs with email candidates: **{counts['with_emails']}**",
        "",
        "## References",
        "",
        f"- PDFs with an exact reference-section heading: **{counts['with_reference_heading']}**",
        f"- PDFs with high/usable deterministic reference segmentation: **{counts['with_segmented_references']}**",
        f"- Reference confidence: `{json.dumps(counts['reference_confidence'], sort_keys=True)}`",
        f"- Reference methods: `{json.dumps(counts['reference_methods'], sort_keys=True)}`",
        f"- Segmented reference entries: **{counts['total_segmented_reference_entries']}**",
        f"- DOI identifiers found inside segmented entries: **{counts['total_dois_in_segmented_references']}**",
        "",
        "## Interpretation",
        "",
        "These are coverage diagnostics, not acceptance requirements for Zotero ingestion. A missing or scanned PDF simply produces less local evidence. Inspect `pdf_evidence_report.json` for per-paper evidence samples.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local PDF evidence extraction against the real Zotero library")
    parser.add_argument("--db", help="Path to the real zotero.sqlite")
    parser.add_argument("--data-dir", help="Zotero data directory; defaults to parent of --db")
    parser.add_argument("--output", default="pdf-evidence-output", help="Output root directory")
    parser.add_argument("--label", default="pdf-evidence", help="Run label")
    parser.add_argument("--limit", type=int, default=200, help="Deterministic stratified sample size")
    parser.add_argument("--all", action="store_true", help="Process every locally available PDF")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else db_path.parent
    limit = None if args.all else max(1, args.limit)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output) / f"{stamp}-{safe_label(args.label)}"
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = run_dir / "zotero_snapshot.sqlite"

    source = open_readonly(db_path)
    try:
        create_snapshot(source, snapshot_path)
    finally:
        source.close()

    snapshot = open_readonly(snapshot_path)
    try:
        reader = ZoteroSQLiteReader(snapshot, data_dir)
        report = build_report(reader, limit=limit)
    finally:
        snapshot.close()

    report["source"] = str(db_path)
    report["data_dir"] = str(data_dir)
    report["snapshot"] = str(snapshot_path)

    json_path = run_dir / "pdf_evidence_report.json"
    md_path = run_dir / "PDF_EVIDENCE_REPORT.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"PDF evidence validation completed: {run_dir}")
    print(f"  available local PDFs: {report['available_local_pdf_records']}")
    print(f"  selected PDFs: {report['selected_pdf_records']}")
    print(f"  parse errors: {report['counts']['parse_errors']}")
    print(f"  text status: {report['counts']['text_status']}")
    print(f"  reference headings: {report['counts']['with_reference_heading']}")
    print(f"  segmented references: {report['counts']['with_segmented_references']}")
    print(f"  report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
