"""FastAPI routes for deterministic Graph Analytics."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from paperazzi.analytics.builder import GraphAnalyticsBuilder
from paperazzi.analytics.revision import wos_revision
from paperazzi.analytics.service import (
    AnalyticsNotFoundError,
    AnalyticsUnavailableError,
    GraphAnalyticsService,
)
from paperazzi.database.models import Paper


class AnalyticsBuildRequest(BaseModel):
    min_shared_references: int = 2
    min_co_citation: int = 2
    community_min_weight: float = 0.10


def build_analytics_router(
    session_factory: Any,
    wos_db_path: str | Path,
    analytics_db_path: str | Path,
) -> APIRouter:
    router = APIRouter()
    wos_path = Path(wos_db_path)
    analytics_path = Path(analytics_db_path)

    @contextmanager
    def session_scope():
        with session_factory() as session:
            yield session

    def service() -> GraphAnalyticsService:
        return GraphAnalyticsService(analytics_path)

    def paper_ut(paper_id: int) -> str:
        with session_scope() as session:
            if session.get(Paper, paper_id) is None:
                raise HTTPException(status_code=404, detail=f"paper {paper_id} does not exist")
            inspector = sa.inspect(session.get_bind())
            if not inspector.has_table("paper_wos_links"):
                raise HTTPException(status_code=409, detail="paper_wos_links is unavailable; run current migrations")
            row = session.execute(
                sa.text(
                    """SELECT wos_ut FROM paper_wos_links
                       WHERE paper_id=:paper_id AND status='ACCEPTED'
                       ORDER BY paper_wos_link_id DESC LIMIT 1"""
                ),
                {"paper_id": paper_id},
            ).first()
            if row is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"paper {paper_id} has no accepted local WoS link; Graph Analytics currently uses WoS UT nodes",
                )
            return str(row[0])

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, AnalyticsNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, AnalyticsUnavailableError):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, FileNotFoundError):
            return HTTPException(status_code=409, detail=f"source database unavailable: {exc}")
        if isinstance(exc, ValueError):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

    @router.get("/api/analytics/stats")
    def analytics_stats() -> dict[str, Any]:
        payload = service().stats()
        current_revision = wos_revision(wos_path)
        latest = payload.get("latest_run") or {}
        built_revision = (latest.get("corpus_definition") or {}).get("source_revision")
        if built_revision is None or not current_revision.get("available"):
            stale: bool | None = None
        else:
            stale = built_revision != current_revision
        payload.update(
            {
                "wos_database": str(wos_path),
                "wos_available": wos_path.is_file(),
                "analytics_database": str(analytics_path),
                "built_from_wos_revision": built_revision,
                "current_wos_revision": current_revision,
                "stale": stale,
                "rebuild_required": stale is True,
            }
        )
        return payload

    @router.post("/api/analytics/runs")
    def build_run(request: AnalyticsBuildRequest) -> dict[str, Any]:
        if request.min_shared_references < 1 or request.min_co_citation < 1:
            raise HTTPException(status_code=400, detail="minimum relation counts must be >= 1")
        if request.community_min_weight < 0:
            raise HTTPException(status_code=400, detail="community_min_weight must be >= 0")
        try:
            return GraphAnalyticsBuilder(wos_path, analytics_path).build(
                min_shared_references=request.min_shared_references,
                min_co_citation=request.min_co_citation,
                community_min_weight=request.community_min_weight,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/centrality")
    def centrality(
        metric: str = "pagerank_local",
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        try:
            return service().centrality(metric=metric, limit=limit)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/wos/{ut}/related")
    def wos_related(ut: str, limit: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        try:
            return service().related(ut, limit=limit)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/wos/{ut}/neighborhood")
    def wos_neighborhood(ut: str, limit: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        try:
            return service().neighborhood(ut, limit=limit)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/papers/{paper_id}/related")
    def paper_related(paper_id: int, limit: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        try:
            ut = paper_ut(paper_id)
            payload = service().related(ut, limit=limit)
            payload["paper_id"] = paper_id
            payload["wos_ut"] = ut
            return payload
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/papers/{paper_id}/neighborhood")
    def paper_neighborhood(paper_id: int, limit: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        try:
            ut = paper_ut(paper_id)
            payload = service().neighborhood(ut, limit=limit)
            payload["paper_id"] = paper_id
            payload["wos_ut"] = ut
            return payload
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/connector")
    def connector(
        from_ut: str,
        to_ut: str,
        max_paths: int = Query(default=3, ge=1, le=20),
        max_hops: int = Query(default=8, ge=1, le=30),
    ) -> dict[str, Any]:
        try:
            return service().connector(
                from_ut,
                to_ut,
                max_paths=max_paths,
                max_hops=max_hops,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/paper-connector")
    def paper_connector(
        from_paper_id: int,
        to_paper_id: int,
        max_paths: int = Query(default=3, ge=1, le=20),
        max_hops: int = Query(default=8, ge=1, le=30),
    ) -> dict[str, Any]:
        try:
            source_ut = paper_ut(from_paper_id)
            target_ut = paper_ut(to_paper_id)
            payload = service().connector(
                source_ut,
                target_ut,
                max_paths=max_paths,
                max_hops=max_hops,
            )
            payload["from_paper_id"] = from_paper_id
            payload["to_paper_id"] = to_paper_id
            return payload
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/communities")
    def communities() -> dict[str, Any]:
        try:
            return service().communities()
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/api/analytics/rpys")
    def analytics_rpys(peaks_only: bool = False) -> dict[str, Any]:
        try:
            return service().rpys(peaks_only=peaks_only)
        except Exception as exc:
            raise translate_error(exc) from exc

    return router


__all__ = ["build_analytics_router"]
