# Phase 5 Final Validation and Closeout Contract

## Purpose

This is the authoritative final validation contract after the Phase 5 HTTP-harness fixes, local micromamba isolation, warning cleanup, and identity-review query optimization.

A report may state `PHASE_5_STATUS = PASS` **only when every mandatory item below was actually executed and passed**. Automated HTTP 200 checks are not a substitute for the mandatory real-browser semantic check.

## Fixed baseline and changes under test

Previous real-database baseline (`20260817-110214-test-report`):

```text
papers = 2513
source author mentions = 12207
accepted author mentions = 10448
unresolved author mentions = 1759
full-corpus projection mismatches = 0
reachable PDF rows = 2161
stale PDF rows = 0
Uvicorn /api/reviews/identity?limit=5 = 447.136 ms
ASGI    /api/reviews/identity?limit=5 = 451.042 ms
```

The current code changes specifically target:

1. identity-review N+1 query behavior — now one bounded SQL query with SQL-side ranking and `LIMIT`;
2. unclosed SQLAlchemy engines in migration tests;
3. invalid string escape in PDF DOI cleanup;
4. Python compatibility/deprecation warnings when applicable;
5. strict report completeness so an omitted browser test cannot be mislabeled PASS.

The identity-review optimization must preserve the established ranking semantics:

```text
UNRESOLVED_CORRESPONDING_AUTHOR role priority = 100
FIRST-author creator mention role priority = 90
stored priority may override either when larger
final ordering = effective_priority DESC, review_item_id ASC
```

## Environment contract

All local authoritative work must use:

```text
environment manager = micromamba
environment name = Paperazzi
Python = 3.13
constraints = constraints/phase5-test.txt
```

Do not install, uninstall, upgrade, or downgrade packages in Anaconda base or any unrelated environment.

Before any authoritative test, the following must pass:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
micromamba run -n Paperazzi python -m pip check
```

If either fails, stop. Do not continue and do not write a PASS report.

## Test sequence

### 1. Repository and warning regression

Record the exact commit and verify a clean/understood working tree. Run the complete suite with warnings visible:

```bash
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

Mandatory:

- all tests pass;
- `test_identity_review_queue_is_ranked_with_one_select` passes;
- `test_phase5_closeout_report` tests pass;
- no `SyntaxWarning` from `local_evidence/pdf.py`;
- no unclosed SQLite `ResourceWarning` from the migration tests;
- record every remaining project-originated warning, even if non-blocking.

Do not hide warnings with warning filters.

### 2. Full real-database validation

Use the existing real Paperazzi DB. Do not create an empty replacement.

```bash
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path <REAL_DB_PATH> --sample-papers 0
```

Mandatory:

```text
REAL_DATABASE_QUERY = PASS
ASGI_IN_PROCESS = PASS
UVICORN_LOCALHOST_HTTP = PASS
product_path_status = PASS
full_corpus_projection_check = true
source_author_projection_mismatch_count = 0
foreign_key_check_rows = 0
```

Record all corpus scale fields, unresolved-author visibility, PDF state, search checks, and timings.

### 3. Identity-review hotspot remeasurement

The previous Uvicorn baseline for `/api/reviews/identity?limit=5` was `447.136 ms`.

After one warm-up request, measure at least five consecutive requests through the real Uvicorn product path. Report every timing, median, minimum, maximum, and the improvement ratio relative to 447.136 ms.

Classify exactly one:

```text
IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED
IDENTITY_REVIEW_PERFORMANCE_CLASS = NO_REGRESSION
IDENTITY_REVIEW_PERFORMANCE_CLASS = REGRESSED
```

`IMPROVED` means the real median is at least 30% lower than the old baseline. `NO_REGRESSION` means it does not meet that improvement threshold but is no slower than 110% of the old baseline. `REGRESSED` means median > 491.85 ms.

A regression blocks closeout. Do not add caching or FTS5 merely to force this number down; return the measurements for analysis.

Also confirm the regression suite proves the query uses one SELECT for the synthetic ranking case.

### 4. Extended real search validation

Use values that actually exist in the corpus. Test all of the following:

- distinctive full/long paper title;
- DOI;
- venue/journal fragment;
- canonical author name;
- non-ASCII author name if one exists;
- punctuation-heavy title or DOI if one exists.

For each case report:

```text
query
expected object ID
found = true/false
elapsed_ms
```

If the corpus truly contains no suitable example, write `NOT_AVAILABLE_IN_CORPUS` with the query used to establish that fact. Do not silently omit the category.

