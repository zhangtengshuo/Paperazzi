# Phase 5 Validation Architecture

## Environment contract

Authoritative local Phase 5 work has one required Python environment:

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
pinned dependencies = constraints/phase5-test.txt
```

The user's existing Anaconda `base` and other pre-existing Python environments are diagnostic context only. They must not be upgraded, downgraded, or otherwise changed for Paperazzi.

Create the isolated environment from the repository root:

```bash
micromamba create -y -f environment/Paperazzi.yml
micromamba run -n Paperazzi python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The checker must return `"pass": true` before authoritative local tests or real-library validation run. If `Paperazzi` already exists, only that environment may be repaired/updated.

All local commands in this document are conceptually executed through `micromamba run -n Paperazzi ...`; shell activation is optional and must not be relied upon for correctness.

GitHub Actions is already an ephemeral isolated environment and therefore remains free to use `actions/setup-python`; it validates the same dependency constraints on Python 3.11 and 3.13.

## Purpose

Phase 5 validation distinguishes three independent layers:

```text
real Paperazzi DB/query semantics
        ↓
in-process ASGI adapter
        ↓
real localhost Uvicorn server
```

A later-layer failure must not erase evidence already collected from an earlier layer.

## Why synchronous TestClient was removed

The first real-DB validator accumulated results in memory and wrote its report only after Starlette `TestClient` requests completed. In the user's former Anaconda/Python 3.13 environment, the request hung inside the AnyIO blocking portal before a Paperazzi handler ran. The timeout also discarded earlier real-DB observations.

The revised design removes synchronous Starlette/FastAPI `TestClient` from authoritative Phase 5 validation.

### In-process HTTP

```text
httpx.ASGITransport
+
httpx.AsyncClient
```

### Product-path HTTP

A real Uvicorn subprocess is started on a temporary localhost port and queried with a normal `httpx.Client`.

The localhost client uses `trust_env=false`, preventing `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` from silently redirecting the smoke test. Reports record only whether proxy variables exist, never their values.

## Failure-isolated report

`scripts/validate_phase5.py` writes `data/phase5-validation/phase5_report.json` before testing starts and atomically rewrites it at each stage transition.

```text
REAL_DATABASE_QUERY
ASGI_IN_PROCESS
UVICORN_LOCALHOST_HTTP
```

A hard failure during a later stage therefore preserves earlier evidence.

## Canonical dependency baseline

`constraints/phase5-test.txt` defines the reproducible dependency set. `pyproject.toml` still expresses supported lower bounds; the constraints file defines the authoritative local/CI validation baseline.

Before running the validator, `scripts/check_paperazzi_environment.py` verifies:

```text
active environment name = Paperazzi
Python = 3.13
installed package versions match constraints/phase5-test.txt
```

The environment contract records whether micromamba context markers are visible, but it does not rely solely on those markers because `micromamba run` implementations may expose them differently. Creation with micromamba remains a documented project rule.

## Automated PASS semantics

The validation JSON exposes:

```text
status
product_path_status
in_process_harness_status
```

`product_path_status=PASS` requires:

```text
REAL_DATABASE_QUERY = PASS
UVICORN_LOCALHOST_HTTP = PASS
```

Final automated `status=PASS` additionally requires `ASGI_IN_PROCESS=PASS`.

## Real-database information collected

The validator records:

- active papers and canonical authors;
- source/accepted/unresolved author mentions;
- source-author projection mismatches;
- unresolved authors visible in paper details;
- `PRAGMA foreign_key_check`;
- real title/author/DOI search checks;
- `PDF_AVAILABLE`, reachable, and stale PDF counts;
- list/detail timing statistics;
- ASGI route statuses/timings;
- Uvicorn route statuses/timings and server log tail.

## Required local execution

First verify the environment:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

Then run the suite and real DB smoke:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3
```

For full-corpus author projection:

```bash
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3 --sample-papers 0
```

`--sample-papers 0` means all active papers.

## Interpretation

### Query PASS + ASGI PASS + Uvicorn PASS

Automated Phase 5 real-database validation is healthy. Continue with manual browser semantic inspection.

### Query PASS + ASGI FAIL + Uvicorn PASS

The product path is working. Investigate the in-process harness/dependency state; do not rewrite Paperazzi query semantics merely to satisfy an adapter.

### Query PASS + ASGI PASS + Uvicorn FAIL

Treat as a deployment-path or localhost environment defect. Preserve server log tail, routes, environment checker result, and DB identity.

### Query FAIL

Treat as the highest-priority Phase 5 defect. Preserve paper/author IDs and mismatch examples. Never solve it by force-merging identities or hiding unresolved source authors.

## Local AI evidence required for remote review

The local AI must return more than PASS/FAIL. The tracked report should include:

```text
micromamba version
confirmation that Paperazzi is a separate environment
environment checker PASS/FAIL
Python version
pip check result
constraint mismatches if any
full regression count/result
real DB scale and full-corpus projection result
ASGI and Uvicorn route timings
real search examples and timings
PDF reachability/stale counts
browser smoke result
high-publication/high-degree author performance observations
warnings/exceptions that may matter later
```

For environment differences, report package names/versions and module origins when useful, but do not commit proxy credentials, tokens, cookies, or unnecessary machine-local filesystem paths.

## Manual browser validation

Verify:

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

Visual polish is not a correctness gate; semantic loss, unsafe file access, broken navigation, or pathological latency is.
