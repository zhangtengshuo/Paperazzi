# Phase 5 Test Report

Date: 2026-08-17 10:10:03 Asia/Shanghai
Repository commit: `a071163 Add Phase 5 local AI real-database test contract`
Branch: `main`

## Environment

```text
OS: Linux 6.18.33.2-microsoft-standard-WSL2 x86_64
Python: 3.13.9 (Anaconda, GCC 11.2.0)
SQLite runtime: 3.51.0
FastAPI: 0.136.1
Starlette: 1.0.0
HTTPX: 0.28.1
AnyIO: 4.10.0
SQLAlchemy: 2.0.43
Alembic: 1.19.1
PyMuPDF: 1.27.2.3
Uvicorn: 0.46.0
Pydantic: 2.12.4
```

The installed web dependencies satisfy the project extras in `pyproject.toml` (`FastAPI>=0.115`, `uvicorn>=0.30`, `httpx>=0.27`).

## Test results

### Existing regression and query-layer tests

- All 96 existing Phase 3/Phase 4 tests reached `ok` in the full-suite run.
- `test_paper_detail_starts_from_complete_source_authors`: **PASS**.
- `test_author_profile_and_search`: **PASS**.
- These cover source-author visibility, unresolved identity display, roles, author profiles and search.

### HTTP test failure

`tests.test_phase5_web.Phase5WebTests.test_http_mvp_routes` does not complete. It hangs on the first request:

```text
tests/test_phase5_web.py:147
self.assertEqual(client.get("/").status_code, 200)
```

Reproduction with traceback timer:

```text
timeout 25s python -c "... TestClient ... test_http_mvp_routes ..."
exit code: 124
```

The traceback shows the request waiting inside the test-client portal rather than inside an application handler:

```text
selectors.select
asyncio.base_events.run_forever
anyio._backends._asyncio.run_blocking_portal
anyio.from_thread.run_blocking_portal
starlette.testclient.handle_request
httpx._client.request
starlette.testclient.get
tests/test_phase5_web.py:147
```

A minimal FastAPI application with one `GET /` route and the same `TestClient` also hangs and exits 124 after 15 seconds. This indicates an environment/test-harness compatibility issue in the Starlette/AnyIO request path; no route assertion or application exception was observed.

### Real-database smoke validator

```text
timeout 45s python scripts/validate_phase5.py
exit code: 124
phase5_report.json: not generated
```

The validator uses `TestClient`, so it reaches the same request-level hang before producing its report.

## Phase status

Phase 4 is closed as `PASS` in `docs/phase4/PHASE4_CLOSEOUT.md`. Phase 5 is not yet fully validated:

```text
PHASE_4_STATUS = PASS
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
PHASE_5_STATUS = BLOCKED_ON_HTTP_TEST_HARNESS
```

Recommended next action: pin or adjust the compatible Starlette/AnyIO/HTTPX test stack, or migrate the HTTP tests/smoke validator to a verified ASGI transport, then rerun the full suite and `scripts/validate_phase5.py`.
