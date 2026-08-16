#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.zotero_sqlite.probe import create_snapshot, open_readonly, resolve_db_path
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    return cleaned.strip("_") or "reader"


def _missing_file_record(item, attachment) -> dict:
    return {
        "parent": item.zotero_identity,
        "library_id": item.library_id,
        "item_type": item.item_type,
        "title": item.title,
        "attachment_key": attachment.item_key,
        "link_mode": attachment.link_mode_name,
        "content_type": attachment.content_type,
        "stored_path": attachment.path,
        "sync_state": attachment.sync_state,
        "storage_hash": attachment.storage_hash,
        "resolution": attachment.resolution,
    }


def build_report(reader: ZoteroSQLiteReader) -> dict:
    all_items = reader.read_items(include_deleted=True)
    active = [item for item in all_items if not item.deleted]
    deleted = [item for item in all_items if item.deleted]

    item_types = Counter(item.item_type for item in active)
    libraries = Counter(item.library_id for item in active)
    creator_types: Counter[str] = Counter()
    attachment_modes: Counter[str] = Counter()
    attachment_content_types: Counter[str] = Counter()
    attachment_resolution: Counter[str] = Counter()
    local_states: Counter[str] = Counter()
    missing_by_link_mode: Counter[str] = Counter()
    missing_by_content_type: Counter[str] = Counter()
    missing_by_sync_state: Counter[str] = Counter()
    missing_by_library: Counter[str] = Counter()

    missing_title = []
    no_creators = []
    missing_local_files = []
    journal_articles = []

    for item in active:
        if not item.title or not item.title.strip():
            missing_title.append(
                {
                    "identity": item.zotero_identity,
                    "item_type": item.item_type,
                    "doi": item.doi,
                }
            )
        if not item.creators:
            no_creators.append(
                {
                    "identity": item.zotero_identity,
                    "library_id": item.library_id,
                    "item_type": item.item_type,
                    "title": item.title,
                    "doi": item.doi,
                    "date": item.fields.get("date"),
                    "publication_title": item.fields.get("publicationTitle"),
                }
            )
        if item.item_type == "journalArticle":
            journal_articles.append(item)

        for creator in item.creators:
            creator_types[creator.creator_type] += 1

        for attachment in item.attachments:
            attachment_modes[attachment.link_mode_name] += 1
            attachment_content_types[attachment.content_type or "<none>"] += 1
            attachment_resolution[attachment.resolution] += 1
            if attachment.local_exists is True:
                local_states["exists"] += 1
            elif attachment.local_exists is False:
                local_states["missing"] += 1
                missing_by_link_mode[attachment.link_mode_name] += 1
                missing_by_content_type[attachment.content_type or "<none>"] += 1
                missing_by_sync_state[str(attachment.sync_state)] += 1
                missing_by_library[str(item.library_id)] += 1
                missing_local_files.append(_missing_file_record(item, attachment))
            else:
                local_states["unresolved_or_not_applicable"] += 1

    journal_with_doi = sum(1 for item in journal_articles if item.doi and item.doi.strip())
    journal_with_authors = sum(1 for item in journal_articles if item.creators)
    journal_without_creators = [
        entry for entry in no_creators if entry["item_type"] == "journalArticle"
    ]

    deleted_attachment_count = int(
        reader.conn.execute(reader.adapter.deleted_attachments_sql).fetchone()[0]
    )

    recent = sorted(
        active,
        key=lambda item: (item.date_modified or "", item.library_id, item.item_id),
        reverse=True,
    )[:20]

    samples = []
    for item in recent:
        samples.append(
            {
                "identity": item.zotero_identity,
                "item_id": item.item_id,
                "item_type": item.item_type,
                "title": item.title,
                "doi": item.doi,
                "date_modified": item.date_modified,
                "creators": [
                    {
                        "type": c.creator_type,
                        "order": c.order_index,
                        "name": c.display_name,
                    }
                    for c in item.creators
                ],
                "collections": [
                    {
                        "key": c.collection_key,
                        "name": c.name,
                        "parent_key": c.parent_collection_key,
                    }
                    for c in item.collections
                ],
                "tags": [t.name for t in item.tags],
                "attachments": [
                    {
                        "key": a.item_key,
                        "mode": a.link_mode_name,
                        "content_type": a.content_type,
                        "stored_path": a.path,
                        "local_exists": a.local_exists,
                        "sync_state": a.sync_state,
                        "resolution": a.resolution,
                    }
                    for a in item.attachments
                ],
                "content_hash": item.content_hash(),
            }
        )

    return {
        "generated_at": utc_now(),
        "adapter": reader.schema_identity.adapter_name,
        "schema_versions": reader.schema_identity.versions,
        "libraries": reader.libraries(),
        "counts": {
            "canonical_bibliographic_total_including_deleted": len(all_items),
            "active_bibliographic_items": len(active),
            "deleted_bibliographic_items": len(deleted),
            "active_items_by_type": dict(sorted(item_types.items())),
            "active_items_by_library": {str(k): v for k, v in sorted(libraries.items())},
            "creator_links_by_type": dict(sorted(creator_types.items())),
            "attachments_by_link_mode": dict(sorted(attachment_modes.items())),
            "attachments_by_content_type": dict(sorted(attachment_content_types.items())),
            "attachments_by_resolution": dict(sorted(attachment_resolution.items())),
            "attachment_local_state": dict(sorted(local_states.items())),
            "deleted_attachments_filtered": deleted_attachment_count,
        },
        "quality": {
            "active_items_missing_title": len(missing_title),
            "active_items_without_creators": len(no_creators),
            "journal_articles": len(journal_articles),
            "journal_articles_with_doi": journal_with_doi,
            "journal_articles_with_creators": journal_with_authors,
            "journal_articles_without_creators": len(journal_without_creators),
        },
        "missing_file_breakdown": {
            "total": len(missing_local_files),
            "by_link_mode": dict(sorted(missing_by_link_mode.items())),
            "by_content_type": dict(sorted(missing_by_content_type.items())),
            "by_sync_state": dict(sorted(missing_by_sync_state.items())),
            "by_library": dict(sorted(missing_by_library.items())),
        },
        "anomalies": {
            "missing_title_items": missing_title[:100],
            "no_creator_items": no_creators[:100],
            "journal_articles_without_creators": journal_without_creators[:100],
            "missing_local_files": missing_local_files[:100],
            "anomaly_lists_truncated_at": 100,
        },
        "recent_samples": samples,
    }


