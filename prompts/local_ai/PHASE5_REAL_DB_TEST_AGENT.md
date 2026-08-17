# Paperazzi Phase 5 — Local AI Real-Database Validation Agent v3

## Mission

You are the local validation agent for Paperazzi Phase 5. Validate the current `main` against the user's real Paperazzi database and local Zotero/PDF filesystem, preserve evidence on failure, and return enough structured information for remote analysis.

Do not manufacture data. Do not weaken Phase 4 identity safety. Do not modify Zotero source data.

---

# NON-NEGOTIABLE LOCAL ENVIRONMENT CONTRACT

Paperazzi local development and real-data validation now **must use a dedicated micromamba environment named exactly `Paperazzi`**.

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
dependency baseline = constraints/phase5-test.txt
```

## Absolute prohibition

Do **not** install, upgrade, downgrade, uninstall, or otherwise change packages in:

```text
Anaconda base
Miniconda base
any user's existing Conda environment
system Python
any unrelated virtual environment
```

The user's pre-existing Anaconda environment is diagnostic context only. It is not a Paperazzi dependency target.

Do not run a command such as the following against the currently active arbitrary Python environment:

```text
python -m pip install -c constraints/phase5-test.txt ...
```

unless you have first established that this Python belongs to the dedicated `Paperazzi` micromamba environment.

## Required creation procedure

From the repository root, create the dedicated environment with micromamba:

```bash
micromamba create -y -f environment/Paperazzi.yml
micromamba run -n Paperazzi python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The third command must report:

```json
"pass": true
```

before authoritative testing begins.

If an environment named `Paperazzi` already exists, inspect it first. Repair/update only that environment. Do not delete or modify unrelated environments.

For all subsequent local commands, prefer explicit execution through:

```text
micromamba run -n Paperazzi ...
```

rather than relying on whichever environment happens to be activated in the shell.

GitHub Actions is an exception because it is already an ephemeral isolated environment. Do not redesign CI merely to force micromamba there.

---

## Read first

```text
README.md
docs/phase4/PHASE4_CLOSEOUT.md
docs/phase5/README.md
docs/phase5/PHASE5_TESTING.md
environment/Paperazzi.yml
constraints/phase5-test.txt
scripts/check_paperazzi_environment.py
scripts/validate_phase5.py
src/paperazzi/environment_contract.py
src/paperazzi/web/validation.py
src/paperazzi/web/queries.py
src/paperazzi/web/api.py
```

Expected state:

```text
PHASE_4_STATUS = PASS
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```

Work on `main`. Do not create a branch or PR unless explicitly requested.

---

# Source/data rules

- Zotero `zotero.sqlite`, `storage/`, and PDFs are read-only.
- Paperazzi source-author truth starts from `paper_creator_mentions`.
- Every Zotero paper author remains visible even when canonical identity is unresolved.
- `FIRST` and `CORRESPONDING` are additive roles, not author filters.
- Do not force-resolve identities merely to increase coverage.
- Do not create fake `ACCEPTED` references or correspondence evidence.
- Missing/unreachable PDFs may be valid states.
- `PDF_AVAILABLE` pointing to a missing file is stale/inconsistent state to report.
- Validation must not mutate semantic tables.

---

# Stage 0 — Capture native environment WITHOUT modifying it

Before creating/updating `Paperazzi`, capture only diagnostic facts about the currently active environment:

```text
Python version
Python executable
CONDA_DEFAULT_ENV if present
micromamba version
whether an environment named Paperazzi already exists
FastAPI/Starlette/HTTPX/AnyIO versions if already installed
```

Do not install anything into this native environment. Do not try to "repair" it.

Do not repeat the old Starlette synchronous `TestClient` experiment unless specifically requested. The old failure has already been isolated to the blocking-portal test path and is no longer authoritative.

In the tracked report, avoid unnecessary full environment paths. Never record proxy URLs, credentials, cookies, tokens, API keys, or secrets.

---

# Stage 1 — Establish and prove the Paperazzi environment

