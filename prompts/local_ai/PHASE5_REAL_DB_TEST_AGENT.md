# Paperazzi Phase 5 — Local AI Real-Database Validation Agent v2

## Mission

You are the local validation agent for Paperazzi Phase 5. You have access to the user's real Paperazzi SQLite database and local Zotero/PDF filesystem that GitHub Actions cannot see.

Your job is to validate the current `main` implementation, preserve useful evidence when something fails, and return enough structured information for a remote reviewer to decide whether the problem is:

```text
Paperazzi semantic/query defect
ASGI in-process test-environment defect
real Uvicorn/product-path defect
local filesystem/PDF state
performance limitation
dependency/environment mismatch
```

Do not manufacture data and do not weaken Phase 4 identity safety to make Phase 5 green.

---

## Read first

```text
docs/phase4/PHASE4_CLOSEOUT.md
docs/phase5/README.md
docs/phase5/PHASE5_TESTING.md
constraints/phase5-test.txt
scripts/validate_phase5.py
src/paperazzi/web/validation.py
src/paperazzi/web/queries.py
src/paperazzi/web/api.py
```

Expected state:

```text
PHASE_4_STATUS = PASS
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```

Work on `main`. Do not create a branch or PR for this validation task unless the user explicitly changes that policy.

---

# Non-negotiable data rules

- Zotero `zotero.sqlite`, `storage/`, and PDFs are read-only.
- Paperazzi source author truth comes from `paper_creator_mentions`.
- Every Zotero paper author must remain visible even when canonical identity is unresolved.
- `FIRST` and `CORRESPONDING` are additive authorship roles, not inclusion filters.
- Do not force-resolve identities to increase coverage.
- Do not create fake `ACCEPTED` references or correspondence evidence.
- Missing/unreachable PDFs may be valid data states.
- `PDF_AVAILABLE` pointing to a missing file should be reported as stale/inconsistent state, not silently repaired.
- Validation must not mutate semantic tables.

---

# Important change from the previous test contract

Do **not** use Starlette/FastAPI synchronous `TestClient` as the authoritative Phase 5 HTTP test.

The new stack is:

```text
Layer 1: PaperazziQueryService against real DB
Layer 2: httpx.ASGITransport + AsyncClient
Layer 3: real Uvicorn subprocess + localhost HTTP
Layer 4: manual browser check
```

The validator persists every stage before and after execution. If a process hangs or is killed, keep the existing JSON file; its last `RUNNING` stage identifies where execution stopped.

Localhost HTTP validation disables inherited HTTP proxy routing with `trust_env=False`.

---

# Stage 0 — Repository and environment capture

Before installing or changing anything, record the current native environment:

```text
branch
commit SHA
working-tree state
Python version
Python executable
sys.prefix
CONDA_DEFAULT_ENV if present
SQLite runtime
FastAPI
Starlette
HTTPX
AnyIO
SQLAlchemy
Alembic
PyMuPDF
Uvicorn
Pydantic
```

Also record only the Boolean presence of:

```text
HTTP_PROXY
HTTPS_PROXY
ALL_PROXY
NO_PROXY
```

Never write proxy URLs, usernames, passwords, tokens, cookies, API keys, or credentials into Git-tracked reports.

Run `python -m pip check` and record whether dependency consistency passes.

## Native-vs-canonical comparison

First, if practical, run the revised validator once in the user's existing environment **without changing package versions**. This tells us whether removing `TestClient` already fixes the original Anaconda/Python 3.13 failure.

Then inspect:

```text
canonical_test_environment.matches
```

inside the validator report.

If `false`, also run the mandatory final validation in a dedicated environment installed with:

```bash
python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
```

Do not destructively downgrade the user's general-purpose Anaconda base environment merely to match Paperazzi. Prefer a dedicated venv/Conda env.

A final PASS claim must identify which environment produced it.

---

# Stage 1 — Full regression suite

Run:

```bash
python -m unittest discover -s tests -v
```

The revised suite must include at least:

```text
source-author completeness test
author profile/search test
ASGITransport HTTP test
real Uvicorn localhost smoke test
failure-isolated report infrastructure tests
```

Record:

```text
test count
passes
failures
errors
skips
total runtime
```

If a test fails, classify whether the failure reproduces in the canonical constrained environment before editing Paperazzi code.

---

# Stage 2 — Real DB smoke, failure-isolated

Run against the actual existing DB:

```bash
python scripts/validate_phase5.py --db-path <REAL_DB_PATH>
```

Do not create an empty DB if the expected path is missing.

The report is:

```text
data/phase5-validation/phase5_report.json
```

