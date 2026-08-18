"""FastAPI routes for the independent local WoS background corpus."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query

from paperazzi.database.models import Paper
from paperazzi.wos.integration import WosPaperConsumer, match_all_papers
from paperazzi.wos.read import rich_record
from paperazzi.wos.store import WosCorpusStore


def build_wos_router(session_factory: Any, wos_db_path: str | Path) -> APIRouter:
    router = APIRouter()
    wos_path = Path(wos_db_path)
    store = WosCorpusStore(wos_path)

    @contextmanager
    def session_scope(*, write: bool = False):
        with session_factory() as session:
            try:
                yield session
                if write:
                    session.commit()
            except Exception:
                if write:
                    session.rollback()
                raise

    @router.get("/api/wos/stats")
    def wos_stats() -> dict[str, object]:
        if not wos_path.is_file():
            return {"available": False, "database": str(wos_path), "status": "WOS_NOT_CHECKED"}
        return {"available": True, "database": str(wos_path), **store.stats()}

    @router.get("/api/wos/search")
    def wos_search(q: str = Query(min_length=1), limit: int = Query(default=50, ge=1, le=500)) -> dict[str, object]:
        if not wos_path.is_file():
            return {"available": False, "query": q, "items": []}
        return {"available": True, "query": q, "items": store.search(q, limit=limit)}

    @router.get("/api/wos/records/{ut}")
    def wos_record(ut: str) -> dict[str, object]:
        if not wos_path.is_file():
            raise HTTPException(status_code=404, detail="local WoS corpus is not configured")
        record = rich_record(store, ut)
        if record is None:
            raise HTTPException(status_code=404, detail=f"WoS record {ut} is not in the local corpus")
        return record

    @router.get("/api/wos/records/{ut}/references")
    def wos_references(
        ut: str,
        limit: int = Query(default=500, ge=1, le=2000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        if not wos_path.is_file():
            return {"available": False, "ut": ut, "items": []}
        if store.get_record(ut) is None:
            raise HTTPException(status_code=404, detail=f"WoS record {ut} is not in the local corpus")
        return {"available": True, "ut": ut, "items": store.list_references(ut, limit=limit, offset=offset)}

    @router.get("/api/wos/frontier")
    def wos_frontier(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        if not wos_path.is_file():
            return {"available": False, "items": []}
        return {"available": True, "items": store.citation_frontier(limit=limit)}

    @router.get("/api/papers/{paper_id}/wos")
    def paper_wos(paper_id: int) -> dict[str, object]:
        with session_scope() as session:
            if session.get(Paper, paper_id) is None:
                raise HTTPException(status_code=404, detail=f"paper {paper_id} does not exist")
            result = WosPaperConsumer(session, wos_path).detail(paper_id)
            if result.get("status") == "WOS_MATCHED" and result.get("wos_ut"):
                rich = rich_record(store, str(result["wos_ut"]))
                if rich is not None:
                    # The consumer projection de-duplicates RP members across multiple
                    # Corresponding Address groups; retain that role list while replacing
                    # the rest of the record with the richer author/identifier projection.
                    rich["corresponding_authors"] = result.get("record", {}).get("corresponding_authors", [])
                    result["record"] = rich
            return result

    @router.get("/api/wos/coverage")
    def wos_coverage() -> dict[str, object]:
        with session_scope() as session:
            active = int(session.query(Paper).filter(Paper.active_in_zotero.is_(True)).count())
            inspector = sa.inspect(session.get_bind())
            has_links = inspector.has_table("paper_wos_links")
            has_state = inspector.has_table("paper_wos_match_state")
            linked = 0
            if has_links:
                linked = int(session.execute(sa.text(
                    "SELECT count(DISTINCT l.paper_id) FROM paper_wos_links l JOIN papers p ON p.paper_id=l.paper_id "
                    "WHERE l.status='ACCEPTED' AND p.active_in_zotero=1"
                )).scalar() or 0)
            state_counts: dict[str, int] = {}
            if has_state:
                for status, count in session.execute(sa.text(
                    "SELECT s.status,count(*) FROM paper_wos_match_state s JOIN papers p ON p.paper_id=s.paper_id "
                    "WHERE p.active_in_zotero=1 GROUP BY s.status"
                )).all():
                    state_counts[str(status)] = int(count)
            checked = sum(state_counts.values())
            return {
                "wos_database_available": wos_path.is_file(),
                "active_zotero_papers": active,
                "matched": linked,
                "matched_state": state_counts.get("WOS_MATCHED", 0),
                "not_in_local_corpus": state_counts.get("WOS_NOT_IN_LOCAL_CORPUS", 0),
                "ambiguous": state_counts.get("WOS_MATCH_AMBIGUOUS", 0),
                "not_checked": max(0, active - checked),
                "without_accepted_local_wos_link": max(0, active - linked),
                "coverage_fraction": (linked / active) if active else 0.0,
                "completeness_required": False,
            }

    @router.post("/api/wos/match")
    def match_wos(apply: bool = False) -> dict[str, object]:
        """Match active Paperazzi papers to the current local WoS corpus.

        Missing WoS coverage remains a normal result. `apply=false` is a dry run;
        `apply=true` persists accepted links plus explicit matched/ambiguous/not-local
        coverage state so the UI can distinguish 'not checked' from 'checked, no hit'.
        """
        with session_scope(write=apply) as session:
            try:
                return match_all_papers(session, wos_path, apply=apply)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
