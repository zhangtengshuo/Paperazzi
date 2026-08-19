"""First-class Zotero collection-catalog persistence.

The catalog is independent from item membership rows.  It is updated from the full
Zotero ``collections`` table and retains historical rows when a collection disappears.
"""
from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from typing import Any

import sqlalchemy as sa

from paperazzi.ingest.models import CanonicalZoteroCollection, CanonicalZoteroItem

from .base import utcnow
from .models import ZoteroScanRun
from .persistence import (
    CHANGE_MODIFIED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_RESTORED,
    CHANGE_UNCHANGED,
    ScanPersistenceError,
    ScanResult,
    _apply_scan,
    _corpus_hash,
)

CATALOG_TABLE = "zotero_collections"


def _collection_catalog_hash(collections: Sequence[CanonicalZoteroCollection]) -> str:
    payload = [
        {
            "library_id": row.library_id,
            "collection_id": row.collection_id,
            "collection_key": row.collection_key,
            "name": row.name,
            "parent_collection_id": row.parent_collection_id,
            "parent_collection_key": row.parent_collection_key,
            "parent_name": row.parent_name,
        }
        for row in sorted(collections, key=lambda c: (c.library_id, c.collection_key))
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_catalog_table(session: Any) -> None:
    inspector = sa.inspect(session.get_bind())
    if not inspector.has_table(CATALOG_TABLE):
        raise ScanPersistenceError(
            "zotero_collections table is unavailable; run current Alembic migrations"
        )
    scan_columns = {column["name"] for column in inspector.get_columns("zotero_scan_runs")}
    required = {"collection_count", "collection_catalog_hash"}
    if not required.issubset(scan_columns):
        raise ScanPersistenceError(
            "collection scan summary columns are unavailable; run Alembic migration 0012"
        )


def sync_collection_catalog(
    session: Any,
    run_id: int,
    collections: Sequence[CanonicalZoteroCollection],
) -> dict[str, int]:
    """Synchronize one complete catalog snapshot inside an existing scan transaction."""
    _require_catalog_table(session)
    seen: set[tuple[int, str]] = set()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0, "restored": 0}

    existing_rows = session.execute(
        sa.text(
            """SELECT zotero_collection_id,library_id,collection_id,collection_key,name,
                      parent_collection_id,parent_collection_key,parent_name,
                      present_in_last_scan,first_seen_run_id,last_seen_run_id
               FROM zotero_collections"""
        )
    ).mappings().all()
    existing = {(int(row["library_id"]), str(row["collection_key"])): dict(row) for row in existing_rows}

    for collection in collections:
        identity = collection.stable_identity
        if identity in seen:
            raise ScanPersistenceError(
                f"duplicate collection identity in scan input: library={identity[0]} key={identity[1]}"
            )
        seen.add(identity)
        prior = existing.get(identity)
        payload = {
            "library_id": collection.library_id,
            "collection_id": collection.collection_id,
            "collection_key": collection.collection_key,
            "name": collection.name,
            "parent_collection_id": collection.parent_collection_id,
            "parent_collection_key": collection.parent_collection_key,
            "parent_name": collection.parent_name,
            "run_id": run_id,
        }
        if prior is None:
            session.execute(
                sa.text(
                    """INSERT INTO zotero_collections(
                           library_id,collection_id,collection_key,name,parent_collection_id,
                           parent_collection_key,parent_name,present_in_last_scan,
                           first_seen_run_id,last_seen_run_id,created_at,updated_at)
                       VALUES(:library_id,:collection_id,:collection_key,:name,:parent_collection_id,
                              :parent_collection_key,:parent_name,1,:run_id,:run_id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""
                ),
                payload,
            )
            counts["new"] += 1
            continue

        changed = any(
            prior.get(field) != payload[field]
            for field in (
                "collection_id",
                "name",
                "parent_collection_id",
                "parent_collection_key",
                "parent_name",
            )
        )
        restored = not bool(prior["present_in_last_scan"])
        session.execute(
            sa.text(
                """UPDATE zotero_collections
                   SET collection_id=:collection_id,name=:name,
                       parent_collection_id=:parent_collection_id,
                       parent_collection_key=:parent_collection_key,parent_name=:parent_name,
                       present_in_last_scan=1,last_seen_run_id=:run_id,updated_at=CURRENT_TIMESTAMP
                   WHERE library_id=:library_id AND collection_key=:collection_key"""
            ),
            payload,
        )
        if restored:
            counts["restored"] += 1
        elif changed:
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    for identity, prior in existing.items():
        if identity in seen or not bool(prior["present_in_last_scan"]):
            continue
        session.execute(
            sa.text(
                """UPDATE zotero_collections
                   SET present_in_last_scan=0,last_seen_run_id=:run_id,updated_at=CURRENT_TIMESTAMP
                   WHERE library_id=:library_id AND collection_key=:collection_key"""
            ),
            {"run_id": run_id, "library_id": identity[0], "collection_key": identity[1]},
        )
        counts["removed"] += 1
    return counts


def persist_zotero_scan_with_collection_catalog(
    session_factory: Any,
    canonical_items: Sequence[CanonicalZoteroItem],
    collection_catalog: Sequence[CanonicalZoteroCollection],
    scan_metadata: dict[str, Any],
) -> ScanResult:
    """Persist items and the complete collection catalog in one scan lifecycle.

    The STARTED ledger row is committed first, matching the existing Phase 3 failure
    semantics.  Item projection and collection-catalog projection then share one
    transaction: either both become current for the run or neither does.
    """
    run_token = scan_metadata.get("run_token")
    if not run_token:
        raise ScanPersistenceError("scan_metadata requires run_token")

    session = session_factory()
    try:
        _require_catalog_table(session)
        run = ZoteroScanRun(
            run_token=run_token,
            status="STARTED",
            source_db_path=scan_metadata["source_db_path"],
            source_db_size=scan_metadata.get("source_db_size"),
            source_db_mtime_ns=scan_metadata.get("source_db_mtime_ns"),
            snapshot_path=scan_metadata.get("snapshot_path"),
            adapter_name=scan_metadata.get("adapter_name"),
            userdata_version=scan_metadata.get("userdata_version"),
            global_schema_version=scan_metadata.get("global_schema_version"),
            started_at=utcnow(),
        )
        session.add(run)
        session.flush()
        run_id = int(run.scan_run_id)
        session.commit()

        try:
            result = _apply_scan(session, run_id, canonical_items)
            catalog_counts = sync_collection_catalog(session, run_id, collection_catalog)
            run = session.get(ZoteroScanRun, run_id)
            assert run is not None
            run.status = "COMPLETED"
            run.item_count = len(canonical_items)
            run.new_count = result["counts"].get(CHANGE_NEW, 0)
            run.modified_count = result["counts"].get(CHANGE_MODIFIED, 0)
            run.unchanged_count = result["counts"].get(CHANGE_UNCHANGED, 0)
            run.removed_count = result["counts"].get(CHANGE_REMOVED, 0)
            run.restored_count = result["counts"].get(CHANGE_RESTORED, 0)
            run.bibliographic_corpus_hash = _corpus_hash(canonical_items, "bibliographic_hash")
            run.canonical_corpus_hash = _corpus_hash(canonical_items, "canonical_hash")
            run.completed_at = utcnow()
            # 0012 columns are intentionally not on the Phase-3 ORM model yet; update
            # them explicitly so the migration remains additive and older code paths
            # can continue to read the scan ledger.
            session.execute(
                sa.text(
                    """UPDATE zotero_scan_runs
                       SET collection_count=:collection_count,
                           collection_catalog_hash=:catalog_hash
                       WHERE scan_run_id=:run_id"""
                ),
                {
                    "collection_count": len(collection_catalog),
                    "catalog_hash": _collection_catalog_hash(collection_catalog),
                    "run_id": run_id,
                },
            )
            session.commit()
            counts = dict(result["counts"])
            counts.update({f"COLLECTION_{k.upper()}": v for k, v in catalog_counts.items()})
            return ScanResult(
                scan_run_id=run_id,
                status="COMPLETED",
                counts=counts,
                changes=result["changes"],
            )
        except Exception as exc:
            session.rollback()
            run = session.get(ZoteroScanRun, run_id)
            assert run is not None
            run.status = "FAILED"
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:2000]
            run.completed_at = utcnow()
            session.commit()
            return ScanResult(scan_run_id=run_id, status="FAILED", error=str(exc))
    finally:
        session.close()


__all__ = [
    "CATALOG_TABLE",
    "persist_zotero_scan_with_collection_catalog",
    "sync_collection_catalog",
]
