"""Cheap WoS corpus revision fingerprints used to flag stale analytics runs."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

_GRAPH_REVISION_KEYS = (
    "record_count",
    "reference_count",
    "resolved_citation_edges",
    "author_count",
    "keyword_count",
    "classification_count",
)


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
            "latest_import_batch_id": int(
                con.execute("SELECT coalesce(max(batch_id),0) FROM wos_import_batches").fetchone()[0]
            ),
        }
    finally:
        con.close()
    return {"available": True, **values}


def graph_revision_signature(revision: dict[str, Any] | None) -> tuple[Any, ...] | None:
    """Return a cheap canonical graph signature, excluding no-op import batch IDs."""
    if not revision or not revision.get("available"):
        return None
    return tuple(revision.get(key) for key in _GRAPH_REVISION_KEYS)


__all__ = ["graph_revision_signature", "wos_revision"]