def render_markdown(report: dict) -> str:
    counts = report["counts"]
    quality = report["quality"]
    missing = report["missing_file_breakdown"]
    lines = [
        "# Phase 2 — ZoteroSQLiteReader validation report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Adapter: `{report['adapter']}`",
        f"- Schema versions: `{json.dumps(report['schema_versions'], sort_keys=True)}`",
        "",
        "## Corpus",
        "",
        f"- Active bibliographic items: **{counts['active_bibliographic_items']}**",
        f"- Deleted bibliographic items retained for audit: **{counts['deleted_bibliographic_items']}**",
        f"- Libraries: `{json.dumps(counts['active_items_by_library'], sort_keys=True)}`",
        f"- Item types: `{json.dumps(counts['active_items_by_type'], sort_keys=True)}`",
        "",
        "## Mapping quality",
        "",
        f"- Active items missing title: **{quality['active_items_missing_title']}**",
        f"- Active items without creators: **{quality['active_items_without_creators']}**",
        f"- Journal articles: **{quality['journal_articles']}**",
        f"- Journal articles with DOI: **{quality['journal_articles_with_doi']}**",
        f"- Journal articles with creators: **{quality['journal_articles_with_creators']}**",
        f"- Journal articles without creators: **{quality['journal_articles_without_creators']}**",
        "",
        "## Creator roles",
        "",
        f"`{json.dumps(counts['creator_links_by_type'], sort_keys=True)}`",
        "",
        "## Attachments",
        "",
        f"- Link modes: `{json.dumps(counts['attachments_by_link_mode'], sort_keys=True)}`",
        f"- Content types: `{json.dumps(counts['attachments_by_content_type'], sort_keys=True)}`",
        f"- Resolution: `{json.dumps(counts['attachments_by_resolution'], sort_keys=True)}`",
        f"- Local state: `{json.dumps(counts['attachment_local_state'], sort_keys=True)}`",
        f"- Deleted attachment rows filtered from canonical items: **{counts['deleted_attachments_filtered']}**",
        f"- Missing local files (full count): **{missing['total']}**",
        f"- Missing by link mode: `{json.dumps(missing['by_link_mode'], sort_keys=True)}`",
        f"- Missing by content type: `{json.dumps(missing['by_content_type'], sort_keys=True)}`",
        f"- Missing by sync state: `{json.dumps(missing['by_sync_state'], sort_keys=True)}`",
        f"- Missing by library: `{json.dumps(missing['by_library'], sort_keys=True)}`",
        "",
        "## Anomalies",
        "",
        f"- Missing local file details recorded: **{len(report['anomalies']['missing_local_files'])}** (list capped at 100)",
        f"- Missing-title item details recorded: **{len(report['anomalies']['missing_title_items'])}** (list capped at 100)",
        f"- No-creator item details recorded: **{len(report['anomalies']['no_creator_items'])}** (list capped at 100)",
        "",
        "See `reader_report.json` for reconstructed samples and anomaly details.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Paperazzi's production Zotero SQLite reader")
    parser.add_argument("--db", help="Path to the real zotero.sqlite")
    parser.add_argument("--data-dir", help="Zotero data directory; defaults to parent of --db")
    parser.add_argument("--output", default="phase2-output", help="Output root directory")
    parser.add_argument("--label", default="real-library", help="Run label")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else db_path.parent
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
        report = build_report(reader)
    finally:
        snapshot.close()

    report["source"] = str(db_path)
    report["data_dir"] = str(data_dir)
    report["snapshot"] = str(snapshot_path)

    json_path = run_dir / "reader_report.json"
    md_path = run_dir / "READER_REPORT.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Phase 2 reader validation completed: {run_dir}")
    print(f"  active bibliographic items: {report['counts']['active_bibliographic_items']}")
    print(f"  deleted bibliographic items: {report['counts']['deleted_bibliographic_items']}")
    print(f"  deleted attachments filtered: {report['counts']['deleted_attachments_filtered']}")
    print(f"  missing titles: {report['quality']['active_items_missing_title']}")
    print(f"  no-creator items: {report['quality']['active_items_without_creators']}")
    print(f"  local attachment state: {report['counts']['attachment_local_state']}")
    print(f"  report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
