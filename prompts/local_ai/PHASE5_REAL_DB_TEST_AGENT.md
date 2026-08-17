# Paperazzi Phase 5 — Local AI Real-Database Test Agent

## Role

You are the **local validation agent** for Paperazzi Phase 5. You have access to the user's real local Paperazzi database and Zotero-backed filesystem paths that GitHub Actions cannot access.

Your job is to validate the already-implemented Phase 5 query/service layer, FastAPI backend, minimal browser UI, search behavior, and local-PDF access **against the real database**.

This is a validation task first. Do not redesign Phase 5, do not broaden scope, and do not manufacture data merely to make a test pass.

---

## Repository and source-of-truth rules

Repository:

```text
zhangtengshuo/Paperazzi
```

Work from the current `main` branch. For this validation run, do not create a feature/agent/PR branch.

The source-of-truth hierarchy remains:

```text
Zotero sqlite + storage          read-only source
Paperazzi SQLite                 owned semantic/persistence state
paper_creator_mentions           complete source author record
canonical authors/authorships    conservative semantic projection
```

Critical invariant:

> Every Zotero paper author must remain visible in Paperazzi even when canonical identity resolution is unresolved.

Do not treat an unresolved canonical identity as missing source-author data.

Do not write to `zotero.sqlite`, Zotero `storage/`, or PDF files.

---

## Tested baseline

Before beginning, read:

```text
docs/phase4/PHASE4_CLOSEOUT.md
docs/phase5/README.md
scripts/validate_phase5.py
src/paperazzi/web/queries.py
src/paperazzi/web/api.py
```

Expected phase state:

```text
PHASE_4_STATUS = PASS
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```

GitHub CI already covers synthetic/regression behavior. This local run exists specifically to test behavior that requires the user's real Paperazzi database and real local PDF paths.

---

# Test policy

## Mandatory principles

1. **Test before fixing.** Record the failure and isolate the violated invariant before editing source code.
2. **Do not weaken a test to make it green.**
3. **Do not hide unresolved authors.**
4. **Do not merge author identities merely to improve coverage.**
5. **Do not create fake ACCEPTED references or fake corresponding-author evidence.**
6. **Do not treat unavailable PDFs as a database error.** Missing files are valid data states; incorrect `PDF_AVAILABLE` claims are errors.
7. **Do not write semantic state during the Phase 5 smoke test.** The validation itself is read-only with respect to Paperazzi semantic tables.
8. If a real defect is found and repaired, add/extend a regression test that reproduces it before declaring the defect closed.

---

# Stage 0 — Environment and repository sanity

Confirm all of the following before running the real-database test:

```text
current branch = main
working tree understood; do not overwrite unrelated local work
current main contains Phase 5 web/query implementation
Python environment can import paperazzi, FastAPI, SQLAlchemy
```

Install the web/PDF extras if needed:

```bash
python -m pip install -e ".[pdf,web]"
```

The default real-validation DB path expected by the current repository is:

```text
data/phase4-validation/paperazzi.sqlite3
```

If that file does not exist, locate the actual existing Paperazzi validation/production DB. Do **not** create an empty replacement and call that a test.

Record the exact DB path used in the final report.

---

# Stage 1 — Full regression suite

Run the complete test suite on the exact checked-out commit:

```bash
python -m unittest discover -s tests -v
```

Expected baseline at the time this contract was written:

```text
99 tests
0 failures
```

A larger test count is fine if new tests were added later. Any real failure is a blocker until understood.

Record:

```text
commit SHA
test count
failures
errors
skips
```

---

# Stage 2 — Real-database automated smoke validation

Run:

```bash
python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3
```

If the real DB is elsewhere, pass that exact path explicitly.

The validator writes:

```text
data/phase5-validation/phase5_report.json
```

This runtime JSON is local validation state and should normally remain outside Git-tracked source unless repository policy explicitly changes.

## Required PASS conditions

The automated validator must report:

```text
status = PASS
paper_count > 0
active_canonical_authors > 0
source_author_projection_mismatches = []
search_smoke_passed = true
HTTP / = 200
HTTP /health = 200
HTTP /api/papers = 200
HTTP /api/authors = 200
HTTP /api/search = 200
```

