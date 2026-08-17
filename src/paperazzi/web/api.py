"""FastAPI adapter for the Paperazzi local web application."""
from __future__ import annotations

import atexit
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.identity.manual_review import (
    create_identity_from_review,
    identity_review_detail,
    link_review_mention,
    merge_identity_review_pair,
    reject_review_candidate,
    sync_author_name_variants,
)
from paperazzi.identity.profile_evidence import author_sourced_evidence
from paperazzi.identity.review_queries import list_identity_review_queue
from paperazzi.identity.service import IdentityResolutionError
from paperazzi.identity.similar_names import (
    refresh_similar_identity_reviews,
    similar_author_candidates,
)
from paperazzi.web.identity_review_ui import IDENTITY_REVIEW_MULTICANDIDATE_JS
from paperazzi.web.queries import NotFoundError, PaperazziQueryService, PdfUnavailableError
from paperazzi.web.ui import APP_HTML

DEFAULT_DB = Path("data/paperazzi.sqlite3")


class IdentityTargetRequest(BaseModel):
    target_author_id: str
    notes: str | None = None


class IdentityCandidateRequest(BaseModel):
    candidate_author_id: str
    notes: str | None = None


class MergeAuthorsRequest(BaseModel):
    source_author_id: str
    target_author_id: str
    review_item_id: int | None = None
    notes: str | None = None


class ReviewNotesRequest(BaseModel):
    notes: str | None = None


def _database_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("PAPERAZZI_DB", DEFAULT_DB))


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = _database_path(db_path)
    engine = create_paperazzi_engine(path)
    atexit.register(engine.dispose)
    session_factory = sa.orm.sessionmaker(bind=engine)

    app = FastAPI(
        title="Paperazzi",
        version="0.1.0.dev0",
        description="Local-first Zotero-centered scholarly author knowledge base",
    )
    app.state.db_path = path
    app.state.engine = engine
    app.state.session_factory = session_factory

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

    @contextmanager
    def service() -> Iterator[PaperazziQueryService]:
        with session_scope() as session:
            yield PaperazziQueryService(session)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> str:
        enhancement = f"<script>{IDENTITY_REVIEW_MULTICANDIDATE_JS}</script>"
        return APP_HTML.replace("</body>", enhancement + "</body>")

    @app.get("/health")
    def health() -> dict[str, object]:
        if not path.is_file():
            return {"status": "NO_DATABASE", "database": str(path)}
        try:
            with engine.connect() as connection:
                connection.execute(sa.text("SELECT 1"))
            return {"status": "OK", "database": str(path)}
        except Exception as exc:  # pragma: no cover
            return {"status": "ERROR", "database": str(path), "error": type(exc).__name__}

    @app.get("/api/papers")
    def papers(
        q: str | None = None,
        year: int | None = None,
        venue: str | None = None,
        pdf_available: bool | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        with service() as query_service:
            return query_service.list_papers(
                q=q, year=year, venue=venue, pdf_available=pdf_available,
                limit=limit, offset=offset,
            )

    @app.get("/api/papers/{paper_id}")
    def paper(paper_id: int) -> dict[str, object]:
        try:
            with service() as query_service:
                return query_service.get_paper(paper_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/papers/{paper_id}/pdf", response_class=FileResponse)
    def paper_pdf(paper_id: int):
        try:
            with service() as query_service:
                pdf_path = query_service.get_pdf_path(paper_id)
        except PdfUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            path=pdf_path, media_type="application/pdf", filename=pdf_path.name,
            content_disposition_type="inline",
        )

    @app.get("/api/authors")
    def authors(
        q: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        with service() as query_service:
            return query_service.list_authors(q=q, limit=limit, offset=offset)

    @app.get("/api/authors/{author_id}")
    def author(author_id: str) -> dict[str, object]:
        try:
            with service() as query_service:
                return query_service.get_author(author_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/authors/{author_id}/papers")
    def author_papers(author_id: str) -> list[dict[str, object]]:
        try:
            with service() as query_service:
                query_service.get_author(author_id)
                return query_service.get_author_publications(author_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/authors/{author_id}/coauthors")
    def author_coauthors(
        author_id: str, limit: int = Query(default=100, ge=1, le=500)
    ) -> list[dict[str, object]]:
        try:
            with service() as query_service:
                query_service.get_author(author_id)
                return query_service.get_coauthors(author_id, limit=limit)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/authors/{author_id}/evidence")
    def author_evidence(
        author_id: str, limit: int = Query(default=100, ge=1, le=500)
    ) -> list[dict[str, object]]:
        try:
            with session_scope() as session:
                PaperazziQueryService(session).get_author(author_id)
                return author_sourced_evidence(session, author_id, limit=limit)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/reviews/identity")
    def identity_reviews(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, object]]:
        with session_scope() as session:
            return list_identity_review_queue(session, limit=limit)

    @app.get("/api/reviews/identity/{review_item_id}")
    def identity_review(review_item_id: int) -> dict[str, object]:
        try:
            with session_scope() as session:
                detail = identity_review_detail(session, review_item_id)
                if detail.get("subject_type") == "author":
                    detail["candidates"] = similar_author_candidates(
                        session, str(detail["subject_id"]), limit=12
                    )
                return detail
        except (KeyError, IdentityResolutionError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/reviews/identity/refresh-similar")
    def refresh_similar_identity_candidates() -> dict[str, int]:
        """Refresh human-review suggestions; never auto-merge names."""
        with session_scope(write=True) as session:
            return refresh_similar_identity_reviews(session)

    @app.post("/api/reviews/identity/sync-name-variants")
    def sync_name_variants() -> dict[str, int]:
        with session_scope(write=True) as session:
            return sync_author_name_variants(session)

    @app.post("/api/reviews/identity/{review_item_id}/link")
    def link_identity_review(review_item_id: int, request: IdentityTargetRequest) -> dict[str, object]:
        try:
            with session_scope(write=True) as session:
                return link_review_mention(
                    session, review_item_id, request.target_author_id, notes=request.notes
                )
        except IdentityResolutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/reviews/identity/{review_item_id}/not-same")
    def not_same_identity_review(review_item_id: int, request: IdentityCandidateRequest) -> dict[str, object]:
        try:
            with session_scope(write=True) as session:
                return reject_review_candidate(
                    session, review_item_id, request.candidate_author_id, notes=request.notes
                )
        except IdentityResolutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/reviews/identity/{review_item_id}/create-identity")
    def create_identity_review(review_item_id: int, request: ReviewNotesRequest) -> dict[str, object]:
        try:
            with session_scope(write=True) as session:
                return create_identity_from_review(session, review_item_id, notes=request.notes)
        except IdentityResolutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/authors/merge")
    def merge_author_identities(request: MergeAuthorsRequest) -> dict[str, object]:
        try:
            with session_scope(write=True) as session:
                return merge_identity_review_pair(
                    session,
                    request.source_author_id,
                    request.target_author_id,
                    review_item_id=request.review_item_id,
                    notes=request.notes,
                )
        except IdentityResolutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/search")
    def search(
        q: str = Query(min_length=1),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        with service() as query_service:
            return query_service.search(q, limit=limit)

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run(
        "paperazzi.web.api:app",
        host=os.environ.get("PAPERAZZI_HOST", "127.0.0.1"),
        port=int(os.environ.get("PAPERAZZI_PORT", "8765")),
        reload=False,
    )


if __name__ == "__main__":
    main()
