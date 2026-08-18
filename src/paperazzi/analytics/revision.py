"""Cheap WoS corpus revision fingerprint used to flag stale analytics runs."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


def wos_revision(path: str | Path) -> dict[str, Any]:
    db = Path(path)
    if not db.is_file():
        return {"available": False}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        record_count = int(con.execute("SELECT count(*) FROM wos_records").fetchone()[0])
        reference_count = int(con.execute("SELECT count(*) FROM wos_cited_references").fetchone()[0])
        latest_batch_id = int(
            con.execute("SELECT coalesce(max(batch_id),0) FROM wos_import_batches").fetchone()[0]
        )
        resolved_edges = int(
            con.execute(
                "SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL"
            ).fetchone()[0]
        )
    finally:
        con.close()
    return {
        "available": True,
        "record_count": record_count,
        "reference_count": reference_count,
        "resolved_citation_edges": resolved_edges,
        "latest_import_batch_id": latest_batch_id,
    }


__all__ = ["wos_revision"]
