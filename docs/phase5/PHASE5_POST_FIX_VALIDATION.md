# Paperazzi Phase 5 Post-Fix Validation v5

## Status and authority

This document is the authoritative validation procedure for the document-role, provenance/retraction, corresponding-author, primary-PDF, pagination, and Python-runtime fixes introduced after the first Phase 5 browser test.

Where this document conflicts with older Phase 5 validation documents or prompts, **this document wins**.

The validation is intentionally split between:

1. **Local AI automated/real-data-copy validation**; and
2. **user browser semantic confirmation**.

The local AI must not claim the human/browser items passed on the user's behalf.

---

# 1. Fixed runtime contract

Paperazzi has one supported Python runtime for this phase:

```text
Python = 3.13
```

The authoritative local environment is:

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
constraints         = constraints/phase5-test.txt
```

Do not maintain or test a Python 3.11 compatibility path. Do not modify Anaconda/base, system Python, or unrelated environments.

Required environment commands:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
micromamba run -n Paperazzi python -m pip check
```

Both must pass before authoritative validation begins.

---

# 2. Safety contract

The following are non-negotiable:

- Zotero `zotero.sqlite` is read-only.
- Zotero `storage/` and all source PDFs are read-only.
- No test may edit or rename a Zotero PDF.
- No test may write Zotero metadata.
- Mutating provenance/retraction tests must run first on a **transactionally copied Paperazzi database**, not the live Paperazzi database.
- A test-copy failure must never be repaired by editing Zotero.
- The live Paperazzi database must remain unchanged during validation unless the user later gives an explicit deployment instruction.
- Retraction is invalidation plus projection recomputation; it is not physical deletion of extraction history.

Expected final safety lines:

```text
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO
```

---

# 3. Code/schema expectations

Before real-data testing, record:

```text
git commit SHA
branch
Python version
migration head
```

Expected migration head:

```text
0006_document_roles_retractions
```

The synthetic/regression suite must include tests for:

- primary article preferred over SI;
- persisted document role overriding filename heuristic;
- SI reclassification retracting downstream paper-level evidence while preserving raw extraction spans;
- independent valid evidence preserving an otherwise-supported projection;
- bad extraction-attempt retraction;
- two corresponding authors mapped from email local parts;
- sentence-final punctuation not hiding the second email;
- SI correspondence evidence not creating paper-level corresponding roles;
- source-author projection integrity;
- identity-review single-SELECT regression;
- ASGI and real Uvicorn smoke.

Run:

```bash
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

Record exact test count, runtime, failures/errors/skips, and all Paperazzi-originated warnings. Do not suppress warnings to make the run appear clean.

---

# 4. Create a real-DB validation copy

Locate the actual Paperazzi database used by the previous real-data Phase 5 run. Do not create an empty replacement.

Create a **SQLite Backup API** copy in an ignored/local validation directory. The source Paperazzi DB may be open; do not use a naïve byte copy while it is active.

Example procedure, substituting the real paths:

```bash
micromamba run -n Paperazzi python - <<'PY'
import sqlite3
from pathlib import Path
src = Path("<REAL_PAPERAZZI_DB>")
dst = Path("data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3")
dst.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
    source.backup(target)
print(dst)
PY
```

Record a source-file size and SHA-256 before testing. The live DB must not change during copy validation.

Upgrade **the copy only**:

```bash
PAPERAZZI_DB_URL=sqlite:///data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
micromamba run -n Paperazzi python -m alembic upgrade head
```

Verify migration head and:

```text
PRAGMA foreign_key_check -> 0 rows
```

---

# 5. Baseline full-corpus validation on the copy

Run:

```bash
micromamba run -n Paperazzi python scripts/validate_phase5.py \
  --db-path data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
  --sample-papers 0
```

Required:

```text
REAL_DATABASE_QUERY = PASS
ASGI_IN_PROCESS = PASS
UVICORN_LOCALHOST_HTTP = PASS
full_corpus_projection_check = true
source_author_projection_mismatch_count = 0
foreign_key_check_errors = 0
```

Record current corpus counts rather than blindly copying previous values. Previous reference values were approximately:

```text
papers                  = 2513
canonical authors       = 7398
source author mentions  = 12207
accepted author mentions= 10448
unresolved mentions     = 1759
reachable PDFs          = 2161
```

Differences are allowed only when explainable by a newer Zotero/Paperazzi scan.

---

# 6. Real regression A — paper 2468 primary article vs SI

Known regression paper:

```text
paper_id = 2468
```

Previous browser failure:

```text
document 2324 = ct6c00473_si_001.pdf = Supporting Information
document 2325 = main article PDF
old /api/papers/2468/pdf behavior selected the SI
```

Do not assume IDs without checking the current copy. Inspect:

```bash
micromamba run -n Paperazzi python scripts/manage_provenance.py \
  --db-path data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
  inspect-paper --paper-id 2468
