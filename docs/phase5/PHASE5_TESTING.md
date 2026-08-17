# Phase 5 Validation Architecture

## Purpose

Phase 5 validation must distinguish three independent layers:

```text
real Paperazzi DB/query semantics
        ↓
in-process ASGI adapter
        ↓
real localhost Uvicorn server
```

A failure in a later layer must not erase evidence already collected from an earlier layer.

## Why the previous validator was changed

The first Phase 5 real-DB validator accumulated all results in memory and wrote its JSON report only after synchronous Starlette `TestClient` requests completed. On the user's Anaconda/Python 3.13 environment, `TestClient` hung inside the AnyIO blocking portal before an application handler ran. The process timed out and the already-completed real-DB observations were lost.

The revised design removes `TestClient` from Phase 5 validation.

### In-process HTTP

Use:

```text
httpx.ASGITransport
+
httpx.AsyncClient
```

This tests the ASGI application directly without Starlette's synchronous blocking-portal wrapper.

### Product-path HTTP

Start a real Uvicorn subprocess on a temporary localhost port and query it with a normal `httpx.Client`.

The localhost client always uses:

```text
trust_env = false
```

so `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` in the user's shell cannot silently redirect the Paperazzi localhost smoke test. The report records only whether proxy variables are present, never their values.

## Failure-isolated report

`scripts/validate_phase5.py` writes:

```text
data/phase5-validation/phase5_report.json
```

before testing starts, then atomically rewrites it at every stage transition.

Stages:

```text
REAL_DATABASE_QUERY
ASGI_IN_PROCESS
UVICORN_LOCALHOST_HTTP
```

A hard timeout during `ASGI_IN_PROCESS`, for example, leaves:

```json
{
  "REAL_DATABASE_QUERY": {"status": "PASS"},
  "ASGI_IN_PROCESS": {"status": "RUNNING"},
  "UVICORN_LOCALHOST_HTTP": {"status": "NOT_RUN"}
}
```

instead of losing the real-database result.

## Canonical test environment

Runtime compatibility remains broader than one Python minor release, but Paperazzi now has a reproducible Phase 5 validation stack:

```text
constraints/phase5-test.txt
```

Install with:

```bash
python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
```

The canonical CI matrix currently validates Python 3.11 and Python 3.13 with the same pinned dependency set.

`pyproject.toml` continues to express supported lower bounds. The constraints file defines the reproducible test baseline; the two serve different purposes.

The validator records:

```text
Python executable and prefix
platform
SQLite runtime
package versions
module origins
Conda environment name
event-loop policy
proxy-variable presence
canonical-constraint match/mismatch
```

This is important because "same package requirements" is not equivalent to "same resolved environment."

## Automated PASS semantics

The JSON report exposes both:

```text
status
product_path_status
in_process_harness_status
```

`product_path_status=PASS` means:

```text
REAL_DATABASE_QUERY = PASS
UVICORN_LOCALHOST_HTTP = PASS
```

The final automated `status=PASS` additionally requires `ASGI_IN_PROCESS=PASS`.

This distinction prevents an in-process harness problem from being misreported as a product HTTP failure while still requiring the canonical test environment to make all automated layers green.

## Real-database information collected

The validator records:

- active paper count;
- active canonical author count;
- source author mentions;
- accepted and unresolved author mentions;
- source-author projection mismatches;
- unresolved authors still visible in sampled paper details;
- `PRAGMA foreign_key_check`;
- real title/author/DOI search checks;
- `PDF_AVAILABLE` rows;
- actually reachable PDF rows;
- stale `PDF_AVAILABLE` row count and example paper IDs;
- list and paper-detail timing statistics;
- ASGI route statuses/timings;
- Uvicorn route statuses/timings and server log tail.

Filesystem paths are not included in the stale-PDF examples.

## Recommended execution

A normal smoke run:

```bash
python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3
```

A complete paper-projection pass:

```bash
python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3 --sample-papers 0
```

`--sample-papers 0` explicitly means all active papers.

## Interpretation

### Query PASS + ASGI PASS + Uvicorn PASS

The automated Phase 5 real-database stack is healthy. Continue with browser/manual semantic inspection.

### Query PASS + ASGI FAIL + Uvicorn PASS

The product path is working. Investigate the in-process Python/ASGI environment. Compare the validator's installed package versions and module origins with `constraints/phase5-test.txt`; do not rewrite Paperazzi query logic merely to make a test adapter work.

### Query PASS + ASGI PASS + Uvicorn FAIL

This is a real deployment-path defect or localhost environment problem. Uvicorn log tail, route status, Python executable, proxy-presence flags, and exact tested DB must be retained.

### Query FAIL

Treat this as the highest-priority Phase 5 defect. Preserve paper/author IDs and mismatch examples. Do not solve it by force-merging identities or filtering unresolved source authors.

## Manual browser validation

Automated localhost HTTP is not a substitute for one final browser check. The local AI should verify:

```text
paper list
search
paper detail
all source authors
resolved author profile
coauthors
identity review
PDF opening
```

Visual polish is not a correctness gate at this stage; semantic loss, broken navigation, unsafe file access, or pathological latency is.