### 5. Real PDF positive and negative paths

Validate both:

1. a real reachable PDF returns HTTP 200 and corresponds to the requested paper;
2. a real paper without an available PDF returns the controlled unavailable response (normally HTTP 404), not HTTP 500 and not another paper's PDF.

Record paper IDs and status codes. Do not commit private filesystem paths unless necessary for a diagnosed path-mapping defect.

### 6. Real browser semantic smoke — mandatory

Start the real product only from the `Paperazzi` environment:

```bash
micromamba run -n Paperazzi paperazzi-web
```

Use an actual browser. Headless ASGI/Uvicorn requests do **not** satisfy this stage.

Manually inspect and record concrete paper/author IDs for:

- home and paper list render;
- search interaction;
- paper detail;
- all source authors displayed in source order;
- at least one unresolved source author visibly retained;
- FIRST role retained on an unresolved first author where available;
- CORRESPONDING displayed only when accepted evidence exists;
- resolved author profile opens;
- publication list and coauthor list render;
- identity-review page renders in ranked order;
- reachable PDF opens;
- unavailable PDF fails in a controlled way.

If a real browser is unavailable, the final status is **INCOMPLETE**, not PASS. Do not substitute the automated route smoke.

### 7. Targeted author-scale performance

Identify:

- the active canonical author with the highest publication count;
- an author with high coauthor degree.

Measure through the service/API:

```text
high-publication author profile elapsed_ms
high-publication author publication count
high-degree coauthor endpoint elapsed_ms
high-degree shared/coauthor count
```

These measurements are diagnostic and do not need an arbitrary hard latency threshold, but pathological latency must be reported.

### 8. Identity precision audit

This remains optional for Phase 5 closeout but strongly recommended before Phase 6 enrichment.

If performed, run the deterministic audit and report `CORRECT / FALSE_MERGE / UNCERTAIN`. Any convincing false merge must include reproducible author/mention/paper IDs and blocks enrichment of that identity until resolved.

If not performed, state exactly:

```text
IDENTITY_PRECISION_AUDIT = NOT_RUN_OPTIONAL
```

## Mandatory final report

Create exactly one tracked report:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-final-closeout-v4/PHASE5_FINAL_VALIDATION_REPORT.md
```

The report must begin with this status block and may not omit a line:

```text
PHASE_5_STATUS = PASS
PAPERAZZI_MICROMAMBA_ENV = PASS
EXISTING_ANACONDA_ENV_MODIFIED = NO
PHASE_5_REAL_DB_SMOKE = PASS
PRODUCT_PATH_STATUS = PASS
ASGI_HARNESS_STATUS = PASS
FULL_CORPUS_AUTHOR_PROJECTION = PASS
BROWSER_SEMANTIC_SMOKE = PASS
EXTENDED_SEARCH_VALIDATION = PASS
REAL_UNAVAILABLE_PDF_VALIDATION = PASS
IDENTITY_REVIEW_PERFORMANCE_RECHECK = PASS
MEANINGFUL_WARNINGS_REVIEWED = PASS
ZOTERO_SOURCE_MODIFIED = NO
IDENTITY_PRECISION_AUDIT = PASS|NOT_RUN_OPTIONAL
IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED|NO_REGRESSION
```

If any mandatory item did not run or failed, do not copy this PASS block. Use `PHASE_5_STATUS = INCOMPLETE` or `PHASE_5_STATUS = FAIL` in the narrative and do not attempt formal closeout.

The Markdown report must contain evidence sections for:

1. commit/branch/working-tree state;
2. micromamba environment proof and `pip check`;
3. full regression result and warning inventory;
4. full-corpus real DB numbers;
5. source-author/unresolved-author semantics;
6. ASGI and Uvicorn route/timing tables;
7. identity-review before/after measurements;
8. all extended search cases;
9. positive and negative real PDF cases;
10. browser semantic checks with concrete IDs;
11. high-publication/high-degree performance;
12. identity precision audit or explicit optional-not-run status;
13. explicit confirmation that Zotero/source data and Anaconda base were not modified.

## Machine gate

Before committing the report, run:

```bash
micromamba run -n Paperazzi python scripts/check_phase5_closeout_report.py <REPORT_PATH>
```

It must print:

```text
PHASE 5 CLOSEOUT REPORT: PASS
```

The checker intentionally rejects a report that carries PASS status lines while also saying that browser validation was not run.

Only after the checker passes should the report be committed and pushed to `main`.