```

Required before any write:

- the SI document is classified `SUPPLEMENTARY` by heuristic or persisted role;
- the article is `PRIMARY_ARTICLE` or an explicitly confirmed primary candidate;
- `selected_primary_document_id` is the main article, not the SI.

If the SI has no persisted role yet, first run `set-document-role` **without `--apply`** and capture the dry-run result. Then, on the test copy only, persist:

```text
role        = SUPPLEMENTARY
source      = LOCAL_AI
reason_code = CONFIRMED_SUPPORTING_INFORMATION
```

with explicit `--apply`.

After apply, require:

- one `RetractionEvent` if this classification invalidated previously usable paper-level derivations;
- every changed downstream row has a `RetractionImpact`;
- raw `DocumentEvidenceSpan` history still exists;
- live `AuthorshipEvidence` from the SI is no longer accepted/candidate paper-level truth;
- affected corresponding-author projections are recomputed from remaining valid evidence;
- SI reference outputs that were live paper-level derivations are no longer current;
- the main article remains the PDF returned by the paper PDF route.

Record before/after counts for the SI document:

```text
accepted raw spans
authorship evidence by status
reference sections by status
references by status
retraction event id
retraction impact count
selected primary document id
```

A zero-impact event is acceptable only if the SI had no live downstream derivations to retract; explain this explicitly.

---

# 7. Real regression B — paper 2467 corresponding authors

Known regression paper:

```text
paper_id = 2467
expected corresponding authors:
  - Rishab Dutta
  - Marc Illa
```

The source PDF previously contained correspondence emails equivalent to:

```text
rishab.dutta@...
marc.illasubina@...
```

The previous parser/database state failed to establish the two corresponding-author roles.

First inspect paper 2467 and identify its selected primary document. Do not use any supplementary document as a paper-level authorship source.

Run the rebuild tool **without `--apply`** on the primary document:

```bash
micromamba run -n Paperazzi python scripts/rebuild_document_evidence.py \
  --db-path data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
  --document-id <PRIMARY_DOCUMENT_ID>
```

The preview must show:

- no extraction error;
- document role is not `SUPPLEMENTARY`;
- both correspondence emails are visible after normalization/extraction;
- correspondence candidate text is consistent with the source PDF;
- `previous_accepted_attempt_id` is reported when a current accepted run exists.

The local AI must inspect the actual PDF text before assigning `PASS`. It must not accept a correspondence result solely because the expected answer is known from this document.

If the preview matches the actual PDF, apply on the **test copy only**:

```bash
micromamba run -n Paperazzi python scripts/rebuild_document_evidence.py \
  --db-path data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
  --document-id <PRIMARY_DOCUMENT_ID> \
  --review-decision PASS \
  --reviewer LOCAL_AI \
  --quality-notes "Verified against paper 2467 primary PDF front matter" \
  --apply
