"""Cheap WoS corpus revision fingerprint used to flag stale analytics runs.

The fingerprint intentionally excludes import batch IDs: an identical overlapping WoS
re-import creates a new batch observation but does not necessarily change the canonical
graph and therefore should not force an analytics rebuild.
"""
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
        values = {
            "record_count": int(con.execute("SELECT count(*) FROM wos_records").fetchone()[0]),
            "reference_count": int(con.execute("SELECT count(*) FROM wos_cited_references").fetchone()[0]),
            "resolved_citation_edges": int(
                con.execute("SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL").fetchone()[0]
            ),
            "author_count": int(con.execute("SELECT count(*) FROM wos_authors").fetchone()[0]),
            "keyword_count": int(con.execute("SELECT count(*) FROM wos_keywords").fetchone()[0]),
            "classification_count": int(con.execute("SELECT count(*) FROM wos_classifications").fetchone()[0]),
        }
    finally:
        con.close()
    return {"available": True, **values}


__all__ = ["wos_revision"]
