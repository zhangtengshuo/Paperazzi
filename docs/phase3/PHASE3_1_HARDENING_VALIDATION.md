# Phase 3.1 — Persistence Hardening validation

**Purpose:** validate the persistence fixes found during post-Phase-3 code review before `PHASE3_V1` is frozen and before Phase 4 identity/reference resolution begins.

This is a **database correctness** validation. It is not another Phase 2.5 PDF-quality experiment and does not require re-reviewing 200 PDFs with AI.

---

## 1. Fixed bugs covered by this validation

Phase 3.1 must verify all of the following:

1. an `UNCHANGED` Zotero item still refreshes attachment/PDF runtime filesystem state;
2. `zotero_attachments` may contain all Zotero attachments, but `paper_documents` contains PDF attachments only;
3. parent removal and child-attachment removal propagate `present_in_last_scan=false` to `paper_documents`;
4. `linked-absolute-path` PDFs are recognized correctly;
5. filesystem document fallback keys are `fs:<file_size>:<mtime_ns>`;
6. deterministic Attempt 1 is persisted as `REVIEW_PENDING` and candidate evidence, never as accepted output before AI/manual review;
7. prompt hash is SHA-256 of the actual `PDF_EVIDENCE_AGENT.md` bytes;
8. section confidence, segmentation confidence and entry-text quality are not derived from one field;
9. accepted/current extraction pointers are protected by real foreign keys;
10. paper-local creator mention IDs survive organization-only and attachment-only Zotero changes.

---

## 2. Important migration rule

Phase 3 had not yet been frozen as a production schema when these bugs were found. The hardening patch therefore amends migration `0002_document_evidence_references` before freeze and adds:

```text
0003_extraction_reviews
```

**Do not reuse `data/phase3-validation/paperazzi.sqlite3` from the previous Phase 3D run.**

For this validation create a fresh ignored Paperazzi DB from migration head. Zotero and its PDFs remain read-only.

Expected migration head:

```text
0003_extraction_reviews (head)
```

---

## 3. Gate A — complete unit/regression suite

Run first:

```bash
python -m unittest discover -s tests -v
```

Do not continue if any test fails.

The suite must now include hardening regressions for:

```text
non-PDF attachment -> no paper_document
PDF_RECORD_ONLY -> PDF_AVAILABLE while Zotero semantic hash stays UNCHANGED
linked-absolute-path
fs:size:mtime_ns change key
parent/child removal propagation
creator_mention_id stability
prompt content hash
mandatory review gate
pending-run duplicate suppression
review provenance table
accepted_attempt/current_run FK integrity
raw reference section: section confidence != segmentation confidence
```

If a failure is a real implementation bug, add/adjust a synthetic regression test first, then fix the code. Do not patch around one real Zotero item.

---

## 4. Gate B — migration integrity on a fresh database

Use a fresh temporary/ignored DB and verify:

```text
alembic upgrade head
alembic current -> 0003_extraction_reviews (head)
PRAGMA foreign_key_check -> zero rows
```

Also inspect foreign keys and confirm:

```text
paper_documents.current_extraction_run_id
    -> document_extraction_runs.extraction_run_id

document_extraction_runs.accepted_attempt_id
    -> document_extraction_attempts.attempt_id

document_extraction_reviews.attempt_id
    -> document_extraction_attempts.attempt_id
```

`document_extraction_attempts.decision` must accept `REVIEW_PENDING`.

---

## 5. Gate C — real Zotero scan ×2

Run the updated validator:

```bash
python scripts/validate_phase3.py
```

It creates a fresh ignored DB under `data/phase3-validation/`, snapshots Zotero read-only, and imports the complete active canonical library twice.

Required behavior:

```text
first scan:
  all currently active Zotero items -> NEW

second scan:
  NEW       0
  MODIFIED  0
  REMOVED   0
  RESTORED  0
  UNCHANGED == full active item count
```

The second scan must create no duplicate papers and no new item-version churn.

### PDF document boundary

The validator computes current expected values directly from `CanonicalZoteroItem` rather than comparing with an old hard-coded Phase 2.5 count.

Require:

```text
paper_documents count
    == current Zotero attachment records whose content_type == application/pdf

PDF_AVAILABLE count
    == current local-existing PDF attachment count

non_pdf_document_count == 0
```

A change in the user's Zotero library since Phase 2.5 is therefore allowed.

---

## 6. Gate D — deterministic 200-PDF persistence sample

The validator reuses the frozen-v3 deterministic 200-document sample when available.

The purpose is **not** to re-prove parser quality. It verifies persistence semantics.

Expected deterministic counts should remain consistent with the frozen-v3 sample where the same 200 files remain available, especially:

```text
reference sections     153
reference entries      7363
```

If the local library changed and a sampled file disappeared, report the exact difference rather than forcing old counts.

### Mandatory review gate

After the deterministic sample is persisted, require:

