"""Stable import surface for the independent Web of Science corpus store.

Schema v3 lives in :mod:`paperazzi.wos.store_v3`.  This wrapper performs the tiny
pre-flight migration needed by existing v2 SQLite files before v3 creates indexes on
new columns.  Existing callers continue to import ``WosCorpusStore`` from this module.
"""
from __future__ import annotations

import sqlite3

from .store_v3 import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    V3_BATCH_COLUMNS,
    V3_RECORD_COLUMNS,
    WosCorpusStore as _V3WosCorpusStore,
)


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


class WosCorpusStore(_V3WosCorpusStore):
    """Schema-v3 store with a safe in-place upgrade path from existing v2 files."""

    def initialize(self) -> None:
        if self.path.is_file():
            con = sqlite3.connect(self.path)
            try:
                record_columns = _columns(con, "wos_records") if _columns(con, "sqlite_master") else set()
                if record_columns:
                    for name, sql_type in V3_RECORD_COLUMNS.items():
                        if name not in record_columns:
                            con.execute(f"ALTER TABLE wos_records ADD COLUMN {name} {sql_type}")
                batch_columns = _columns(con, "wos_import_batches") if record_columns else set()
                if batch_columns:
                    for name, sql_type in V3_BATCH_COLUMNS.items():
                        if name not in batch_columns:
                            con.execute(f"ALTER TABLE wos_import_batches ADD COLUMN {name} {sql_type}")
                con.commit()
            finally:
                con.close()
        super().initialize()


__all__ = ["SCHEMA_SQL", "SCHEMA_VERSION", "WosCorpusStore"]