Create or update only the dedicated micromamba environment `Paperazzi`, then run:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
micromamba run -n Paperazzi python -m pip check
```

Required:

```text
environment name = Paperazzi
Python = 3.13
constraint match = true
pip check = PASS
```

If the checker fails, stop authoritative testing and report exactly:

```text
active environment name
actual Python version
which constrained packages differ
expected version
installed version
```

Repair only `Paperazzi`, rerun the checker, then continue.

---

# Stage 2 — Full regression suite

Run only through the dedicated environment:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
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

The suite must include the environment-contract tests, ASGITransport HTTP test, real Uvicorn localhost smoke, source-author completeness, author profile/search, and failure-isolated validation infrastructure.

If a regression fails, preserve the exact test and traceback before editing code.

---

# Stage 3 — Real DB smoke

Locate the actual existing Paperazzi database. Do not create an empty replacement.

Run:

```bash
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path <REAL_DB_PATH>
```

Preserve:

```text
data/phase5-validation/phase5_report.json
```

even if the command exits nonzero.

Required stages:

```text
REAL_DATABASE_QUERY
ASGI_IN_PROCESS
UVICORN_LOCALHOST_HTTP
```

Return status and elapsed time for each.

---

# Stage 4 — Full-corpus author projection

If the smoke passes, run:

```bash
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path <REAL_DB_PATH> --sample-papers 0
```

Required:

```text
full_corpus_projection_check = true
source_author_projection_mismatch_count = 0
```

If any mismatch exists, preserve the paper IDs and compare source `paper_creator_mentions(author)` with `PaperazziQueryService.get_paper()["authors"]`.

Never hide unresolved source authors to make this pass.

---

# Stage 5 — Information you MUST return for remote analysis

Do not report only PASS/FAIL. Collect the following.

## A. Environment facts

```text
micromamba version
Paperazzi environment exists = true/false
environment checker PASS/FAIL
Python version inside Paperazzi
pip check PASS/FAIL
constraint mismatch list if any
```

Also state explicitly:

```text
Existing Anaconda/base environment modified = NO
```

If this cannot be stated truthfully, stop and report what changed.

## B. Real database scale

```text
active papers
active canonical authors
source author mentions
accepted author mentions
unresolved author mentions
full-corpus papers checked
source-author projection mismatch count
unresolved source authors visible in paper details
foreign-key check rows
```

## C. HTTP separation

For both `ASGI_IN_PROCESS` and `UVICORN_LOCALHOST_HTTP`, return status and timing for:

```text
/
/health
/api/papers
/api/authors
/api/search
/api/reviews/identity
one real paper detail
one real author detail
author publications
coauthors
one PDF route when reachable
```

If Uvicorn fails, include `server_log_tail`.

## D. Search using real corpus values

Test and report exact queries for:

```text
one distinctive paper title
one DOI
one journal/venue fragment
one canonical author name
one non-ASCII author name if available
one punctuation-heavy title/DOI if available
```

For each:

```text
query
expected record
found true/false
elapsed_ms
```

Do not invent unavailable corpus cases.

## E. PDF state

```text
PDF_AVAILABLE rows
reachable PDF rows
stale PDF_AVAILABLE rows
up to 20 stale example paper IDs
successful PDF HTTP paper ID(s)
controlled unavailable-PDF paper ID
```

Prefer paper IDs over full local paths in the tracked report.

## F. Performance

Return at least:

```text
list_papers(20) elapsed_ms
list_authors(20) elapsed_ms
paper detail mean/p50/p95/max
ASGI route timings
Uvicorn route timings
common author search timing
distinctive title search timing
high-publication author profile timing
high-degree coauthor-list timing
```

Do not add FTS5/caching without measured evidence.

## G. Warnings that may matter later

Report meaningful warnings separately even if tests pass, for example:

```text
ResourceWarning / leaked SQLite connection
DeprecationWarning affecting Python 3.14+
syntax warnings
unexpected package/module origin
stale PDF concentration
path-mapping anomalies
very slow query outliers
```

Do not treat harmless runner/cache warnings as product failures, but preserve warnings that imply future code maintenance.

---

# Stage 6 — Manual semantic/browser checks

Inspect several real papers with unresolved authors and confirm:

```text
source name visible
author order preserved
identity_status=UNRESOLVED when appropriate
FIRST survives unresolved identity
CORRESPONDING only appears with accepted semantic evidence
```

Inspect representative canonical authors:

```text
single-paper author
multi-paper author
first author
corresponding author if available
high-publication author
high-degree coauthor
```

Then run the product from the dedicated environment:

```bash
micromamba run -n Paperazzi paperazzi-web
```

Verify in a browser:

```text
home
paper list
search
paper detail
all source authors
author profile
publications/coauthors
identity review
reachable PDF
controlled unavailable PDF
```

Do not fail for visual polish alone.

---

# Stage 7 — Identity precision audit

After Phase 5 smoke is stable, strongly prefer running:

```bash
micromamba run -n Paperazzi python scripts/export_identity_precision_audit.py
```

Review especially:

```text
SAME_NORMALIZED_NAME_MULTIPLE_IDENTITIES
THRESHOLD_EDGE
FIRST_AUTHOR
HIGH_PUBLICATION_DEGREE
East-Asian/common names when represented
```

Return counts:

```text
CORRECT
FALSE_MERGE
UNCERTAIN
```

A convincing false merge is a Phase 4 identity-quality defect. Preserve reproducible evidence rather than changing thresholds from a tiny sample.

---

# Failure handling

If a mandatory stage fails:

1. Preserve the exact failure before fixing anything.
2. Preserve `phase5_report.json` if produced.
3. Classify the responsible layer: environment, query/DB, ASGI, Uvicorn, browser, filesystem/PDF.
4. Never repair by changing the user's Anaconda/base environment.
5. If code behavior is wrong, add a regression test first.
6. Fix only the responsible layer.
7. Rerun environment checker, full regression suite, 200-paper smoke, then full-corpus projection.

---

# Required tracked report

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-real-db-v3/PHASE5_REAL_DB_TEST_RESULTS.md
```

It must contain:

1. tested branch/commit;
2. micromamba/Paperazzi environment proof;
3. explicit confirmation that existing Anaconda/base was not modified;
4. regression-suite result;
5. real DB scale/full-corpus projection;
6. ASGI and Uvicorn results/timings;
7. real search cases;
8. PDF state;
9. manual semantic/browser checks;
10. measured performance;
11. meaningful warnings;
12. defects and fixes;
13. identity precision audit if performed;
14. explicit information requested above for remote analysis.

Do not commit machine-local secrets or unnecessary full filesystem paths.

---

# Final status vocabulary

Report:

```text
PAPERAZZI_MICROMAMBA_ENV = PASS|FAIL
EXISTING_ANACONDA_ENV_MODIFIED = NO|YES
PHASE_5_REAL_DB_SMOKE = PASS|FAIL
PRODUCT_PATH_STATUS = PASS|FAIL
ASGI_HARNESS_STATUS = PASS|FAIL|ERROR
FULL_CORPUS_AUTHOR_PROJECTION = PASS|FAIL
```

A final Phase 5 PASS requires:

```text
Paperazzi micromamba environment contract PASS
existing Anaconda/base environment untouched
full regression suite PASS
REAL_DATABASE_QUERY PASS
ASGI_IN_PROCESS PASS
UVICORN_LOCALHOST_HTTP PASS
full-corpus source-author projection mismatch count = 0
manual browser semantic smoke PASS
no Zotero/source data modified
```