```text
Attempt 1 decision                  REVIEW_PENDING
DocumentExtractionReview rows       0   (validator itself does not impersonate AI review)
evidence ACCEPTED rows              0
reference section ACCEPTED rows     0
reference ACCEPTED rows             0
documents_with_current_run          0
```

The deterministic outputs must remain:

```text
CANDIDATE
```

A `NATIVE_TEXT_GOOD` PDF is **not** automatically `PASS`.

At the same time, calling `decide_extraction_trigger()` again for documents with an existing `STARTED`/review-pending run must return no new trigger. Waiting for AI review must not create duplicate extraction runs.

Do **not** run mandatory AI review across all 200 PDFs for this Phase 3.1 validation. Phase 2.5b already validated that quality-control workflow. Here the database only needs to prove that acceptance cannot occur without a review record.

---

## 7. Gate E — confidence semantics

Check the persisted anchor diagnostics.

### Rota 1964 (`MD8N7CDD`)

Expected deterministic candidate semantics:

```text
section exists               yes
explicit References heading  yes
section_confidence           HIGH
segmentation_confidence      NULL / none
entry_text_quality           UNREVIEWED
entries                      0
acceptance_status            CANDIDATE
```

This is intentionally different from the old `MEDIUM/MEDIUM/PARTIAL` persistence mapping.

### QuTiP-BoFiN (`I97Q72KK`)

Expected:

```text
78 entries
text_channel = PYMUPDF_CONTENT_STREAM
section_confidence = HIGH
segmentation_confidence = HIGH
entry_text_quality = UNREVIEWED
acceptance_status = CANDIDATE
```

### Nature-style (`87JCS8EY`)

The deterministic structural result may still be HIGH, but `entry_text_quality` must remain `UNREVIEWED` until local-AI review. Never infer `GOOD` from `NATIVE_TEXT_GOOD`.

---

## 8. Gate F — review/acceptance state machine

This is covered primarily by synthetic tests; do not repeat a large AI run.

Required transition:

```text
Attempt 1 created
  actor = DETERMINISTIC
  decision = REVIEW_PENDING
  evidence/reference = CANDIDATE
        ↓
DocumentExtractionReview created
  reviewer_type = LOCAL_AI or MANUAL
  decision = PASS / ACCEPT_PARTIAL / RETRY / ...
        ↓
accept_attempt() only allowed if a review exists
```

For `PASS` / accepted partial output:

```text
run.status = COMPLETED
run.accepted_attempt_id = reviewed attempt
paper_document.current_extraction_run_id = run
accepted attempt evidence/reference -> ACCEPTED
older retry outputs -> SUPERSEDED where applicable
```

Calling `accept_attempt()` without any review row must raise `ExtractionError` and leave candidate state unchanged.

`RETRY` review cannot finalize a run.

---

## 9. Gate G — runtime-state and identity-stability regressions

Synthetic tests must prove:

### Local PDF arrives without Zotero metadata change

```text
scan 1: PDF_RECORD_ONLY
scan 2: same canonical/attachment hash, file now exists
scan 2 item change = UNCHANGED
paper_document = PDF_AVAILABLE
FIRST_AVAILABLE extraction trigger becomes possible
```

### Creator mention stability

A tag-only or attachment-only update must not delete/reinsert creator mentions.

Require the same:

```text
creator_mention_id
```

before and after those changes.

This is required before Phase 4 can safely map creator mentions to stable authors.

---

## 10. Gate H — rollback and integrity

The updated validator retains the duplicate-Zotero-identity failure injection.

Require:

```text
scan result = FAILED
scan run row = FAILED
partial paper projection = 0 rows in the fresh injection DB
```

Finally:

```text
PRAGMA foreign_key_check
```

must return zero rows.

---

## 11. What not to do

Do not:

- modify `zotero.sqlite`;
- modify Zotero PDFs;
- rerun a 2161/2175-document AI review;
- implement Phase 4 author identity;
- match references to cited papers;
- build CITES edges;
- add API/frontend work;
- weaken the mandatory review gate to make old Phase 3D counts pass.

If the real Zotero library changed since the previous run, report current counts and explain the delta.

---

## 12. Required compact report

After all gates pass, commit a compact report under:

```text
docs/phase3/runs/<timestamp>-phase3-1-hardening/
```

Include at minimum:

```text
unit tests: passed / failed
migration head
foreign_key_check rows
first/second full scan counts
paper count
creator mention count
all Zotero attachment count
PDF document count
expected PDF attachment count
PDF_AVAILABLE count
expected local PDF count
non-PDF paper_document count
200-sample candidate attempt count
candidate/accepted evidence counts
review row count during deterministic validation
pending-run duplicate-trigger count
QuTiP / Rota / Soriano / JACS / Nature anchor states
rollback injection result
```

Also state whether all nine persistence bugs identified in the post-Phase-3 review are closed.

Only if every gate passes, report:

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

If any gate fails, keep Phase 4 blocked and report the failing invariant precisely.
