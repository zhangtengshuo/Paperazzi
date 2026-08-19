"""FastAPI routes for the read-only Zotero collection catalog projection."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from paperazzi.database.models import Paper
from paperazzi.web.collections import (
    CollectionCatalogUnavailable,
    CollectionNotFound,
    ZoteroCollectionQueryService,
)
from paperazzi.web.collections_ui import COLLECTIONS_UI_JS


def build_collections_router(session_factory: Any) -> APIRouter:
    router = APIRouter()

    @contextmanager
    def session_scope():
        with session_factory() as session:
            yield session

    def service(session: Any) -> ZoteroCollectionQueryService:
        try:
            return ZoteroCollectionQueryService(session)
        except CollectionCatalogUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/collections/ui.js", response_class=Response, include_in_schema=False)
    def collection_ui_script() -> Response:
        return Response(COLLECTIONS_UI_JS, media_type="application/javascript; charset=utf-8")

    @router.get("/api/collections/tree")
    def collection_tree(
        library_id: int = Query(default=1),
        include_empty: bool = Query(default=True),
    ) -> dict[str, Any]:
        with session_scope() as session:
            return service(session).tree(library_id, include_empty=include_empty)

    @router.get("/api/collections/unfiled/papers")
    def unfiled_papers(
        library_id: int = Query(default=1),
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        with session_scope() as session:
            return service(session).unfiled_papers(library_id, limit=limit, offset=offset)

    @router.get("/api/collections/{collection_key}")
    def collection_detail(
        collection_key: str,
        library_id: int = Query(default=1),
    ) -> dict[str, Any]:
        try:
            with session_scope() as session:
                node = service(session).collection(library_id, collection_key)
                return {"available": True, "library_id": library_id, "collection": node}
        except CollectionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/collections/{collection_key}/papers")
    def collection_papers(
        collection_key: str,
        library_id: int = Query(default=1),
        include_descendants: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        try:
            with session_scope() as session:
                return service(session).papers(
                    library_id,
                    collection_key,
                    include_descendants=include_descendants,
                    limit=limit,
                    offset=offset,
                )
        except CollectionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/papers/{paper_id}/organization")
    def paper_organization(paper_id: int) -> dict[str, Any]:
        with session_scope() as session:
            if session.get(Paper, paper_id) is None:
                raise HTTPException(status_code=404, detail=f"paper {paper_id} does not exist")
            return service(session).paper_organization(paper_id)

    return router


__all__ = ["build_collections_router"]
