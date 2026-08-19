#!/usr/bin/env python3
"""Run one read-only Zotero scan including the complete collection catalog."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.collection_catalog import persist_zotero_scan_with_collection_catalog
from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.zotero_sqlite.probe import open_readonly, resolve_db_path
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zotero-db", help="Path to read-only Zotero zotero.sqlite; auto-discovered when omitted")
    parser.add_argument("--zotero-data-dir", help="Zotero data directory; defaults to parent of zotero.sqlite")
    parser.add_argument("--paperazzi-db", default="data/paperazzi.sqlite3")
    parser.add_argument("--run-token")
    args = parser.parse_args()

    zotero_db = resolve_db_path(args.zotero_db)
    zotero_data_dir = Path(args.zotero_data_dir).expanduser().resolve() if args.zotero_data_dir else zotero_db.parent
    paperazzi_db = Path(args.paperazzi_db).expanduser().resolve()
    if not paperazzi_db.is_file():
        raise FileNotFoundError(
            f"Paperazzi database not found: {paperazzi_db}. Run current Alembic migrations first."
        )

    stat = zotero_db.stat()
    conn = open_readonly(zotero_db)
    try:
        reader = ZoteroSQLiteReader(conn, zotero_data_dir)
        items = reader.read_items(include_deleted=False)
        catalog = reader.read_collection_catalog()
        versions = reader.schema_identity.versions
    finally:
        conn.close()

    engine = create_paperazzi_engine(paperazzi_db)
    Session = sa.orm.sessionmaker(bind=engine)
    run_token = args.run_token or "zotero-collections-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = persist_zotero_scan_with_collection_catalog(
        Session,
        items,
        catalog,
        {
            "run_token": run_token,
            "source_db_path": str(zotero_db),
            "source_db_size": stat.st_size,
            "source_db_mtime_ns": stat.st_mtime_ns,
            "adapter_name": reader.schema_identity.adapter_name,
            "userdata_version": versions.get("userdata"),
            "global_schema_version": versions.get("globalSchema"),
        },
    )
    print(
        json.dumps(
            {
                "status": result.status,
                "scan_run_id": result.scan_run_id,
                "items_read": len(items),
                "collections_read": len(catalog),
                "counts": result.counts,
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if result.status != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
