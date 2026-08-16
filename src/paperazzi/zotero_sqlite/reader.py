from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from paperazzi.ingest.models import (
    CanonicalAttachment,
    CanonicalCollection,
    CanonicalCreator,
    CanonicalTag,
    CanonicalZoteroItem,
)

from .adapters import select_adapter


LINK_MODE_NAMES = {
    0: "imported_file",
    1: "imported_url",
    2: "linked_file",
    3: "linked_url",
    4: "embedded_image",
}

_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class ZoteroDataError(RuntimeError):
    pass


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def resolve_attachment_path(
    *,
    zotero_data_dir: Path,
    item_key: str,
    link_mode: int,
    stored_path: str | None,
) -> tuple[str | None, bool | None, str]:
    """Resolve an attachment without asking Zotero Desktop.

    Resolution is intentionally conservative. Imported storage paths are fully
    deterministic. Linked-file paths using Zotero's ``attachments:`` base-directory
    placeholder remain unresolved until Paperazzi gains an explicit linked-attachment
    base-directory configuration.
    """
    if not stored_path:
        return None, None, "missing-path"

    if stored_path.startswith("storage:"):
        relative = stored_path[len("storage:") :]
        path = zotero_data_dir / "storage" / item_key / relative
        return str(path), path.exists(), "zotero-storage"

    if link_mode == 2:
        if stored_path.startswith("attachments:"):
            return None, None, "linked-base-directory-required"
        if _WINDOWS_ABSOLUTE_RE.match(stored_path):
            # Do not silently rewrite a Windows path when running under WSL/Linux.
            # A later path-mapping layer can translate drive letters explicitly.
            return stored_path, None, "linked-windows-path-unmapped"
        path = Path(stored_path).expanduser()
        if path.is_absolute():
            return str(path), path.exists(), "linked-absolute-path"
        return stored_path, None, "linked-relative-path-unresolved"

    if link_mode == 3:
        return None, None, "linked-url-no-local-file"

    # Imported/embedded attachments should normally use storage:. Preserve any
    # non-standard value for diagnosis rather than inventing a filesystem path.
    return stored_path, None, "nonstandard-imported-path"