Immediately inspect and preserve it even if the command exits nonzero.

Required stages:

```text
REAL_DATABASE_QUERY
ASGI_IN_PROCESS
UVICORN_LOCALHOST_HTTP
```

For each stage report:

```text
status
elapsed_ms
failure/exception if any
```

The automated final status is PASS only when all three pass.

Also report separately:

```text
product_path_status
in_process_harness_status
```

If `product_path_status=PASS` but ASGI fails, do not call the Paperazzi web product broken. Report an in-process environment/harness defect and compare dependency/module origins.

---

# Stage 3 — Full-corpus source-author projection

After the 200-paper smoke passes, run:

```bash
python scripts/validate_phase5.py --db-path <REAL_DB_PATH> --sample-papers 0
```

`0` means all active papers.

Required:

```text
full_corpus_projection_check = true
source_author_projection_mismatch_count = 0
```

If any mismatch exists, preserve every available example paper ID and compare:

```text
paper_creator_mentions(author)
vs
PaperazziQueryService.get_paper()["authors"]
```

Do not repair by filtering unresolved source authors.

---

# Stage 4 — Information that MUST be returned to the remote reviewer

This section is mandatory. The purpose is not merely to say PASS/FAIL; return information useful for the next design decision.

## A. Environment reproducibility

Return:

```text
native environment:
  Python executable/version
  Conda/venv identity
  canonical constraints match true/false
  pip check pass/fail

canonical validation environment:
  Python executable/version
  canonical constraints match true/false
  pip check pass/fail
```

For every mismatch against `constraints/phase5-test.txt`, list:

```text
package
expected version
installed version
module origin
```

Module origin is important: two environments can report similar versions while importing different installations.

If the native environment still fails but canonical passes, preserve both reports.

## B. Real database scale and identity coverage

Return:

```text
active papers
active canonical authors
source author mentions
accepted author mentions
unresolved author mentions
full-corpus papers checked
source-author projection mismatch count
unresolved source authors visible in checked paper details
foreign-key check rows
```

Do not interpret unresolved identities as missing author records.

## C. HTTP layer separation

Return route status and elapsed time for both:

```text
ASGI_IN_PROCESS
UVICORN_LOCALHOST_HTTP
```

At minimum:

```text
/
/health
/api/papers
/api/authors
/api/search
/api/reviews/identity
one real paper detail
one real author detail
one author publications route
one coauthors route
one PDF route when a reachable PDF exists
```

If Uvicorn fails, include its `server_log_tail`.

If ASGI fails while Uvicorn passes, include the ASGI exception/timeout and do not alter business logic without evidence.

## D. Search behavior using REAL corpus values

Test and return the exact scholarly queries used:

```text
one full or distinctive paper title
one DOI
one journal/venue fragment
one canonical author name
one non-ASCII author name if available
one punctuation-heavy title or DOI if available
```

For each return:

```text
query
expected object
found true/false
elapsed_ms
unexpected results if material
```

If no suitable non-ASCII/punctuation case exists, state `NOT_AVAILABLE_IN_CORPUS`; do not invent one.

## E. PDF state

Return:

```text
PDF_AVAILABLE rows
actually reachable PDF rows
number of stale PDF_AVAILABLE rows
up to 20 stale example paper IDs
successful PDF HTTP paper ID(s)
controlled unavailable-PDF example paper ID
```

Do **not** commit full local filesystem paths unless needed to diagnose a path-mapping defect. Paper IDs are preferred.

If many PDFs are stale, determine whether the DB simply needs a normal Zotero/Paperazzi rescan or whether path projection is wrong.

## F. Measured performance

Return at minimum:

```text
list_papers(20) elapsed_ms
list_authors(20) elapsed_ms
paper detail mean
paper detail p50
paper detail p95
paper detail max
ASGI route timings
Uvicorn route timings
```

Also manually measure:

```text
common author search
distinctive title search
author profile for a high-publication-count author
coauthor list for a high-degree author
```

Do not add FTS5 simply because it was previously planned. Report measurements first.

If one path is disproportionately slow, identify query type and relevant author/paper ID so the remote reviewer can decide whether indexing, batching, or query refactoring is justified.

## G. Original hang comparison

The previous local environment was approximately:

```text
Python 3.13.9 Anaconda
FastAPI 0.136.1
Starlette 1.0.0
HTTPX 0.28.1
AnyIO 4.10.0
```

and synchronous Starlette `TestClient` hung in `AnyIO BlockingPortal`.

After pulling the fix, explicitly answer:

