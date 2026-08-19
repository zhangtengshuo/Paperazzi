"""Shared read-only paper organization projection from the latest Zotero scan."""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from paperazzi.database.models import ZoteroItemCollection, ZoteroItemState, ZoteroItemTag


def paper_zotero_organization(session: Any, paper_id: int) -> dict[str, Any]:
    """Return current collection paths and tags for one Paperazzi paper.

    Collections and tags remain separate source dimensions.  The catalog is optional
    for backward compatibility: when migration/scan data are unavailable, item-level
    memberships and tags can still be returned, but full ancestor paths are not
    invented.
    """
    state = (
        session.query(ZoteroItemState)
        .filter(
            ZoteroItemState.paper_id == paper_id,
            ZoteroItemState.present_in_last_scan.is_(True),
        )
        .order_by(ZoteroItemState.zotero_item_state_id)
        .first()
    )
    if state is None:
        return {
            "paper_id": paper_id,
            "available": True,
            "collections": [],
            "collection_paths": [],
            "tags": [],
        }

    inspector = sa.inspect(session.get_bind())
    has_catalog = inspector.has_table("zotero_collections")
    catalog: dict[str, dict[str, Any]] = {}
    if has_catalog:
        catalog = {
            str(row["collection_key"]): dict(row)
            for row in session.execute(
                sa.text(
                    """SELECT collection_key,name,parent_collection_key,parent_collection_id
                       FROM zotero_collections
                       WHERE library_id=:library_id AND present_in_last_scan=1"""
                ),
                {"library_id": state.library_id},
            ).mappings()
        }

    memberships = (
        session.query(ZoteroItemCollection)
        .filter_by(zotero_item_state_id=state.zotero_item_state_id)
        .order_by(
            ZoteroItemCollection.order_index,
            ZoteroItemCollection.zotero_item_collection_id,
        )
        .all()
    )
    paths: list[list[dict[str, Any]]] = []
    collection_rows: list[dict[str, Any]] = []
    for membership in memberships:
        key = membership.collection_key
        if not key:
            continue
        chain: list[dict[str, Any]] = []
        cursor: str | None = key
        seen: set[str] = set()
        cycle_detected = False
        missing_catalog = False
        while cursor:
            if cursor in seen:
                cycle_detected = True
                break
            seen.add(cursor)
            row = catalog.get(cursor)
            if row is None:
                missing_catalog = True
                if cursor == key:
                    chain.append(
                        {
                            "collection_key": cursor,
                            "name": membership.name,
                            "missing_catalog": True,
                        }
                    )
                break
            chain.append({"collection_key": cursor, "name": row["name"]})
            cursor = row["parent_collection_key"]
        chain.reverse()
        paths.append(chain)
        collection_rows.append(
            {
                "collection_key": key,
                "name": membership.name,
                "order_index": membership.order_index,
                "path": chain,
                "cycle_detected": cycle_detected,
                "missing_catalog": missing_catalog,
            }
        )

    tags = [
        {"tag_id": tag.tag_id, "name": tag.name, "tag_type": tag.tag_type}
        for tag in session.query(ZoteroItemTag)
        .filter_by(zotero_item_state_id=state.zotero_item_state_id)
        .order_by(sa.func.lower(ZoteroItemTag.name), ZoteroItemTag.zotero_item_tag_id)
        .all()
    ]
    return {
        "paper_id": paper_id,
        "library_id": state.library_id,
        "available": has_catalog,
        "collections": collection_rows,
        "collection_paths": paths,
        "tags": tags,
    }


__all__ = ["paper_zotero_organization"]