### Most important invariant

For every sampled paper:

```text
count(paper_creator_mentions WHERE creator_type='author')
==
count(authors returned by PaperazziQueryService.get_paper())
```

If this fails for even one sampled paper, Phase 5 real-DB validation is **FAIL**.

Do not "repair" the mismatch by filtering source mentions or by force-resolving identities.

---

# Stage 3 — Increase source-author coverage check

The default validator samples 200 papers. If Stage 2 passes, run a full-corpus author-projection check by setting `--sample-papers` comfortably above the actual active paper count, for example:

```bash
python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3 --sample-papers 100000
```

This is intended to verify the complete real corpus, not just a sample.

Required:

```text
source_author_projection_mismatches = []
```

Record the actual number of papers checked.

If runtime is unexpectedly excessive, investigate query complexity rather than silently falling back to a tiny sample.

---

# Stage 4 — Unresolved-author visibility audit

The real corpus is known to contain unresolved source-author mentions. Phase 5 must expose them rather than dropping them.

Use the validator output and direct query/API inspection to verify at least several papers containing unresolved authors.

For each inspected paper confirm:

```text
source display name is present
identity_status = UNRESOLVED
canonical author ID may be null
paper author order is preserved
FIRST role is still represented when the unresolved mention is the first source author
```

This check is a **semantic requirement**, not cosmetic UI behavior.

If unresolved authors disappear from paper detail, stop and report FAIL.

---

# Stage 5 — Author profile correctness

Inspect a representative set of resolved canonical authors. Include at minimum:

```text
an author with one paper
an author with multiple papers
an author appearing as first author on at least one paper
an author with multiple coauthors
```

For each author compare service/API output against direct database facts.

Verify:

```text
preferred name / known variants are coherent
publication count is correct
paper roles are paper-specific
first-author flag is correct
corresponding-author flag is only shown when accepted semantic state exists
coauthor list does not include the author themself
coauthor counts are plausible and derive from active authorships
```

Do not infer corresponding-author status from author order, email guesswork, or candidate PDF evidence.

---

# Stage 6 — Search validation

Test searches drawn from the actual corpus, not synthetic words only.

Include:

```text
exact paper-title fragment
DOI fragment or full DOI
venue/journal fragment
canonical author preferred-name fragment
known author name variant when available
```

Expected behavior:

- relevant records are returned;
- search does not crash on punctuation or non-ASCII names;
- an unresolved source author is not required to appear in canonical-author search unless/until a search surface explicitly supports source mentions;
- no result should imply identity certainty that the database does not contain.

Record any query that is unexpectedly slow on the real corpus. Do not add FTS5 solely because it was planned; add it only if measured real-database behavior justifies it.

---

# Stage 7 — Local PDF validation

Paperazzi must open local PDFs without requiring Zotero Desktop to be running.

For a representative set of papers with persisted:

```text
availability_status = PDF_AVAILABLE
present_in_last_scan = true
```

verify:

```text
PaperazziQueryService.get_pdf_path(paper_id) returns an existing file
GET /api/papers/{paper_id}/pdf returns success for a reachable PDF
content served is the persisted PDF for that paper
client cannot supply an arbitrary filesystem path
```

Also inspect at least one paper without a reachable PDF and confirm the API reports a controlled not-found/unavailable condition rather than crashing or exposing another file.

Important distinction:

```text
FILE_UNAVAILABLE / PDF_RECORD_ONLY / UNRESOLVED_PATH = valid data state
PDF_AVAILABLE pointing to a nonexistent file             = stale/inconsistent state to report
```

Do not edit or copy PDF files to make this test pass.

---

# Stage 8 — HTTP and minimal browser UI smoke test

Start the local server against the exact tested DB:

```bash
PAPERAZZI_DB=data/phase4-validation/paperazzi.sqlite3 paperazzi-web
```

Use the actual DB path if different.

Default address:

```text
http://127.0.0.1:8765
```

Verify the browser workflow:

