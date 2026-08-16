"""Read-only reconnaissance of a local Zotero SQLite database.

This module intentionally has no third-party dependencies.  It is the first
executable component of Paperazzi and exists to discover the *actual* Zotero
schema/data layout before the production importer is implemented.

Safety properties:
- the source database is opened with SQLite URI ``mode=ro``;
- ``PRAGMA query_only=ON`` is set on every read connection;
- no checkpoint/vacuum/write PRAGMA is issued against Zotero;
- optional snapshots are written only to Paperazzi-owned output directories.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


KEY_OBJECTS = (
    "items",
    "itemTypes",
    "itemData",
    "itemDataValues",
    "fields",
    "fieldsCombined",
    "creators",
    "itemCreators",
    "creatorTypes",
    "itemAttachments",
    "collections",
    "collectionItems",
    "tags",
    "itemTags",
    "deletedItems",
    "libraries",
    "version",
    "fulltextItems",
    "annotations",
)

REFERENCE_OBJECTS = (
    "version",
    "libraries",
    "itemTypes",
    "creatorTypes",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    return cleaned.strip("_") or "probe"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        head = value[:64].hex()
        suffix = "..." if len(value) > 64 else ""
        return f"<bytes:{len(value)}:{head}{suffix}>"
    return str(value)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: jsonable(row[key]) for key in row.keys()}


def default_zotero_db_candidates() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Zotero" / "zotero.sqlite",
    ]

    # Common legacy/custom-ish locations are included only as hints.  We do not
    # recursively search the home directory because that is slow and surprising.
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Zotero" / "Zotero" / "zotero.sqlite")
    else:
        candidates.extend(
            [
                home / ".zotero" / "zotero" / "zotero.sqlite",
                home / "Library" / "Application Support" / "Zotero" / "zotero.sqlite",
            ]
        )

    # Deduplicate while preserving order.
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Zotero database not found: {path}")
        return path

    candidates = default_zotero_db_candidates()
    found = [p.resolve() for p in candidates if p.is_file()]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        joined = "\n  - ".join(str(p) for p in found)
        raise RuntimeError(
            "Multiple Zotero databases were found. Pass --db explicitly:\n  - " + joined
        )

    hints = "\n  - ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        "Could not auto-discover zotero.sqlite. Pass --db /path/to/zotero.sqlite. "
        f"Checked:\n  - {hints}"
    )


def open_readonly(path: Path) -> sqlite3.Connection:
    # Path.as_uri() handles Windows drive letters and whitespace correctly.
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def create_snapshot(source: sqlite3.Connection, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing snapshot: {destination}")
    dest = sqlite3.connect(destination)
    try:
        source.backup(dest, pages=2048, sleep=0.05)
        dest.commit()
    finally:
        dest.close()


def scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    return None if row is None else row[0]


def pragma_scalar(conn: sqlite3.Connection, name: str) -> Any:
    return scalar(conn, f"PRAGMA {name}")


def source_file_state(db_path: Path) -> dict[str, Any]:
    stat = db_path.stat()
    result: dict[str, Any] = {
        "path": str(db_path),
        "size_bytes": stat.st_size,
        "mtime": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
        "sidecars": {},
    }
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            s = sidecar.stat()
            result["sidecars"][suffix] = {
                "exists": True,
                "size_bytes": s.st_size,
                "mtime": dt.datetime.fromtimestamp(s.st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
            }
        else:
            result["sidecars"][suffix] = {"exists": False}
    return result


def list_objects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'view')
        ORDER BY type, name
        """
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def object_names(objects: list[dict[str, Any]]) -> set[str]:
    return {str(obj["name"]) for obj in objects}


def object_columns(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(name)})").fetchall()
    return [row_to_dict(row) for row in rows]


def object_foreign_keys(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(f"PRAGMA foreign_key_list({quote_ident(name)})").fetchall()
    except sqlite3.DatabaseError:
        return []
    return [row_to_dict(row) for row in rows]


def safe_count(conn: sqlite3.Connection, name: str) -> int | None:
    try:
        return int(scalar(conn, f"SELECT COUNT(*) FROM {quote_ident(name)}"))
    except sqlite3.DatabaseError:
        return None


def collect_schema(conn: sqlite3.Connection, objects: list[dict[str, Any]]) -> dict[str, Any]:
    schema_objects: list[dict[str, Any]] = []
    for obj in objects:
        name = str(obj["name"])
        schema_objects.append(
            {
                "type": obj["type"],
                "name": name,
                "columns": object_columns(conn, name),
                "foreign_keys": object_foreign_keys(conn, name),
            }
        )

    canonical = json.dumps(schema_objects, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "fingerprint_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "objects": schema_objects,
    }


def fetch_limited(conn: sqlite3.Connection, name: str, limit: int = 200) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(f"SELECT * FROM {quote_ident(name)} LIMIT ?", (limit,)).fetchall()
        return [row_to_dict(row) for row in rows]
    except sqlite3.DatabaseError as exc:
        return [{"_error": str(exc)}]


def collect_reference_data(
    conn: sqlite3.Connection, names: set[str]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for name in REFERENCE_OBJECTS:
        if name in names:
            result[name] = fetch_limited(conn, name)
    return result


def collect_key_counts(conn: sqlite3.Connection, names: set[str]) -> dict[str, int | None]:
    return {name: safe_count(conn, name) for name in KEY_OBJECTS if name in names}


def collect_targeted_stats(
    conn: sqlite3.Connection, names: set[str], errors: list[str]
) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    if {"items", "itemTypes"}.issubset(names):
        try:
            rows = conn.execute(
                """
                SELECT it.typeName AS item_type, COUNT(*) AS n
                FROM items AS i
                JOIN itemTypes AS it ON it.itemTypeID = i.itemTypeID
                GROUP BY it.typeName
                ORDER BY n DESC, item_type
                """
            ).fetchall()
            stats["items_by_type"] = [row_to_dict(r) for r in rows]
        except sqlite3.DatabaseError as exc:
            errors.append(f"items_by_type: {exc}")

    if {"itemCreators", "creatorTypes"}.issubset(names):
        try:
            rows = conn.execute(
                """
                SELECT ct.creatorType AS creator_type, COUNT(*) AS n
                FROM itemCreators AS ic
                JOIN creatorTypes AS ct ON ct.creatorTypeID = ic.creatorTypeID
                GROUP BY ct.creatorType
                ORDER BY n DESC, creator_type
                """
            ).fetchall()
            stats["creator_links_by_type"] = [row_to_dict(r) for r in rows]
        except sqlite3.DatabaseError as exc:
            errors.append(f"creator_links_by_type: {exc}")

    if "itemAttachments" in names:
        try:
            cols = {c["name"] for c in object_columns(conn, "itemAttachments")}
            grouping = [col for col in ("linkMode", "contentType") if col in cols]
            if grouping:
                group_sql = ", ".join(quote_ident(col) for col in grouping)
                rows = conn.execute(
                    f"SELECT {group_sql}, COUNT(*) AS n FROM itemAttachments "
                    f"GROUP BY {group_sql} ORDER BY n DESC"
                ).fetchall()
                stats["attachments_by_mode_and_type"] = [row_to_dict(r) for r in rows]
        except sqlite3.DatabaseError as exc:
            errors.append(f"attachments_by_mode_and_type: {exc}")

    if "items" in names:
        try:
            cols = {c["name"] for c in object_columns(conn, "items")}
            if "libraryID" in cols:
                rows = conn.execute(
                    "SELECT libraryID, COUNT(*) AS n FROM items GROUP BY libraryID ORDER BY libraryID"
                ).fetchall()
                stats["items_by_library"] = [row_to_dict(r) for r in rows]
        except sqlite3.DatabaseError as exc:
            errors.append(f"items_by_library: {exc}")

    return stats


def find_field_id(conn: sqlite3.Connection, names: set[str], field_name: str) -> int | None:
    for source in ("fieldsCombined", "fields"):
        if source not in names:
            continue
        columns = {str(c["name"]) for c in object_columns(conn, source)}
        if not {"fieldID", "fieldName"}.issubset(columns):
            continue
        try:
            row = conn.execute(
                f"SELECT fieldID FROM {quote_ident(source)} WHERE fieldName = ? LIMIT 1",
                (field_name,),
            ).fetchone()
            if row is not None:
                return int(row[0])
        except sqlite3.DatabaseError:
            continue
    return None


def collect_recent_items(
    conn: sqlite3.Connection,
    names: set[str],
    limit: int,
    errors: list[str],
) -> list[dict[str, Any]]:
    required = {"items", "itemTypes", "itemData", "itemDataValues"}
    if not required.issubset(names):
        return []

    title_field_id = find_field_id(conn, names, "title")
    if title_field_id is None:
        errors.append("Could not resolve Zotero fieldID for 'title'.")
        return []

    item_columns = {str(c["name"]) for c in object_columns(conn, "items")}
    order_column = "dateModified" if "dateModified" in item_columns else "itemID"

    try:
        rows = conn.execute(
            f"""
            SELECT
                i.itemID,
                i.key,
                i.libraryID,
                it.typeName AS item_type,
                v.value AS title,
                {('i.dateAdded,' if 'dateAdded' in item_columns else 'NULL AS dateAdded,')}
                {('i.dateModified' if 'dateModified' in item_columns else 'NULL AS dateModified')}
            FROM items AS i
            JOIN itemTypes AS it ON it.itemTypeID = i.itemTypeID
            LEFT JOIN itemData AS d ON d.itemID = i.itemID AND d.fieldID = ?
            LEFT JOIN itemDataValues AS v ON v.valueID = d.valueID
            WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
            ORDER BY i.{quote_ident(order_column)} DESC
            LIMIT ?
            """,
            (title_field_id, limit),
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        errors.append(f"recent_items: {exc}")
        return []

    items = [row_to_dict(row) for row in rows]
    item_ids = [int(item["itemID"]) for item in items if item.get("itemID") is not None]
    creators_by_item: dict[int, list[dict[str, Any]]] = defaultdict(list)

    if item_ids and {"itemCreators", "creators", "creatorTypes"}.issubset(names):
        creator_cols = {str(c["name"]) for c in object_columns(conn, "creators")}
        required_creator_cols = {"creatorID", "firstName", "lastName"}
        if required_creator_cols.issubset(creator_cols):
            placeholders = ",".join("?" for _ in item_ids)
            field_mode_sql = "c.fieldMode" if "fieldMode" in creator_cols else "NULL AS fieldMode"
            try:
                creator_rows = conn.execute(
                    f"""
                    SELECT
                        ic.itemID,
                        ic.orderIndex,
                        ct.creatorType AS creator_type,
                        c.creatorID,
                        c.firstName,
                        c.lastName,
                        {field_mode_sql}
                    FROM itemCreators AS ic
                    JOIN creators AS c ON c.creatorID = ic.creatorID
                    JOIN creatorTypes AS ct ON ct.creatorTypeID = ic.creatorTypeID
                    WHERE ic.itemID IN ({placeholders})
                    ORDER BY ic.itemID, ic.orderIndex
                    """,
                    tuple(item_ids),
                ).fetchall()
                for creator_row in creator_rows:
                    data = row_to_dict(creator_row)
                    creators_by_item[int(data.pop("itemID"))].append(data)
            except sqlite3.DatabaseError as exc:
                errors.append(f"recent_item_creators: {exc}")

    for item in items:
        item["creators"] = creators_by_item.get(int(item["itemID"]), [])
    return items


def resolve_attachment_path(data_dir: Path, attachment_key: str, raw_path: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"resolution": "unresolved", "resolved_path": None, "exists": None}
    if not raw_path:
        return result

    if raw_path.startswith("storage:"):
        relative = raw_path[len("storage:") :].lstrip("/\\")
        candidate = data_dir / "storage" / attachment_key / relative
        result.update(
            resolution="zotero-storage",
            resolved_path=str(candidate),
            exists=candidate.exists(),
        )
        return result

    if raw_path.startswith("attachments:"):
        result["resolution"] = "linked-attachment-base-dir"
        return result

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        result.update(
            resolution="absolute-linked-path",
            resolved_path=str(candidate),
            exists=candidate.exists(),
        )
    return result


def collect_pdf_samples(
    conn: sqlite3.Connection,
    names: set[str],
    data_dir: Path,
    limit: int,
    errors: list[str],
) -> list[dict[str, Any]]:
    if not {"items", "itemAttachments"}.issubset(names):
        return []

    attachment_cols = {str(c["name"]) for c in object_columns(conn, "itemAttachments")}
    needed = {"itemID", "path"}
    if not needed.issubset(attachment_cols):
        errors.append("itemAttachments does not have expected itemID/path columns.")
        return []

    select_cols = [
        "i.key AS attachment_key",
        "ia.itemID",
        "ia.path",
        "ia.parentItemID" if "parentItemID" in attachment_cols else "NULL AS parentItemID",
        "ia.linkMode" if "linkMode" in attachment_cols else "NULL AS linkMode",
        "ia.contentType" if "contentType" in attachment_cols else "NULL AS contentType",
    ]
    filters: list[str] = ["LOWER(COALESCE(ia.path, '')) LIKE '%.pdf%'"]
    if "contentType" in attachment_cols:
        filters.append("LOWER(COALESCE(ia.contentType, '')) = 'application/pdf'")

    try:
        rows = conn.execute(
            f"""
            SELECT {', '.join(select_cols)}
            FROM itemAttachments AS ia
            JOIN items AS i ON i.itemID = ia.itemID
            WHERE {' OR '.join(filters)}
            ORDER BY ia.itemID DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        errors.append(f"pdf_samples: {exc}")
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        data = row_to_dict(row)
        resolution = resolve_attachment_path(
            data_dir,
            str(data.get("attachment_key") or ""),
            data.get("path") if isinstance(data.get("path"), str) else None,
        )
        data.update(resolution)
        result.append(data)
    return result


def collect_report(
    conn: sqlite3.Connection,
    source_db: Path,
    analysis_db: Path,
    snapshot_created: bool,
    run_label: str,
    quick_check: bool,
    include_content_samples: bool,
    sample_limit: int,
) -> dict[str, Any]:
    errors: list[str] = []
    objects = list_objects(conn)
    names = object_names(objects)

    metadata: dict[str, Any] = {
        "generated_at": utc_now(),
        "run_label": run_label,
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "sqlite_library_version": sqlite3.sqlite_version,
        "sqlite_python_module_version": sqlite3.version,
        "source": source_file_state(source_db),
        "analysis_database": str(analysis_db),
        "snapshot_created": snapshot_created,
        "read_mode": "mode=ro + PRAGMA query_only=ON",
    }

    pragmas: dict[str, Any] = {}
    for pragma in (
        "user_version",
        "application_id",
        "schema_version",
        "data_version",
        "journal_mode",
        "page_count",
        "page_size",
        "freelist_count",
        "foreign_keys",
        "query_only",
    ):
        try:
            pragmas[pragma] = jsonable(pragma_scalar(conn, pragma))
        except sqlite3.DatabaseError as exc:
            pragmas[pragma] = None
            errors.append(f"PRAGMA {pragma}: {exc}")

    if quick_check:
        try:
            check_rows = conn.execute("PRAGMA quick_check").fetchall()
            pragmas["quick_check"] = [jsonable(row[0]) for row in check_rows]
        except sqlite3.DatabaseError as exc:
            pragmas["quick_check"] = [f"ERROR: {exc}"]
            errors.append(f"PRAGMA quick_check: {exc}")
    else:
        pragmas["quick_check"] = ["SKIPPED"]

    schema = collect_schema(conn, objects)
    report: dict[str, Any] = {
        "probe_version": 1,
        "metadata": metadata,
        "pragmas": pragmas,
        "schema": schema,
        "key_object_counts": collect_key_counts(conn, names),
        "key_object_columns": {
            name: object_columns(conn, name) for name in KEY_OBJECTS if name in names
        },
        "reference_data": collect_reference_data(conn, names),
        "stats": collect_targeted_stats(conn, names, errors),
        "content_samples_enabled": include_content_samples,
        "recent_items": [],
        "pdf_samples": [],
        "errors": errors,
    }

    if include_content_samples:
        report["recent_items"] = collect_recent_items(conn, names, sample_limit, errors)
        report["pdf_samples"] = collect_pdf_samples(
            conn,
            names,
            source_db.parent,
            max(sample_limit * 2, 10),
            errors,
        )

    return report


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No data._\n"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(md_escape(v) for v in row) + " |")
    return "\n".join(out) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["metadata"]
    pragmas = report["pragmas"]
    lines: list[str] = [
        "# Paperazzi Zotero SQLite Probe Report",
        "",
        f"- **Generated:** `{meta['generated_at']}`",
        f"- **Label:** `{meta['run_label']}`",
        f"- **Source:** `{meta['source']['path']}`",
        f"- **Analysis DB:** `{meta['analysis_database']}`",
        f"- **Snapshot created:** `{meta['snapshot_created']}`",
        f"- **Read mode:** `{meta['read_mode']}`",
        f"- **Platform:** `{meta['platform']}`",
        f"- **Python / SQLite:** `{meta['python_version']}` / `{meta['sqlite_library_version']}`",
        "",
        "## 1. Source database state",
        "",
        f"- Size: `{meta['source']['size_bytes']}` bytes",
        f"- mtime (UTC): `{meta['source']['mtime']}`",
        "",
        markdown_table(
            ["sidecar", "exists", "size_bytes", "mtime"],
            [
                [name, info.get("exists"), info.get("size_bytes"), info.get("mtime")]
                for name, info in meta["source"]["sidecars"].items()
            ],
        ).rstrip(),
        "",
        "## 2. SQLite pragmas",
        "",
        markdown_table(
            ["pragma", "value"],
            [[key, json.dumps(value, ensure_ascii=False)] for key, value in pragmas.items()],
        ).rstrip(),
        "",
        "## 3. Schema identity",
        "",
        f"- Schema fingerprint SHA-256: `{report['schema']['fingerprint_sha256']}`",
        f"- Tables/views discovered: `{len(report['schema']['objects'])}`",
        "",
        "### Key object counts",
        "",
        markdown_table(
            ["object", "rows"],
            [[name, value] for name, value in report["key_object_counts"].items()],
        ).rstrip(),
        "",
        "### Key object columns",
        "",
    ]

    for name, columns in report["key_object_columns"].items():
        compact = ", ".join(
            f"{column.get('name')}:{column.get('type') or '?'}" for column in columns
        )
        lines.append(f"- **{name}** — `{compact}`")

    lines.extend(["", "## 4. Zotero reference data", ""])
    for name, rows in report["reference_data"].items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(rows, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    stats = report["stats"]
    lines.extend(["## 5. Aggregate statistics", ""])
    if stats.get("items_by_type"):
        lines.extend(
            [
                "### Items by type",
                "",
                markdown_table(
                    ["item_type", "n"],
                    [[r.get("item_type"), r.get("n")] for r in stats["items_by_type"]],
                ).rstrip(),
                "",
            ]
        )
    if stats.get("creator_links_by_type"):
        lines.extend(
            [
                "### Creator links by type",
                "",
                markdown_table(
                    ["creator_type", "n"],
                    [[r.get("creator_type"), r.get("n")] for r in stats["creator_links_by_type"]],
                ).rstrip(),
                "",
            ]
        )
    if stats.get("attachments_by_mode_and_type"):
        attachment_rows = stats["attachments_by_mode_and_type"]
        headers = list(attachment_rows[0].keys()) if attachment_rows else []
        lines.extend(
            [
                "### Attachments by mode/type",
                "",
                markdown_table(headers, [[r.get(h) for h in headers] for r in attachment_rows]).rstrip(),
                "",
            ]
        )
    if stats.get("items_by_library"):
        lines.extend(
            [
                "### Items by library",
                "",
                markdown_table(
                    ["libraryID", "n"],
                    [[r.get("libraryID"), r.get("n")] for r in stats["items_by_library"]],
                ).rstrip(),
                "",
            ]
        )

    lines.extend(["## 6. Content samples", ""])
    if not report["content_samples_enabled"]:
        lines.append("Content samples disabled with `--no-content-samples`.")
        lines.append("")
    else:
        recent = report.get("recent_items", [])
        lines.append("### Recent bibliographic items")
        lines.append("")
        recent_rows: list[list[Any]] = []
        for item in recent:
            creator_text = "; ".join(
                " ".join(
                    part
                    for part in [str(c.get("firstName") or ""), str(c.get("lastName") or "")]
                    if part
                )
                + f" [{c.get('creator_type')}]"
                for c in item.get("creators", [])
            )
            recent_rows.append(
                [
                    item.get("itemID"),
                    item.get("key"),
                    item.get("item_type"),
                    item.get("title"),
                    creator_text,
                    item.get("dateModified"),
                ]
            )
        lines.append(
            markdown_table(
                ["itemID", "key", "type", "title", "creators", "dateModified"], recent_rows
            ).rstrip()
        )
        lines.extend(["", "### PDF attachment samples", ""])
        pdf_rows = [
            [
                row.get("itemID"),
                row.get("attachment_key"),
                row.get("linkMode"),
                row.get("contentType"),
                row.get("path"),
                row.get("resolution"),
                row.get("exists"),
            ]
            for row in report.get("pdf_samples", [])
        ]
        lines.append(
            markdown_table(
                ["itemID", "key", "linkMode", "contentType", "stored path", "resolution", "exists"],
                pdf_rows,
            ).rstrip()
        )
        lines.append("")

    lines.extend(["## 7. Probe errors/warnings", ""])
    if report["errors"]:
        for error in report["errors"]:
            lines.append(f"- `{error}`")
    else:
        lines.append("No probe errors were recorded.")

    lines.extend(
        [
            "",
            "## What to return for Paperazzi implementation",
            "",
            "Return **this Markdown report and `report.json`** to the developer/AI doing the next Paperazzi step.",
            "Do **not** upload `zotero.sqlite` or `zotero_snapshot.sqlite` unless explicitly required.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any], run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "report.json"
    md_path = run_dir / "REPORT.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return md_path, json_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only reconnaissance of Zotero's local zotero.sqlite database."
    )
    parser.add_argument(
        "--db",
        help="Path to zotero.sqlite. If omitted, a few standard local paths are checked.",
    )
    parser.add_argument(
        "--output-dir",
        default="probe-output",
        help="Parent directory for generated reports/snapshot (default: ./probe-output).",
    )
    parser.add_argument(
        "--label",
        default="probe",
        help="Human label for the run, e.g. zotero-closed or zotero-open.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Create a transaction-consistent snapshot with SQLite Backup API and analyze the snapshot.",
    )
    parser.add_argument(
        "--quick-check",
        action="store_true",
        help="Run PRAGMA quick_check on the analysis database (read-only but potentially slower).",
    )
    parser.add_argument(
        "--no-content-samples",
        action="store_true",
        help="Do not include recent titles/creator names/PDF-path samples in the report.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of recent bibliographic items to sample (default: 10).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.sample_limit < 1 or args.sample_limit > 100:
        raise SystemExit("--sample-limit must be between 1 and 100")

    try:
        source_db = resolve_db_path(args.db)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_label = safe_label(args.label)
    run_dir = Path(args.output_dir).expanduser().resolve() / f"{timestamp}-{run_label}"
    run_dir.mkdir(parents=True, exist_ok=False)

    source_conn: sqlite3.Connection | None = None
    analysis_conn: sqlite3.Connection | None = None
    try:
        source_conn = open_readonly(source_db)
        analysis_db = source_db
        snapshot_created = False

        if args.snapshot:
            snapshot_path = run_dir / "zotero_snapshot.sqlite"
            create_snapshot(source_conn, snapshot_path)
            source_conn.close()
            source_conn = None
            analysis_db = snapshot_path
            analysis_conn = open_readonly(snapshot_path)
            snapshot_created = True
        else:
            analysis_conn = source_conn

        report = collect_report(
            analysis_conn,
            source_db=source_db,
            analysis_db=analysis_db,
            snapshot_created=snapshot_created,
            run_label=run_label,
            quick_check=args.quick_check,
            include_content_samples=not args.no_content_samples,
            sample_limit=args.sample_limit,
        )
        md_path, json_path = write_reports(report, run_dir)

        print("Paperazzi Zotero SQLite probe completed.")
        print(f"Source: {source_db}")
        print(f"Markdown report: {md_path}")
        print(f"JSON report: {json_path}")
        if snapshot_created:
            print(f"Snapshot: {analysis_db}")
        print("Return REPORT.md and report.json; do not return the SQLite snapshot.")
        return 0
    except sqlite3.DatabaseError as exc:
        print(f"SQLITE ERROR: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"OS ERROR: {exc}", file=sys.stderr)
        return 4
    finally:
        if analysis_conn is not None:
            try:
                analysis_conn.close()
            except sqlite3.Error:
                pass
        if source_conn is not None and source_conn is not analysis_conn:
            try:
                source_conn.close()
            except sqlite3.Error:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
