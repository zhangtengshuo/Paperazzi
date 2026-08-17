# Phase 5 Test Report

Date: 2026-08-17 10:57:31–10:57:39 Asia/Shanghai
Repository commit: `b3996d1 Test Phase 5 micromamba environment gate`
Branch at validation: `main`

## Result

```text
PHASE_5_STATUS = PASS
PRODUCT_PATH_STATUS = PASS
IN_PROCESS_HARNESS_STATUS = PASS
```

The authoritative local validation completed in the dedicated `Paperazzi`
micromamba environment. The JSON validator output was written to the local
ignored path `data/phase5-validation/phase5_report.json`; this tracked Markdown
file preserves the reviewable result.

## Environment contract

```text
Environment manager: micromamba 2.8.1
Environment name: Paperazzi
Separate environment: PASS; not the existing Anaconda/base environment
Python: 3.13.15
SQLite runtime: 3.53.4
Platform: Linux x86_64 under WSL2
Environment checker: PASS
pip check: PASS (No broken requirements found.)
```

The pinned dependency contract matched with no mismatches:

```text
SQLAlchemy 2.0.52
Alembic 1.19.1
PyMuPDF 1.28.2
FastAPI 0.141.1
Starlette 1.6.0
httpx 0.28.1
anyio 4.14.2
uvicorn 0.52.3
pydantic 2.13.4
```

Proxy variables were present in the process environment, but the localhost
smoke client used `trust_env=false`; proxy values were not recorded.

## Regression suite

```text
Command: python -m unittest discover -s tests -v
Result: PASS
Tests: 107
Elapsed: 33.824 seconds
```

All 107 tests completed successfully.

## Real database validation

```text
Database: data/phase4-validation/paperazzi.sqlite3
Sample papers: 2513 (full corpus; --sample-papers 0)
Papers: 2513
Active canonical authors: 7398
Source author mentions: 12207
Accepted author mentions: 10448
Unresolved author mentions: 1759
Full-corpus source-author projection mismatches: 0
Foreign-key check errors: 0
PDF_AVAILABLE rows: 2161
Reachable PDF rows: 2161
Stale PDF rows: 0
```

The three real search checks all passed:

| Check | Query | Result | Time |
| --- | --- | --- | ---: |
| Author name | `Damiano Aliverti-Piuri` | found | 30.305 ms |
| Paper title | `Geometric Optimization of Restricted-Open and Complete Active Space Self-Consistent Field Wave Functions` | found | 24.686 ms |
| DOI | `10.1021/acs.jpca.4c03213` | found | 23.532 ms |

Database and detail timings:

```text
list papers (20): 19.888 ms
list authors (20): 85.788 ms
paper detail requests: 2513
paper detail p50: 1.504 ms
paper detail p95: 1.932 ms
paper detail mean: 1.541 ms
paper detail max: 23.775 ms
```

High-publication/high-degree author performance was not separately isolated in
this run. The full-corpus paper-detail measurement above is the available
performance observation; a targeted author-degree benchmark remains future
work.

## HTTP validation

### ASGI in-process

`ASGI_IN_PROCESS = PASS` using `httpx.ASGITransport` and `httpx.AsyncClient`.

| Route | Status | Time |
| --- | ---: | ---: |
| `/` | 200 | 3.504 ms |
| `/health` | 200 | 1.364 ms |
| `/api/papers?limit=5` | 200 | 10.901 ms |
| `/api/authors?limit=5` | 200 | 26.325 ms |
| `/api/search?q=test&limit=5` | 200 | 37.233 ms |
| `/api/reviews/identity?limit=5` | 200 | 451.042 ms |
| `/api/papers/1` | 200 | 4.174 ms |
| `/api/authors/{author_id}` | 200 | 9.158 ms |
| `/api/authors/{author_id}/papers` | 200 | 6.555 ms |
| `/api/authors/{author_id}/coauthors?limit=10` | 200 | 6.446 ms |
| `/api/papers/1/pdf` | 200 | 45.133 ms |

### Real Uvicorn localhost HTTP

`UVICORN_LOCALHOST_HTTP = PASS`; the server started successfully and its log
tail was empty.

| Route | Status | Time |
| --- | ---: | ---: |
| `/` | 200 | 0.994 ms |
| `/health` | 200 | 0.901 ms |
| `/api/papers?limit=5` | 200 | 20.746 ms |
| `/api/authors?limit=5` | 200 | 30.751 ms |
| `/api/search?q=test&limit=5` | 200 | 37.206 ms |
| `/api/reviews/identity?limit=5` | 200 | 447.136 ms |
| `/api/papers/1` | 200 | 3.974 ms |
| `/api/authors/{author_id}` | 200 | 8.558 ms |
| `/api/authors/{author_id}/papers` | 200 | 6.604 ms |
| `/api/authors/{author_id}/coauthors?limit=10` | 200 | 7.542 ms |
| `/api/papers/1/pdf` | 200 | 48.529 ms |

### Browser smoke

Manual browser interaction was not run in this headless validation session.
Automated product-path smoke covered the home page, health, paper list/detail,
search, author profile, author papers/coauthors, identity review, and PDF
routes through both ASGI and real localhost Uvicorn; all returned HTTP 200.

## Warnings and follow-up

- The regression run emitted `ResourceWarning` messages for unclosed SQLite
  connections in `test_duplicate_identity_rejected`; the test still passed.
- `src/paperazzi/zotero_sqlite/probe.py` emitted a Python deprecation warning
  for `sqlite3.version`; the test still passed.
- No application exception, Uvicorn startup error, projection mismatch,
  foreign-key error, or stale PDF was observed.