```text
home page opens
→ paper list loads
→ search returns real records
→ paper detail opens
→ ALL source authors are shown
→ resolved author link opens profile
→ author publications/coauthors load
→ PDF action works when local PDF exists
→ identity-review view loads without mutating data
```

The first UI is intentionally minimal. Do not fail it merely for visual polish. Fail it for incorrect data, missing source authors, broken navigation, unsafe PDF handling, or unusable latency.

---

# Stage 9 — Real-data performance observations

Measure enough to answer whether the current SQLAlchemy/SQLite search implementation is acceptable for the current real corpus.

At minimum observe:

```text
paper list initial load
common author search
paper-title search
author profile with many publications/coauthors
```

Do not introduce FTS5 or caching speculatively. Report measured slow cases first.

Suggested interpretation:

```text
interactive and comfortably sub-second / low single-digit second → keep current implementation
repeatedly slow enough to impair normal use                → profile query, then propose targeted index/FTS5 work
```

Exact performance thresholds are not a correctness gate at this phase; pathological behavior is.

---

# Stage 10 — Optional identity precision audit

This is quality control and is **not** a Phase 5 PASS gate.

Generate the deterministic stratified sample with:

```bash
python scripts/export_identity_precision_audit.py
```

Review selected auto-accepted identity links, especially:

```text
SAME_NORMALIZED_NAME_MULTIPLE_IDENTITIES
THRESHOLD_EDGE
FIRST_AUTHOR
HIGH_PUBLICATION_DEGREE
```

For each reviewed row use only:

```text
CORRECT
FALSE_MERGE
UNCERTAIN
```

Do not change automatic thresholds merely because unresolved coverage exists.

If a convincing false merge is found, report it as a Phase 4 identity-quality defect and preserve all evidence needed to reproduce it.

---

# Failure handling

If any mandatory stage fails:

1. Preserve the exact failing paper/author IDs and observed output.
2. Identify whether the defect is in:
   - persistence/source data;
   - query/service projection;
   - HTTP adapter;
   - UI presentation;
   - stale local filesystem state.
3. Add a minimal regression test if the problem is code behavior.
4. Fix only the responsible layer.
5. Run the full regression suite again.
6. Rerun the real-database validator.

Never solve a Phase 5 display/query problem by weakening Phase 4 identity safety.

---

# Required tracked report

After validation, create a tracked Markdown report at:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-real-db/PHASE5_REAL_DB_TEST_RESULTS.md
```

The report must contain:

## 1. Tested repository state

```text
branch
commit SHA
Python version
Paperazzi DB path
```

## 2. Regression suite

```text
tests passed / failed / skipped
```

## 3. Real database summary

```text
active papers
active canonical authors
sampled/full-corpus papers checked
source-author projection mismatch count
unresolved source authors observed
PDF_AVAILABLE rows
reachable PDFs checked
```

## 4. API/UI results

```text
home
health
papers
authors
search
paper detail
author detail
coauthors
PDF route
identity review
```

## 5. Search observations

List actual real-corpus queries used and whether the result was correct.

## 6. Manual semantic spot checks

List paper IDs / author IDs checked and concise findings. Do not include sensitive filesystem data beyond what is needed for reproducibility.

## 7. Performance observations

Record slow paths if any.

## 8. Defects found and fixes

If none:

```text
NONE
```

If fixes were made, identify regression tests and commits.

## 9. Final status

Use exactly one of:

```text
PHASE_5_REAL_DB_SMOKE = PASS
PHASE_5_REAL_DB_SMOKE = FAIL
```

A PASS requires all mandatory correctness stages above to pass. Optional identity precision audit does not determine this status.

---

# Completion criterion

The Phase 5 MVP can be considered validated on the real library when all of the following are true:

```text
full regression suite passes
real DB opens successfully
all checked source authors remain visible
full-corpus author projection has zero mismatches
resolved author profiles are semantically consistent
real-corpus search works
HTTP routes work
local PDF routing works safely for reachable PDFs
missing/unreachable PDFs are handled as valid controlled states
no source/Zotero data is modified
```

At that point report:

```text
PHASE_5_REAL_DB_SMOKE = PASS
NEXT = Phase 5 usability/performance refinement, then Phase 6 priority-author enrichment
```
