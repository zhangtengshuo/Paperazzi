# Paperazzi Phase 5 Post-Fix Validation Agent v5

## Mission

Validate the current Paperazzi `main` after the document-role, provenance/retraction, corresponding-author, primary-PDF, pagination, and Python-runtime fixes.

The authoritative specification is:

```text
docs/phase5/PHASE5_POST_FIX_VALIDATION.md
```

Read it fully before running any command. If an older Phase 5 prompt or document conflicts with it, the v5 post-fix document wins.

---

# Runtime contract

Use only:

```text
manager = micromamba
environment = Paperazzi
Python = 3.13
```

Do not test or maintain Python 3.11 compatibility.

Do not install/change packages in Anaconda/base, system Python, or unrelated environments.

Every authoritative Python command must run through:

```text
micromamba run -n Paperazzi ...
```

unless the command itself is `micromamba`.

---

# Safety contract

During validation:

- Zotero `zotero.sqlite` is read-only.
- Zotero storage/PDFs are read-only.
- The live Paperazzi DB is read-only.
- Any provenance/retraction/rebuild write must be performed on a SQLite Backup API copy of the Paperazzi DB.
- Do not apply validated corrections back to the live DB unless the user explicitly asks in a later message.
- Do not fabricate correspondence evidence or document roles merely to satisfy expected results.
- Do not hide unresolved source authors.
- Do not weaken Phase 4 identity thresholds.

At the end you must be able to state truthfully:

```text
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO
```

---

# Known real regression anchors

These are diagnostic anchors, not answers to copy blindly.

## Paper 2468

Previously:

```text
paper_id 2468
SI document was observed as 2324: ct6c00473_si_001.pdf
main article was observed as document 2325
```

The old product path incorrectly opened the SI because PDF selection followed document ordering.

Verify current IDs/content before asserting anything.

Expected semantic behavior after the fix:

```text
SI -> SUPPLEMENTARY
main article -> selected primary PDF
Open local PDF -> main article, not SI
```

## Paper 2467

Previously observed expected corresponding authors from the actual primary PDF:

```text
Rishab Dutta
Marc Illa
```

The old state failed to create accepted corresponding-author roles. Verify the actual PDF front matter yourself before accepting rebuilt evidence.

The parser fix must preserve both emails, including the second address when followed by sentence punctuation. Email local-part mapping may map `marc.illasubina...` to `Marc Illa` only when the paper-author match is unique.

No third author may be marked corresponding without independent source evidence.

---

# Required execution sequence

## Stage 1 — establish environment and code state

Record:

```text
commit SHA
branch
Python version
micromamba version
Paperazzi environment checker result
pip check result
migration head
```

Require Python 3.13.

## Stage 2 — full synthetic/regression suite

Run:

```bash
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

Record exact:

```text
test count
runtime
failures
errors
skips
Paperazzi-originated warnings
```

Do not suppress warnings.

If a test fails, preserve the failure before editing code.

## Stage 3 — create real Paperazzi test copy

Locate the existing real Paperazzi DB used by the previous Phase 5 validation.

Use Python `sqlite3.Connection.backup()` to create:

```text
data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3
```

or an equivalent ignored local path.

Record SHA-256/size of source and copy. Do not mutate the source DB.

Upgrade the copy to Alembic head `0006_document_roles_retractions` and verify `PRAGMA foreign_key_check` returns zero rows.

## Stage 4 — full-corpus validation on the copy

Run `scripts/validate_phase5.py --sample-papers 0` against the copy.

Require:

```text
REAL_DATABASE_QUERY PASS
ASGI_IN_PROCESS PASS
UVICORN_LOCALHOST_HTTP PASS
full-corpus author projection mismatch = 0
foreign-key errors = 0
```

Record fresh corpus counts.

## Stage 5 — paper 2468 primary/SI regression

Use:

```text
scripts/manage_provenance.py inspect-paper
```

against the test copy.

Verify current document IDs, filenames, effective roles and selected primary document.

If the SI does not yet have a persisted role, run `set-document-role` first as a dry run, capture it, then apply only to the test copy with:

```text
role = SUPPLEMENTARY
source = LOCAL_AI
reason_code = CONFIRMED_SUPPORTING_INFORMATION
```

Capture before/after:

```text
raw accepted spans
authorship evidence statuses
reference section/reference statuses
RetractionEvent id
RetractionImpact count
selected primary document id
```

Raw extraction history must remain. Invalid paper-level derivations must stop being current.

Then verify `/api/papers/2468/pdf` resolves to the main article.

## Stage 6 — paper 2467 correspondence regression

Inspect paper 2467 and identify the actual primary document.

Run `scripts/rebuild_document_evidence.py` with no `--apply` first.

Review the real PDF front matter and preview. Require both correspondence emails/candidates to be present and semantically correct before accepting.

Only then apply a `PASS` rebuild to the test copy.

If a previous accepted attempt existed, require:

```text
previous_accepted_attempt_id != null
replacement_retraction_id != null
old attempt retained historically
old current outputs invalidated/superseded
new reviewed attempt current
old and new evidence not simultaneously current
```

Require final corresponding-author set for paper 2467 to contain Rishab Dutta and Marc Illa, with no false-positive third author.

## Stage 7 — multi-PDF sample

Inspect at least 20 real papers with multiple PDF attachments, prioritizing SI/ESI/supplement filenames.

Hard failure if a known supplementary PDF is selected while a reachable non-supplementary article candidate exists.

Do not bulk-write roles merely to obtain a PASS.

## Stage 8 — extended search/PDF negative/performance

Repeat the real search cases from the authoritative document.

Test one reachable primary PDF and one unavailable-PDF 404 case.

Measure `/api/reviews/identity?limit=5` after one warm-up using at least five real Uvicorn requests. Record all raw times and median/min/max.

Ensure the single-SELECT identity-review regression test passes. Do not add caching/FTS5 just for timing.

## Stage 9 — pagination API

Validate first, second and final pages for Papers and Authors using `limit=100` and offsets.

Require stable totals and different page contents.

## Stage 10 — launch browser validation on the test copy

Start Paperazzi with `PAPERAZZI_DB` pointing to the **test copy**.

Give the user the localhost URL and the exact checklist from `docs/phase5/PHASE5_POST_FIX_VALIDATION.md`.

You may not set:

```text
USER_BROWSER_CONFIRMATION = PASS
```

until the user explicitly confirms the browser results.

If all automated/local-AI stages pass but the user has not yet responded, report:

```text
PHASE_5_POST_FIX_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
USER_BROWSER_CONFIRMATION = PENDING
```

Do not convert this to PASS yourself.

---

# Report path

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-post-fix-v5/PHASE5_POST_FIX_VALIDATION_REPORT.md
```

The report must include the complete required status block from the authoritative v5 document and evidence for every field.

At minimum include:

- commit and migration head;
- Python 3.13 environment proof;
- test count/runtime/warnings;
- source/test-copy DB fingerprints;
- full-corpus counts/projection/FK;
- paper 2468 before/after role/retraction evidence;
- paper 2467 rebuild and cross-run replacement evidence;
- final corresponding-author names for paper 2467;
- multi-PDF sample table/count;
- extended search results;
- PDF positive/negative IDs;
- identity-review raw timing series and median;
- pagination API evidence;
- browser checklist status and the user's explicit confirmation when received;
- confirmation Zotero, live Paperazzi DB, and Anaconda/base were not modified.

If any mandatory stage fails, use `FAIL` or `PENDING`; never omit the field and never claim a global PASS.

---

# Defect handling

If you find a defect:

1. preserve pre-fix evidence;
2. identify the responsible layer;
3. make the smallest code fix;
4. add/strengthen a regression test;
5. rerun the full Python 3.13 suite;
6. recreate or reset the test-copy DB when mutation history could contaminate the result;
7. rerun every affected real-data stage;
8. separate pre-fix and post-fix evidence in the report.

Do not silently repair database rows with ad hoc SQL when a supported provenance/retraction operation should be used.