class ZoteroSQLiteReader:
    """Production read-only mapper for a validated Zotero SQLite snapshot."""

    def __init__(self, conn: sqlite3.Connection, zotero_data_dir: str | Path):
        conn.row_factory = sqlite3.Row
        self.conn = conn
        self.zotero_data_dir = Path(zotero_data_dir).expanduser().resolve()
        self.adapter, self.schema_identity = select_adapter(conn)

    def libraries(self) -> list[dict[str, Any]]:
        return [_row_dict(row) for row in self.conn.execute(self.adapter.libraries_sql)]

    def read_items(self, *, include_deleted: bool = False) -> list[CanonicalZoteroItem]:
        item_rows = self.conn.execute(
            self.adapter.bibliographic_items_sql(include_deleted)
        ).fetchall()
        if not item_rows:
            return []

        active_ids = {int(row["itemID"]) for row in item_rows}

        fields: dict[int, dict[str, Any]] = defaultdict(dict)
        for row in self.conn.execute(self.adapter.fields_sql):
            item_id = int(row["itemID"])
            if item_id not in active_ids:
                continue
            name = str(row["fieldName"])
            value = row["value"]
            if name in fields[item_id] and fields[item_id][name] != value:
                raise ZoteroDataError(
                    f"Item {item_id} has multiple values for field {name!r}: "
                    f"{fields[item_id][name]!r} vs {value!r}"
                )
            fields[item_id][name] = value

        creators: dict[int, list[CanonicalCreator]] = defaultdict(list)
        for row in self.conn.execute(self.adapter.creators_sql):
            item_id = int(row["itemID"])
            if item_id not in active_ids:
                continue
            creators[item_id].append(
                CanonicalCreator(
                    creator_id=int(row["creatorID"]),
                    creator_type=str(row["creatorType"]),
                    order_index=int(row["orderIndex"]),
                    first_name=row["firstName"],
                    last_name=row["lastName"],
                    field_mode=None if row["fieldMode"] is None else int(row["fieldMode"]),
                )
            )

        collections: dict[int, list[CanonicalCollection]] = defaultdict(list)
        for row in self.conn.execute(self.adapter.collections_sql):
            item_id = int(row["itemID"])
            if item_id not in active_ids:
                continue
            collections[item_id].append(
                CanonicalCollection(
                    collection_id=int(row["collectionID"]),
                    collection_key=str(row["collectionKey"]),
                    name=str(row["collectionName"]),
                    parent_collection_id=(
                        None
                        if row["parentCollectionID"] is None
                        else int(row["parentCollectionID"])
                    ),
                    parent_collection_key=(
                        None
                        if row["parentCollectionKey"] is None
                        else str(row["parentCollectionKey"])
                    ),
                    order_index=int(row["orderIndex"]),
                )
            )

        tags: dict[int, list[CanonicalTag]] = defaultdict(list)
        for row in self.conn.execute(self.adapter.tags_sql):
            item_id = int(row["itemID"])
            if item_id not in active_ids:
                continue
            tags[item_id].append(
                CanonicalTag(
                    tag_id=int(row["tagID"]),
                    name=str(row["name"]),
                    tag_type=int(row["tagType"]),
                )
            )

        attachments: dict[int, list[CanonicalAttachment]] = defaultdict(list)
        for row in self.conn.execute(self.adapter.attachments_sql):
            parent_id = int(row["parentItemID"])
            if parent_id not in active_ids:
                continue
            link_mode = int(row["linkMode"])
            stored_path = row["path"]
            item_key = str(row["key"])
            resolved_path, local_exists, resolution = resolve_attachment_path(
                zotero_data_dir=self.zotero_data_dir,
                item_key=item_key,
                link_mode=link_mode,
                stored_path=stored_path,
            )
            attachments[parent_id].append(
                CanonicalAttachment(
                    library_id=int(row["libraryID"]),
                    item_id=int(row["itemID"]),
                    item_key=item_key,
                    parent_item_id=parent_id,
                    link_mode=link_mode,
                    link_mode_name=LINK_MODE_NAMES.get(link_mode, f"unknown_{link_mode}"),
                    content_type=row["contentType"],
                    path=stored_path,
                    resolved_path=resolved_path,
                    local_exists=local_exists,
                    resolution=resolution,
                    sync_state=None if row["syncState"] is None else int(row["syncState"]),
                    storage_mod_time=(
                        None if row["storageModTime"] is None else int(row["storageModTime"])
                    ),
                    storage_hash=row["storageHash"],
                )
            )

        result: list[CanonicalZoteroItem] = []
        seen_identity: set[tuple[int, str]] = set()
        for row in item_rows:
            item_id = int(row["itemID"])
            library_id = int(row["libraryID"])
            item_key = str(row["key"])
            identity = (library_id, item_key)
            if identity in seen_identity:
                raise ZoteroDataError(
                    f"Duplicate Zotero stable identity libraryID={library_id}, key={item_key}"
                )
            seen_identity.add(identity)

            result.append(
                CanonicalZoteroItem(
                    library_id=library_id,
                    item_id=item_id,
                    item_key=item_key,
                    item_type=str(row["itemType"]),
                    zotero_version=int(row["zoteroVersion"]),
                    synced=int(row["synced"]),
                    date_added=row["dateAdded"],
                    date_modified=row["dateModified"],
                    client_date_modified=row["clientDateModified"],
                    deleted=bool(row["deleted"]),
                    fields=dict(fields.get(item_id, {})),
                    creators=tuple(creators.get(item_id, ())),
                    collections=tuple(collections.get(item_id, ())),
                    tags=tuple(tags.get(item_id, ())),
                    attachments=tuple(attachments.get(item_id, ())),
                )
            )

        return result

    def iter_items(self, *, include_deleted: bool = False) -> Iterable[CanonicalZoteroItem]:
        yield from self.read_items(include_deleted=include_deleted)


__all__ = [
    "LINK_MODE_NAMES",
    "ZoteroDataError",
    "ZoteroSQLiteReader",
    "resolve_attachment_path",
]
