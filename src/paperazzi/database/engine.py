"""Paperazzi-owned SQLite engine with the required connection pragmas."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event


def create_paperazzi_engine(path: str | Path) -> sa.Engine:
    """Create the writable Paperazzi engine (never used for Zotero sources).

    Every connection enables foreign_keys and busy_timeout; the database uses
    WAL journalling as required for the writable Paperazzi DB.
    """
    if isinstance(path, Path):
        path = str(path)
    engine = sa.create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _paperazzi_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine
