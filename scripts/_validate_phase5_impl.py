#!/usr/bin/env python3
"""Failure-isolated Phase 5 validation against a real Paperazzi database.

Each stage is written to disk before and after execution. A later HTTP harness
failure therefore cannot erase evidence already collected from the real DB.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import traceback
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.models import Paper, PaperCreatorMention, PaperDocument  # noqa:E402
from paperazzi.identity.models import Author, AuthorIdentityMembership  # noqa:E402
from paperazzi.web.api import create_app  # noqa:E402
from paperazzi.web.queries import PaperazziQueryService  # noqa:E402
from paperazzi.web.validation import (  # noqa:E402
    atomic_write_json,
    compare_constraints,
    environment_snapshot,
    run_asgi_smoke,
    run_uvicorn_smoke,
)

DEFAULT_DB = REPO_ROOT / "data" / "phase4-validation" / "paperazzi.sqlite3"
DEFAULT_REPORT = REPO_ROOT / "data" / "phase5-validation" / "phase5_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--sample-papers",
        type=int,
        default=200,
        help="Number of active papers checked through get_paper; 0 means all.",
    )
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--startup-timeout", type=float, default=12.0)
    return parser.parse_args()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def write_report(path: Path, report: dict[str, object]) -> None:
    report["updated_at"] = now()
    atomic_write_json(path, report)


def begin_stage(path: Path, report: dict[str, object], name: str) -> float:
    report["stages"][name] = {"status": "RUNNING", "started_at": now()}
    write_report(path, report)
    return time.perf_counter()


def finish_stage(
    path: Path,
    report: dict[str, object],
    name: str,
    started: float,
    *,
    status: str,
    data: dict[str, object] | None = None,
    error: BaseException | None = None,
) -> None:
    row: dict[str, object] = {
        "status": status,
        "started_at": report["stages"][name]["started_at"],
        "finished_at": now(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    if data:
        row.update(data)
    if error is not None:
        row["error_type"] = type(error).__name__
        row["error"] = str(error)[:1600]
        row["traceback_tail"] = traceback.format_exc()[-5000:]
    report["stages"][name] = row
    write_report(path, report)


def build_http_routes(context: dict[str, object]) -> dict[str, str]:
    routes = {
        "home": "/",
        "health": "/health",
        "papers": "/api/papers?limit=5",
        "authors": "/api/authors?limit=5",
        "search": "/api/search?q=test&limit=5",
        "identity_review": "/api/reviews/identity?limit=5",
    }
    if context.get("paper_id") is not None:
        routes["paper_detail"] = f"/api/papers/{context['paper_id']}"
    if context.get("author_id"):
        author_id = context["author_id"]
        routes["author_detail"] = f"/api/authors/{author_id}"
        routes["author_papers"] = f"/api/authors/{author_id}/papers"
        routes["author_coauthors"] = f"/api/authors/{author_id}/coauthors?limit=10"
    if context.get("reachable_pdf_paper_id") is not None:
        routes["pdf"] = f"/api/papers/{context['reachable_pdf_paper_id']}/pdf"
    return routes


def http_requests_pass(stage_data: dict[str, object]) -> bool:
    requests = stage_data.get("requests", {})
    if not isinstance(requests, dict):
        return False
    return bool(requests) and all(
        isinstance(row, dict) and row.get("status_code") == 200
        for row in requests.values()
    )


def query_stage(db_path: Path, sample_papers: int) -> tuple[dict[str, object], dict[str, object]]:
    engine = create_paperazzi_engine(db_path)
    sf = sa.orm.sessionmaker(bind=engine)
    context: dict[str, object] = {}
    try:
        with sf() as session:
            service = PaperazziQueryService(session)
            paper_count = session.query(Paper).filter(Paper.active_in_zotero.is_(True)).count()
            author_count = session.query(Author).filter_by(status="ACTIVE").count()
            source_author_mentions = (
                session.query(PaperCreatorMention)
                .filter(PaperCreatorMention.creator_type == "author")
                .count()
            )
            accepted_author_mentions = (
                session.query(sa.func.count(sa.distinct(AuthorIdentityMembership.creator_mention_id)))
                .join(
                    PaperCreatorMention,
                    PaperCreatorMention.creator_mention_id
                    == AuthorIdentityMembership.creator_mention_id,
                )
                .filter(
                    PaperCreatorMention.creator_type == "author",
                    AuthorIdentityMembership.status == "ACCEPTED",
                )
                .scalar()
                or 0
            )
            fk_rows = session.execute(sa.text("PRAGMA foreign_key_check")).fetchall()

            limit = paper_count if sample_papers <= 0 else min(sample_papers, paper_count)
            papers = (
                session.query(Paper)
                .filter(Paper.active_in_zotero.is_(True))
                .order_by(Paper.paper_id)
                .limit(limit)
                .all()
            )
            mismatches: list[dict[str, int]] = []
            mismatch_count = 0
            unresolved_visible = 0
            detail_latencies: list[float] = []
            for paper in papers:
                expected = (
                    session.query(PaperCreatorMention)
                    .filter_by(paper_id=paper.paper_id, creator_type="author")
                    .count()
                )
                started = time.perf_counter()
                detail = service.get_paper(paper.paper_id)
                detail_latencies.append((time.perf_counter() - started) * 1000)
                observed = len(detail["authors"])
                if expected != observed:
                    mismatch_count += 1
                    if len(mismatches) < 50:
                        mismatches.append(
                            {"paper_id": paper.paper_id, "expected": expected, "observed": observed}
                        )
                unresolved_visible += sum(
                    row["identity_status"] == "UNRESOLVED" for row in detail["authors"]
                )

            list_started = time.perf_counter()
            first_page = service.list_papers(limit=20)
            list_papers_ms = (time.perf_counter() - list_started) * 1000

            author_list_started = time.perf_counter()
            first_authors = service.list_authors(limit=20)
            list_authors_ms = (time.perf_counter() - author_list_started) * 1000

            search_checks: list[dict[str, object]] = []
            first_named = (
                session.query(Author)
                .filter(Author.status == "ACTIVE", Author.preferred_name.is_not(None))
                .order_by(Author.author_id)
                .first()
            )
            if first_named is not None and first_named.preferred_name:
                query = first_named.preferred_name
                started = time.perf_counter()
                result = service.search(query, limit=50)
                search_checks.append(
                    {
                        "kind": "AUTHOR_NAME",
                        "query": query,
                        "expected_author_id": first_named.author_id,
                        "found": any(r["author_id"] == first_named.author_id for r in result["authors"]),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
                context["author_id"] = first_named.author_id

            first_paper = (
                session.query(Paper)
                .filter(Paper.active_in_zotero.is_(True), Paper.title.is_not(None))
                .order_by(Paper.paper_id)
                .first()
            )
            if first_paper is not None and first_paper.title:
                query = first_paper.title
                started = time.perf_counter()
                result = service.search(query, limit=50)
                search_checks.append(
                    {
                        "kind": "PAPER_TITLE",
                        "query": query,
                        "expected_paper_id": first_paper.paper_id,
                        "found": any(r["paper_id"] == first_paper.paper_id for r in result["papers"]),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
                context["paper_id"] = first_paper.paper_id

            doi_paper = (
                session.query(Paper)
                .filter(Paper.active_in_zotero.is_(True), Paper.doi.is_not(None))
                .order_by(Paper.paper_id)
                .first()
            )
            if doi_paper is not None and doi_paper.doi:
                started = time.perf_counter()
                result = service.search(doi_paper.doi, limit=50)
                search_checks.append(
                    {
                        "kind": "DOI",
                        "query": doi_paper.doi,
                        "expected_paper_id": doi_paper.paper_id,
                        "found": any(r["paper_id"] == doi_paper.paper_id for r in result["papers"]),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )

            pdf_rows = (
                session.query(PaperDocument)
                .filter_by(availability_status="PDF_AVAILABLE", present_in_last_scan=True)
                .all()
            )
            reachable_pdf_rows = 0
            stale_pdf_count = 0
            stale_pdf_examples: list[int] = []
            for row in pdf_rows:
                if row.local_path and Path(row.local_path).is_file():
                    reachable_pdf_rows += 1
                    if context.get("reachable_pdf_paper_id") is None:
                        context["reachable_pdf_paper_id"] = row.paper_id
                else:
                    stale_pdf_count += 1
                    if len(stale_pdf_examples) < 20:
                        stale_pdf_examples.append(row.paper_id)

            search_ok = bool(search_checks) and all(bool(row["found"]) for row in search_checks)
            data = {
                "paper_count": paper_count,
                "active_canonical_authors": author_count,
                "source_author_mentions": source_author_mentions,
                "accepted_author_mentions": int(accepted_author_mentions),
                "unresolved_author_mentions": source_author_mentions - int(accepted_author_mentions),
                "sampled_papers": len(papers),
                "full_corpus_projection_check": len(papers) == paper_count,
                "source_author_projection_mismatch_count": mismatch_count,
                "source_author_projection_mismatch_examples": mismatches,
                "unresolved_source_authors_visible_in_sample": unresolved_visible,
                "search_smoke_passed": search_ok,
                "search_checks": search_checks,
                "pdf_available_rows": len(pdf_rows),
                "reachable_pdf_rows": reachable_pdf_rows,
                "stale_pdf_available_rows": stale_pdf_count,
                "stale_pdf_available_example_paper_ids": stale_pdf_examples,
                "foreign_key_check_rows": len(fk_rows),
                "performance_ms": {
                    "list_papers_20": round(list_papers_ms, 3),
                    "list_authors_20": round(list_authors_ms, 3),
                    "paper_detail_count": len(detail_latencies),
                    "paper_detail_p50": percentile(detail_latencies, 0.50),
                    "paper_detail_p95": percentile(detail_latencies, 0.95),
                    "paper_detail_max": round(max(detail_latencies), 3) if detail_latencies else None,
                    "paper_detail_mean": round(statistics.mean(detail_latencies), 3) if detail_latencies else None,
                },
                "first_page_returned": len(first_page["items"]),
                "first_author_page_returned": len(first_authors["items"]),
            }
            data["pass"] = bool(
                paper_count > 0
                and author_count > 0
                and mismatch_count == 0
                and search_ok
                and len(fk_rows) == 0
            )
            return data, context
    finally:
        engine.dispose()


def main() -> int:
    args = parse_args()
    if not args.db_path.is_file():
        raise FileNotFoundError(args.db_path)

    report: dict[str, object] = {
        "schema": "paperazzi.phase5_real_db_validation.v2",
        "phase": "PHASE_5",
        "status": "IN_PROGRESS",
        "created_at": now(),
        "database": str(args.db_path.resolve()),
        "environment": environment_snapshot(),
        "canonical_test_environment": compare_constraints(
            REPO_ROOT / "constraints" / "phase5-test.txt"
        ),
        "parameters": {
            "sample_papers": args.sample_papers,
            "request_timeout": args.request_timeout,
            "startup_timeout": args.startup_timeout,
        },
        "stages": {
            "REAL_DATABASE_QUERY": {"status": "NOT_RUN"},
            "ASGI_IN_PROCESS": {"status": "NOT_RUN"},
            "UVICORN_LOCALHOST_HTTP": {"status": "NOT_RUN"},
        },
    }
    write_report(args.report_path, report)

    context: dict[str, object] = {}
    started = begin_stage(args.report_path, report, "REAL_DATABASE_QUERY")
    try:
        query_data, context = query_stage(args.db_path, args.sample_papers)
        finish_stage(
            args.report_path, report, "REAL_DATABASE_QUERY", started,
            status="PASS" if query_data["pass"] else "FAIL", data=query_data,
        )
    except Exception as exc:
        finish_stage(
            args.report_path, report, "REAL_DATABASE_QUERY", started,
            status="ERROR", error=exc,
        )

    routes = build_http_routes(context)

    started = begin_stage(args.report_path, report, "ASGI_IN_PROCESS")
    try:
        asgi = run_asgi_smoke(
            create_app(args.db_path), routes, request_timeout=args.request_timeout
        )
        asgi_ok = asgi.get("status") == "PASS" and http_requests_pass(asgi)
        finish_stage(
            args.report_path, report, "ASGI_IN_PROCESS", started,
            status="PASS" if asgi_ok else "FAIL", data=asgi,
        )
    except Exception as exc:
        finish_stage(
            args.report_path, report, "ASGI_IN_PROCESS", started,
            status="ERROR", error=exc,
        )

    started = begin_stage(args.report_path, report, "UVICORN_LOCALHOST_HTTP")
    try:
        uvicorn = run_uvicorn_smoke(
            args.db_path, routes,
            startup_timeout=args.startup_timeout,
            request_timeout=args.request_timeout,
        )
        uvicorn_ok = uvicorn.get("status") == "PASS" and http_requests_pass(uvicorn)
        finish_stage(
            args.report_path, report, "UVICORN_LOCALHOST_HTTP", started,
            status="PASS" if uvicorn_ok else "FAIL", data=uvicorn,
        )
    except Exception as exc:
        finish_stage(
            args.report_path, report, "UVICORN_LOCALHOST_HTTP", started,
            status="ERROR", error=exc,
        )

    stages = report["stages"]
    mandatory = ("REAL_DATABASE_QUERY", "ASGI_IN_PROCESS", "UVICORN_LOCALHOST_HTTP")
    report["status"] = "PASS" if all(stages[name]["status"] == "PASS" for name in mandatory) else "FAIL"
    report["product_path_status"] = (
        "PASS"
        if stages["REAL_DATABASE_QUERY"]["status"] == "PASS"
        and stages["UVICORN_LOCALHOST_HTTP"]["status"] == "PASS"
        else "FAIL"
    )
    report["in_process_harness_status"] = stages["ASGI_IN_PROCESS"]["status"]
    write_report(args.report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
