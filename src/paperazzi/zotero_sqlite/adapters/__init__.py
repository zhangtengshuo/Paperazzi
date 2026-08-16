from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .userdata_125 import Userdata125Adapter


class UnsupportedZoteroSchema(RuntimeError):
    """Raised when the local Zotero internal schema has no validated adapter."""


@dataclass(frozen=True, slots=True)
class SchemaIdentity:
    versions: dict[str, int]
    adapter_name: str


def read_schema_versions(conn: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = conn.execute("SELECT schema, version FROM version").fetchall()
    except sqlite3.DatabaseError as exc:
        raise UnsupportedZoteroSchema(f"Cannot read Zotero version table: {exc}") from exc
    return {str(row[0]): int(row[1]) for row in rows}


def select_adapter(conn: sqlite3.Connection) -> tuple[Userdata125Adapter, SchemaIdentity]:
    versions = read_schema_versions(conn)
    userdata = versions.get("userdata")
    global_schema = versions.get("globalSchema")

    if userdata == 125 and global_schema == 42:
        adapter = Userdata125Adapter()
        adapter.validate(conn)
        return adapter, SchemaIdentity(versions=versions, adapter_name=adapter.name)

    raise UnsupportedZoteroSchema(
        "Unsupported Zotero internal schema: "
        f"userdata={userdata!r}, globalSchema={global_schema!r}. "
        "Paperazzi refuses to guess. Run the Phase 1 probe and add/validate a new adapter."
    )


__all__ = [
    "SchemaIdentity",
    "UnsupportedZoteroSchema",
    "read_schema_versions",
    "select_adapter",
]