```text
Does the revised ASGITransport test pass in the original/native environment?
Does real Uvicorn localhost HTTP pass in that environment?
Does the canonical constrained environment pass?
```

This comparison is especially important. It tells us whether the defect was solely the old test adapter or a broader Python 3.13/Conda incompatibility.

---

# Stage 5 — Manual semantic spot checks

Inspect real papers containing unresolved source authors.

For several cases confirm:

```text
source display name visible
author order preserved
identity_status=UNRESOLVED when appropriate
FIRST survives unresolved canonical identity
CORRESPONDING appears only with accepted semantic evidence
```

Inspect canonical authors including:

```text
single-paper author
multi-paper author
first author
corresponding author if available
high-publication-count author
high-coauthor-degree author
```

Check publication counts and coauthors against direct DB facts.

Preserve paper IDs/author IDs for any discrepancy.

---

# Stage 6 — Browser/product smoke

Start the product against the tested DB and inspect in a real browser.

Verify:

```text
home loads
paper list loads
real search works
paper detail opens
all source authors appear
resolved author link opens profile
publication list/coauthors load
identity review loads
reachable PDF opens
unavailable PDF fails in a controlled way
```

Do not fail Phase 5 for visual polish alone.

Report browser and operating context:

```text
browser name/version if easily available
WSL/native Linux/Windows context
URL used
whether browser and server were on the same host
```

If browser behavior differs from automated localhost HTTP, that difference is important and must be reported.

---

# Stage 7 — Optional but strongly recommended identity precision audit

After Phase 5 smoke is stable, run:

```bash
python scripts/export_identity_precision_audit.py
```

This does not gate Phase 5, but it is important quality information because stable/idempotent identity resolution does not prove precision.

Review the deterministic stratified sample, emphasizing:

```text
SAME_NORMALIZED_NAME_MULTIPLE_IDENTITIES
THRESHOLD_EDGE
FIRST_AUTHOR
HIGH_PUBLICATION_DEGREE
East-Asian/common names when represented
```

Return summary counts:

```text
CORRECT
FALSE_MERGE
UNCERTAIN
```

For every convincing `FALSE_MERGE`, return:

```text
author_id
creator_mention_id
paper_id
source name
why the merge appears false
independent evidence used
```

Do not lower/raise thresholds solely from a tiny sample; use false merges to construct reproducible regression cases first.

---

# Failure handling

If any mandatory stage fails:

1. Preserve `phase5_report.json` immediately.
2. Preserve exact paper/author IDs and route.
3. Identify the layer:
   - real DB/query;
   - ASGI in-process;
   - Uvicorn/product;
   - browser;
   - filesystem/PDF;
   - environment/dependency.
4. Compare native vs canonical environment.
5. Add a regression test before fixing application behavior.
6. Fix only the responsible layer.
7. Rerun the full regression suite.
8. Rerun 200-paper smoke.
9. Rerun full-corpus projection if smoke passes.

Never solve a web/display failure by weakening Phase 4 identity resolution.

---

# Required tracked report

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-real-db-v2/PHASE5_REAL_DB_TEST_RESULTS.md
```

It must include:

1. tested commit/branch;
2. native environment and canonical environment comparison;
3. regression-suite result;
4. full `REAL_DATABASE_QUERY` summary;
5. ASGI and Uvicorn status/timings;
6. real search cases;
7. PDF reachability/stale-state summary;
8. manual semantic spot checks;
9. browser smoke result;
10. measured performance;
11. defects/fixes;
12. optional identity precision audit summary;
13. explicit information requested for remote review.

Do not commit `phase5_report.json` if it contains machine-local paths; quote the useful non-sensitive fields in the Markdown report instead.

---

# Final status vocabulary

Use exactly one automated state:

```text
PHASE_5_REAL_DB_SMOKE = PASS
PHASE_5_REAL_DB_SMOKE = FAIL
```

Also report:

```text
PRODUCT_PATH_STATUS = PASS|FAIL
ASGI_HARNESS_STATUS = PASS|FAIL|ERROR
CANONICAL_ENVIRONMENT_MATCH = true|false
FULL_CORPUS_AUTHOR_PROJECTION = PASS|FAIL
```

A final PASS requires:

```text
full regression suite PASS in canonical environment
REAL_DATABASE_QUERY PASS
ASGI_IN_PROCESS PASS in canonical environment
UVICORN_LOCALHOST_HTTP PASS
full-corpus source-author projection mismatch count = 0
manual browser semantic smoke PASS
no source/Zotero data modified
```

The optional identity precision audit does not determine Phase 5 PASS, but its findings must be surfaced if performed.
