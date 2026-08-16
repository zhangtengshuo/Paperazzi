from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CanonicalCreator:
    creator_id: int
    creator_type: str
    order_index: int
    first_name: str | None
    last_name: str | None
    field_mode: int | None = None

    @property
    def display_name(self) -> str:
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        if self.field_mode == 1:
            return last or first
        return " ".join(part for part in (first, last) if part)


@dataclass(frozen=True, slots=True)
class CanonicalCollection:
    collection_id: int
    collection_key: str
    name: str
    parent_collection_id: int | None
    parent_collection_key: str | None
    order_index: int


@dataclass(frozen=True, slots=True)
class CanonicalTag:
    tag_id: int
    name: str
    tag_type: int


@dataclass(frozen=True, slots=True)
class CanonicalAttachment:
    library_id: int
    item_id: int
    item_key: str
    parent_item_id: int | None
    link_mode: int
    link_mode_name: str
    content_type: str | None
    path: str | None
    resolved_path: str | None
    local_exists: bool | None
    resolution: str
    sync_state: int | None = None
    storage_mod_time: int | None = None
    storage_hash: str | None = None

    @property
    def zotero_identity(self) -> str:
        return f"zotero:{self.library_id}:{self.item_key}"


@dataclass(frozen=True, slots=True)
class CanonicalZoteroItem:
    library_id: int
    item_id: int
    item_key: str
    item_type: str
    zotero_version: int
    synced: int
    date_added: str | None
    date_modified: str | None
    client_date_modified: str | None
    deleted: bool
    fields: dict[str, Any] = field(default_factory=dict)
    creators: tuple[CanonicalCreator, ...] = ()
    collections: tuple[CanonicalCollection, ...] = ()
    tags: tuple[CanonicalTag, ...] = ()
    attachments: tuple[CanonicalAttachment, ...] = ()

    @property
    def zotero_identity(self) -> str:
        """Stable Zotero-side identity within the local library set."""
        return f"zotero:{self.library_id}:{self.item_key}"

    @property
    def title(self) -> str | None:
        value = self.fields.get("title")
        return None if value is None else str(value)

    @property
    def doi(self) -> str | None:
        value = self.fields.get("DOI")
        return None if value is None else str(value)

    def stable_payload(self) -> dict[str, Any]:
        """Semantic payload used for deterministic scan-to-scan content hashing.

        Deliberately excluded:
        - SQLite-internal numeric IDs;
        - Zotero sync/version counters;
        - dateAdded/dateModified/clientDateModified;
        - deleted status (tracked separately by the diff engine);
        - local attachment existence/resolution state;
        - attachment sync timestamps/state.

        This prevents a pure Zotero sync or local file download from masquerading as a
        bibliographic metadata change. Attachment storage hashes remain included so a
        genuinely replaced attachment can be detected.
        """
        return {
            "library_id": self.library_id,
            "item_key": self.item_key,
            "item_type": self.item_type,
            "fields": dict(sorted(self.fields.items())),
            "creators": [
                {
                    "creator_type": c.creator_type,
                    "order_index": c.order_index,
                    "first_name": c.first_name,
                    "last_name": c.last_name,
                    "field_mode": c.field_mode,
                }
                for c in self.creators
            ],
            "collections": [
                {
                    "collection_key": c.collection_key,
                    "name": c.name,
                    "parent_collection_key": c.parent_collection_key,
                    "order_index": c.order_index,
                }
                for c in self.collections
            ],
            "tags": [
                {"name": t.name, "tag_type": t.tag_type}
                for t in sorted(self.tags, key=lambda x: (x.name.casefold(), x.tag_type))
            ],
            "attachments": [
                {
                    "library_id": a.library_id,
                    "item_key": a.item_key,
                    "link_mode": a.link_mode,
                    "link_mode_name": a.link_mode_name,
                    "content_type": a.content_type,
                    "path": a.path,
                    "storage_hash": a.storage_hash,
                }
                for a in sorted(self.attachments, key=lambda x: (x.library_id, x.item_key))
            ],
        }

    def content_hash(self) -> str:
        payload = json.dumps(
            self.stable_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["zotero_identity"] = self.zotero_identity
        result["content_hash"] = self.content_hash()
        return result