```

For an accepted rebuild with a previous accepted attempt, require:

- old accepted attempt is retracted in the same transaction;
- output contains `replacement_retraction_id`;
- old attempt history is retained;
- old raw/derived current outputs are superseded/invalidated according to provenance policy;
- new reviewed attempt becomes the current accepted extraction;
- old and new attempts are not simultaneously current evidence;
- downstream corresponding-author projection is recalculated from the new accepted evidence.

Required paper-level result:

```text
Rishab Dutta -> CORRESPONDING
Marc Illa    -> CORRESPONDING
all other authors on paper 2467 -> not CORRESPONDING unless independently proven by the PDF
```

A false-positive third corresponding author is a hard failure.

Record:

```text
primary document id
old current run id
old accepted attempt id
new run id
new accepted attempt id
replacement retraction id
corresponding AuthorshipEvidence rows and status
final corresponding-author names
unresolved correspondence review rows, if any
```

---

# 8. Multi-PDF/SI sanity sample

To ensure paper 2468 is not a one-off patch, select at least 20 real papers with multiple PDF attachments, prioritizing filenames containing SI/ESI/supplement markers.

For each sampled paper record:

```text
paper_id
document filenames/effective roles
selected primary document
whether selected primary looks like SI
```

Hard failure:

```text
known SUPPLEMENTARY selected while a reachable non-supplementary article candidate exists
```

Do not persist bulk document roles merely to make this sample pass. Persist a role only when evidence supports it and only on the test copy during validation.

---

# 9. Search, PDF negative path, and identity-review performance

Repeat the existing extended search checks using real corpus values:

- distinctive title;
- DOI;
- venue/journal fragment;
- canonical author;
- non-ASCII author when available;
- punctuation-heavy title/DOI when available.

For each, record query, expected object, found/not found, and elapsed time.

Repeat both PDF cases:

- reachable primary PDF -> HTTP 200 and correct paper;
- unavailable PDF -> controlled 404, never another paper's PDF and never HTTP 500.

Recheck:

```text
/api/reviews/identity?limit=5
```

Use one warm-up and at least five consecutive real-Uvicorn timings. Record every timing, median, min, and max.

The earlier optimized reference median was approximately:

```text
3.868 ms
```

Do not add caching or FTS5 merely to chase this number. Structural regression test `test_identity_review_queue_is_ranked_with_one_select` must pass. A large return toward the old ~447 ms N+1 behavior is a blocker.

---

# 10. Pagination automated checks

The UI now uses `PAGE_SIZE = 100` for Papers and Authors.

Automated/API checks must prove:

```text
/api/papers?limit=100&offset=0
/api/papers?limit=100&offset=100
/api/authors?limit=100&offset=0
/api/authors?limit=100&offset=100
```

Required:

- total count is stable between pages;
- page 1 and page 2 are not identical;
- no duplicate row is introduced solely by pagination boundaries;
- offset/limit do not change source-author semantics;
- final page has <=100 items and no out-of-range error.

---

# 11. User browser semantic confirmation — mandatory

The local AI must start Paperazzi against the **test-copy database**, not the live database, and provide the localhost URL to the user.

Example:

```bash
PAPERAZZI_DB=data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
micromamba run -n Paperazzi paperazzi-web
```

The local AI may prepare evidence but may not mark this section PASS until the user explicitly confirms the browser observations.

The user must check:

### A. Papers pagination

- Papers page shows total corpus count.
- `Next` changes to a different set of papers.
- `Previous` returns to the prior page.
- page number and total page count are plausible.

### B. Authors pagination

- Authors page is no longer limited to the alphabetically first 100 identities.
- `Next` reaches later alphabetic regions.
- `Previous` returns correctly.

### C. Paper 2468

- open paper 2468;
- `Document role` is consistent with the selected article;
- `Open local PDF` opens the **main paper**, not `ct6c00473_si_001.pdf` or another SI;
- visually confirm the opened PDF is the article.

### D. Paper 2467

- source author order is correct;
- Rishab Dutta is marked `CORRESPONDING`;
- Marc Illa is marked `CORRESPONDING`;
- no unrelated author is marked `CORRESPONDING`;
- opening the PDF confirms the correspondence information.

### E. Unresolved-author semantics

Open at least one known paper with an unresolved author and confirm:

- source name remains visible;
- order is preserved;
- `UNRESOLVED` is visible;
- FIRST remains visible when the unresolved source author is first author.

### F. Identity review

- Identity Review page opens normally;
- high-priority corresponding/first-author cases remain ranked ahead of ordinary items when present;
- no obvious UI stall comparable to the old ~450 ms endpoint behavior.

The user reports each item as `PASS` or `FAIL` with the relevant paper/author ID when possible.

---

# 12. Live database deployment is NOT part of validation

Passing the test-copy validation does not authorize live mutation.

After the report and user browser confirmation are complete, the live Paperazzi database may be migrated/corrected only after an explicit user instruction such as:

```text
Apply the validated corrections to the live Paperazzi database.
```

Before live deployment, create a separate SQLite Backup API backup of the live Paperazzi DB and record its SHA-256.

Do not touch Zotero in deployment either.

---

# 13. Required report

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-post-fix-v5/PHASE5_POST_FIX_VALIDATION_REPORT.md
```

The report must contain:

1. commit SHA and migration head;
2. Python 3.13/micromamba environment proof;
3. regression-suite count/runtime/warnings;
4. real DB source fingerprint and test-copy fingerprint;
5. full-corpus counts/projection/FK result;
6. paper 2468 document-role and retraction before/after evidence;
7. paper 2467 rebuild/cross-run replacement/corresponding-author evidence;
8. 20+ multi-PDF sanity sample result;
9. extended search checks;
10. PDF positive/negative checks;
11. identity-review timings;
12. pagination API checks;
13. user browser checklist with explicit user-confirmed PASS/FAIL/PENDING;
14. statement that Zotero and the live Paperazzi DB were not modified during validation;
15. defects found and any fixes made, with pre-fix and post-fix evidence separated.

Required status block:

```text
PYTHON_313_CONTRACT = PASS|FAIL
SYNTHETIC_REGRESSION = PASS|FAIL
REAL_DB_COPY_MIGRATION = PASS|FAIL
FULL_CORPUS_AUTHOR_PROJECTION = PASS|FAIL
PAPER_2468_PRIMARY_PDF = PASS|FAIL
PAPER_2468_RETRACTION = PASS|FAIL
PAPER_2467_CORRESPONDING = PASS|FAIL
CROSS_RUN_REPLACEMENT = PASS|FAIL
MULTI_PDF_SANITY_SAMPLE = PASS|FAIL
EXTENDED_SEARCH_VALIDATION = PASS|FAIL
REAL_UNAVAILABLE_PDF_VALIDATION = PASS|FAIL
IDENTITY_REVIEW_PERFORMANCE_RECHECK = PASS|FAIL
PAGINATION_API = PASS|FAIL
USER_BROWSER_CONFIRMATION = PASS|FAIL|PENDING
ZOTERO_SOURCE_MODIFIED = NO|YES
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO|YES
EXISTING_ANACONDA_ENV_MODIFIED = NO|YES
```

A final Phase 5 post-fix validation PASS requires every mandatory item above to be `PASS`, all three mutation-safety lines to be the safe values, and `USER_BROWSER_CONFIRMATION = PASS` based on the user's actual browser inspection.

If the local AI has completed its part but the user has not yet performed browser checks, the correct overall result is:

```text
PHASE_5_POST_FIX_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
```

Do not report `PASS` early.
