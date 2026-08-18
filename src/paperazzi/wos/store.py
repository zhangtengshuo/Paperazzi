"""Stable import surface for the independent Web of Science corpus store.

Schema v3 lives in :mod:`paperazzi.wos.store_v3`. This wrapper performs the tiny
pre-flight migration needed by existing v2 SQLite files before v3 creates indexes on
new columns. Existing callers continue to import ``WosCorpusStore`` from this module.
"""
from __future__ import annotations

import sqlite3

from .parser import CR_COMPLETE, CR_COMPLETE_ZERO, CR_MISSING_FROM_EXPORT
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
                record_columns = _columns(con, "wos_records")
                if record_columns:
                    for name, sql_type in V3_RECORD_COLUMNS.items():
                        if name not in record_columns:
                            con.execute(f"ALTER TABLE wos_records ADD COLUMN {name} {sql_type}")
                batch_columns = _columns(con, "wos_import_batches")
                if batch_columns:
                    for name, sql_type in V3_BATCH_COLUMNS.items():
                        if name not in batch_columns:
                            con.execute(f"ALTER TABLE wos_import_batches ADD COLUMN {name} {sql_type}")
                con.commit()
            finally:
                con.close()
        super().initialize()

    @staticmethod
    def _refresh_cr_status(con: sqlite3.Connection, ut: str) -> None:
        """Derive canonical CR quality from all observations without downgrading data."""
        canonical_count = int(con.execute(
            "SELECT count(*) FROM wos_cited_references WHERE source_ut=?", (ut,)
        ).fetchone()[0])
        observations = [dict(row) for row in con.execute(
            "SELECT cr_export_status,reported_reference_count FROM wos_record_observations WHERE ut=?", (ut,)
        ).fetchall()]
        statuses = {str(row["cr_export_status"]) for row in observations}
        reported = [
            int(row["reported_reference_count"])
            for row in observations
            if row["reported_reference_count"] is not None
        ]
        max_reported = max(reported) if reported else None
        complete_counts = [
            int(row["reported_reference_count"])
            for row in observations
            if row["cr_export_status"] == CR_COMPLETE
            and row["reported_reference_count"] is not None
        ]

        if canonical_count == 0:
            if max_reported is not None and max_reported > 0:
                status = CR_MISSING_FROM_EXPORT
            elif CR_COMPLETE_ZERO in statuses:
                status = CR_COMPLETE_ZERO
            else:
                status = "UNKNOWN"
        elif complete_counts and canonical_count == max(complete_counts):
            status = CR_COMPLETE
        elif complete_counts:
            status = "MERGED"
        else:
            status = "PARTIAL_OR_UNVERIFIED"

        con.execute(
            "UPDATE wos_records SET cr_status=?,best_cr_count=?,reported_reference_count=coalesce(?,reported_reference_count) WHERE ut=?",
            (status, canonical_count, max_reported, ut),
        )


__all__ = ["SCHEMA_SQL", "SCHEMA_VERSION", "WosCorpusStore"]
