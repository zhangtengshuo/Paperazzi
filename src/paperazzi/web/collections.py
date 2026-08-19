"""Read-only Zotero collection-tree queries for Paperazzi Web."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import sqlalchemy as sa

from paperazzi.database.models import Paper, ZoteroItemCollection, ZoteroItemState, ZoteroItemTag
from paperazzi.web.queries import PaperazziQueryService


class CollectionCatalogUnavailable(RuntimeError):
    pass


class CollectionNotFound(LookupError):
    pass


def _sort_key(node: dict[str, Any]) -> tuple[str, str]:
    return str(node["name"]).casefold(), str(node["collection_key"])


class ZoteroCollectionQueryService:
    """Bounded-query collection tree and paper navigation service.

    The tree itself is built from exactly three data reads regardless of node count:
    current catalog rows, active collection memberships, and the active paper total.
    Subtree counts are then set unions in memory, avoiding one query per collection.
    """

    def __init__(self, session: Any):
        self.session = session
        if not sa.inspect(session.get_bind()).has_table("zotero_collections"):
            raise CollectionCatalogUnavailable(
                "zotero_collections is unavailable; run current Alembic migrations and a catalog-aware Zotero scan"
            )

    def _catalog_rows(self, library_id: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.session.execute(
                sa.text(
                    """SELECT library_id,collection_id,collection_key,name,parent_collection_id,
                              parent_collection_key,parent_name,first_seen_run_id,last_seen_run_id
                       FROM zotero_collections
                       WHERE library_id=:library_id AND present_in_last_scan=1"""
                ),
                {"library_id": library_id},
            ).mappings()
        ]

    def _active_membership_sets(self, library_id: int) -> dict[str, set[int]]:
        rows = self.session.execute(
            sa.text(
                """SELECT c.collection_key,p.paper_id
                   FROM zotero_item_collections c
                   JOIN zotero_item_state s ON s.zotero_item_state_id=c.zotero_item_state_id
                   JOIN papers p ON p.paper_id=s.paper_id
                   WHERE s.library_id=:library_id
                     AND s.present_in_last_scan=1
                     AND p.active_in_zotero=1
                     AND c.collection_key IS NOT NULL"""
            ),
            {"library_id": library_id},
        ).all()
        result: dict[str, set[int]] = defaultdict(set)
        for key, paper_id in rows:
            result[str(key)].add(int(paper_id))
        return result

    def _active_paper_count(self, library_id: int) -> int:
        return int(
            self.session.execute(
                sa.text(
                    """SELECT COUNT(DISTINCT p.paper_id)
                       FROM papers p JOIN zotero_item_state s ON s.paper_id=p.paper_id
                       WHERE p.active_in_zotero=1
                         AND s.present_in_last_scan=1
                         AND s.library_id=:library_id"""
                ),
                {"library_id": library_id},
            ).scalar()
            or 0
        )

    def tree(self, library_id: int, *, include_empty: bool = True) -> dict[str, Any]:
        rows = self._catalog_rows(library_id)
        membership_sets = self._active_membership_sets(library_id)
        total = self._active_paper_count(library_id)
        filed_ids: set[int] = set()
        for paper_ids in membership_sets.values():
            filed_ids.update(paper_ids)
        filed = len(filed_ids)
        unfiled = max(0, total - filed)

        nodes: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row["collection_key"])
            direct_count = len(membership_sets.get(key, set()))
            nodes[key] = {
                **row,
                "collection_key": key,
                "active_paper_count": direct_count,
                "subtree_active_paper_count": 0,
                "has_active_papers": direct_count > 0,
                "depth": 0,
                "path": [],
                "children": [],
                "orphaned": False,
            }

        children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        orphaned: list[dict[str, Any]] = []
        orphan_keys: set[str] = set()

        def mark_orphan(node: dict[str, Any], reason: str) -> None:
            key = str(node["collection_key"])
            node["orphaned"] = True
            node["orphan_reason"] = reason
            if key not in orphan_keys:
                orphan_keys.add(key)
                orphaned.append(node)

        for node in nodes.values():
            parent_key = node["parent_collection_key"]
            parent_id = node["parent_collection_id"]
            if parent_key is None and parent_id is None:
                children[None].append(node)
            elif parent_key is not None and str(parent_key) in nodes:
                children[str(parent_key)].append(node)
            else:
                # A non-null source parent ID whose row is absent is not a root.
                # Preserve it in a diagnostic orphan bucket instead of guessing.
                node["missing_parent_collection_id"] = parent_id
                node["missing_parent_collection_key"] = parent_key
                mark_orphan(node, "MISSING_PARENT")

        for group in children.values():
            group.sort(key=_sort_key)
        orphaned.sort(key=_sort_key)

        visiting: set[str] = set()
        visited: set[str] = set()
        subtree_sets: dict[str, set[int]] = {}

        def build(node: dict[str, Any], ancestors: list[dict[str, str]]) -> set[int]:
            key = str(node["collection_key"])
            if key in visited:
                return set(subtree_sets.get(key, set()))
            if key in visiting:
                # Caller normally detects this before recursing. Keep this fallback
                # for malformed source graphs while never returning a recursive child.
                node["cycle_detected"] = True
                mark_orphan(node, "PARENT_CYCLE")
                return set(membership_sets.get(key, set()))

            visiting.add(key)
            path = [*ancestors, {"collection_key": key, "name": str(node["name"])}]
            node["path"] = path
            node["depth"] = len(path) - 1
            safe_children: list[dict[str, Any]] = []
            paper_ids = set(membership_sets.get(key, set()))

            for child in children.get(key, []):
                child_key = str(child["collection_key"])
                if child_key in visiting:
                    # Do not retain an object edge back to an ancestor; otherwise the
                    # response cannot be serialized and UI recursion never terminates.
                    node["cycle_detected"] = True
                    child["cycle_detected"] = True
                    child["cycle_parent_collection_key"] = key
                    mark_orphan(child, "PARENT_CYCLE")
                    paper_ids.update(membership_sets.get(child_key, set()))
                    continue
                safe_children.append(child)
                paper_ids.update(build(child, path))

            node["children"] = safe_children
            node["subtree_active_paper_count"] = len(paper_ids)
            subtree_sets[key] = paper_ids
            visiting.remove(key)
            visited.add(key)
            return paper_ids

        roots = children.get(None, [])
        for root in roots:
            build(root, [])
        for node in list(orphaned):
            if str(node["collection_key"]) not in visited:
                build(node, [])

        # A closed parent cycle can contain no root and no missing parent, so no node
        # would have been visited above. Surface every remaining component explicitly
        # instead of silently dropping it from the catalog response.
        for node in sorted(nodes.values(), key=_sort_key):
            key = str(node["collection_key"])
            if key in visited:
                continue
            mark_orphan(node, "DISCONNECTED_OR_PARENT_CYCLE")
            build(node, [])

        orphaned.sort(key=_sort_key)

        def prune(node: dict[str, Any], stack: set[str] | None = None) -> dict[str, Any] | None:
            stack = set() if stack is None else set(stack)
            key = str(node["collection_key"])
            if key in stack:
                # Defensive serialization guard; normal build() already truncates
                # cyclic child edges.
                return {**node, "children": [], "cycle_detected": True}
            stack.add(key)
            child_rows = [
                p
                for child in node["children"]
                if (p := prune(child, stack)) is not None
            ]
            copy = {**node, "children": child_rows}
            if include_empty or copy["active_paper_count"] or child_rows:
                return copy
            return None

        visible_roots = [p for root in roots if (p := prune(root)) is not None]
        visible_orphans = [p for node in orphaned if (p := prune(node)) is not None]
        return {
            "available": True,
            "library_id": library_id,
            "all_papers": {"name": "All papers", "active_paper_count": total},
            "unfiled": {"name": "Unfiled", "active_paper_count": unfiled},
            "summary": {
                "active_papers": total,
                "papers_with_collection": filed,
                "unfiled_papers": unfiled,
                "active_collection_memberships": sum(len(v) for v in membership_sets.values()),
                "collection_nodes": len(rows),
                "root_nodes": len(roots),
                "orphaned_nodes": len(orphaned),
                "ordering": "name.casefold(), collection_key",
                "tree_query_contract": "3 bounded source reads; recursive counts computed in memory",
            },
            "roots": visible_roots,
            "orphaned": visible_orphans,
        }

    def _descendant_keys(self, library_id: int, key: str) -> set[str]:
        nodes = {str(r["collection_key"]): r for r in self._catalog_rows(library_id)}
        children: dict[str, list[str]] = defaultdict(list)
        for child_key, node in nodes.items():
            parent = node.get("parent_collection_key")
            if parent is not None and str(parent) in nodes:
                children[str(parent)].append(child_key)
        result = {key}
        stack = [key]
        while stack:
            current = stack.pop()
            for child in children.get(current, []):
                if child not in result:
                    result.add(child)
                    stack.append(child)
        return result

    def collection(self, library_id: int, collection_key: str) -> dict[str, Any]:
        tree = self.tree(library_id, include_empty=True)
        stack = [*tree["roots"], *tree["orphaned"]]
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            key = str(node["collection_key"])
            if key in seen:
                continue
            seen.add(key)
            if key == collection_key:
                return node
            stack.extend(node["children"])
        raise CollectionNotFound(
            f"collection {collection_key!r} is not present in Zotero library {library_id}"
        )

    def papers(
        self,
        library_id: int,
        collection_key: str,
        *,
        include_descendants: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        node = self.collection(library_id, collection_key)
        keys = self._descendant_keys(library_id, collection_key) if include_descendants else {collection_key}
        query = (
            self.session.query(Paper, sa.func.min(ZoteroItemCollection.order_index).label("collection_order"))
            .join(ZoteroItemState, ZoteroItemState.paper_id == Paper.paper_id)
            .join(
                ZoteroItemCollection,
                ZoteroItemCollection.zotero_item_state_id == ZoteroItemState.zotero_item_state_id,
            )
            .filter(
                Paper.active_in_zotero.is_(True),
                ZoteroItemState.present_in_last_scan.is_(True),
                ZoteroItemState.library_id == library_id,
                ZoteroItemCollection.collection_key.in_(sorted(keys)),
            )
            .group_by(Paper.paper_id)
        )
        total = int(query.count())
        rows = (
            query.order_by(
                sa.func.min(ZoteroItemCollection.order_index),
                Paper.publication_year.desc().nullslast(),
                Paper.paper_id.desc(),
            )
            .offset(max(0, offset))
            .limit(min(max(1, limit), 200))
            .all()
        )
        summaries = PaperazziQueryService(self.session)
        return {
            "library_id": library_id,
            "collection": node,
            "include_descendants": include_descendants,
            "total": total,
            "items": [
                {**summaries._paper_summary(paper), "collection_order_index": int(order_index)}
                for paper, order_index in rows
            ],
        }

    def unfiled_papers(self, library_id: int, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        membership_exists = sa.exists().where(
            ZoteroItemCollection.zotero_item_state_id == ZoteroItemState.zotero_item_state_id
        )
        query = (
            self.session.query(Paper)
            .join(ZoteroItemState, ZoteroItemState.paper_id == Paper.paper_id)
            .filter(
                Paper.active_in_zotero.is_(True),
                ZoteroItemState.present_in_last_scan.is_(True),
                ZoteroItemState.library_id == library_id,
                ~membership_exists,
            )
            .distinct()
        )
        total = int(query.count())
        rows = (
            query.order_by(Paper.publication_year.desc().nullslast(), Paper.paper_id.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), 200))
            .all()
        )
        summaries = PaperazziQueryService(self.session)
        return {"library_id": library_id, "total": total, "items": [summaries._paper_summary(p) for p in rows]}

    def paper_organization(self, paper_id: int) -> dict[str, Any]:
        state = (
            self.session.query(ZoteroItemState)
            .filter(
                ZoteroItemState.paper_id == paper_id,
                ZoteroItemState.present_in_last_scan.is_(True),
            )
            .order_by(ZoteroItemState.zotero_item_state_id)
            .first()
        )
        if state is None:
            return {"paper_id": paper_id, "collections": [], "collection_paths": [], "tags": []}
        catalog = {
            str(row["collection_key"]): dict(row)
            for row in self.session.execute(
                sa.text(
                    """SELECT collection_key,name,parent_collection_key,parent_collection_id
                       FROM zotero_collections
                       WHERE library_id=:library_id AND present_in_last_scan=1"""
                ),
                {"library_id": state.library_id},
            ).mappings()
        }
        memberships = (
            self.session.query(ZoteroItemCollection)
            .filter_by(zotero_item_state_id=state.zotero_item_state_id)
            .order_by(ZoteroItemCollection.order_index, ZoteroItemCollection.zotero_item_collection_id)
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
            while cursor:
                if cursor in seen:
                    cycle_detected = True
                    break
                seen.add(cursor)
                row = catalog.get(cursor)
                if row is None:
                    if cursor == key:
                        chain.append({"collection_key": cursor, "name": membership.name, "missing_catalog": True})
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
                }
            )
        tags = [
            {"tag_id": tag.tag_id, "name": tag.name, "tag_type": tag.tag_type}
            for tag in self.session.query(ZoteroItemTag)
            .filter_by(zotero_item_state_id=state.zotero_item_state_id)
            .order_by(sa.func.lower(ZoteroItemTag.name), ZoteroItemTag.zotero_item_tag_id)
            .all()
        ]
        return {
            "paper_id": paper_id,
            "library_id": state.library_id,
            "collections": collection_rows,
            "collection_paths": paths,
            "tags": tags,
        }


__all__ = [
    "CollectionCatalogUnavailable",
    "CollectionNotFound",
    "ZoteroCollectionQueryService",
]
