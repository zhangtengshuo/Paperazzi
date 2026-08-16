# Phase 3 — Persistence implementation plan

**Phase status at start:** Phase 1/2 complete; Phase 2.5 PASS; deterministic PDF baseline `FROZEN_V3` including commit `e06e2bf`.

**Normative schema:** `docs/architecture/PERSISTENCE_MODEL.md`

Phase 3 builds the first real `paperazzi.sqlite3`. It is intentionally divided into four milestones with hard gates. Do not implement Phase 4 identity/citation semantics during this phase.

---

# 0. Scope

Deliver a durable local database that can:

1. ingest current active Zotero bibliographic items from a read-only snapshot;
2. persist current Zotero projections plus append-only change history;
3. compute `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` deterministically;
4. distinguish bibliographic, organization and attachment changes;
5. persist PDF document availability independently from Zotero bibliographic changes;
6. persist PDF extraction runs/attempts, AI review provenance, evidence spans, reference sections and reference entries;
7. preserve accepted, rejected and superseded extraction history;
8. migrate schema reproducibly with Alembic;
9. survive repeated no-change scans without duplicating papers/evidence;
10. leave author identity and reference matching for Phase 4.

---

# 1. Phase 3A — Database foundation

## 3A.1 Dependencies

Add runtime dependencies for Phase 3:

```text
SQLAlchemy 2.x
Alembic 1.x
```

Keep PyMuPDF in the existing optional `pdf` dependency group unless implementation has a concrete reason to change packaging.

Do not add FastAPI, graph databases, PostgreSQL clients, async SQLAlchemy, or frontend dependencies in Phase 3.

## 3A.2 Package structure

Create:

```text
src/paperazzi/database/
├── __init__.py
├── base.py
├── engine.py
├── models.py
├── repositories.py
└── persistence.py

migrations/
├── env.py
├── script.py.mako
└── versions/

alembic.ini
```

Names may be split into multiple model files if `models.py` becomes unwieldy, but keep one explicit metadata/registry and avoid circular imports.

## 3A.3 Engine behavior

Implement a Paperazzi-owned SQLite engine with:

```text
foreign_keys=ON
busy_timeout=5000
WAL for writable Paperazzi DB
```

The Zotero reader remains the existing stdlib `sqlite3` read-only path. Do not route Zotero through the writable SQLAlchemy engine.

## 3A.4 Migration sequence

Prefer two initial migrations:

```text
0001_zotero_persistence
0002_document_evidence_references
```

`0001`:

```text
zotero_scan_runs
papers
zotero_item_state
zotero_item_versions
paper_creator_mentions
zotero_item_tags
zotero_item_collections
zotero_attachments
paper_documents
```

`0002`:

```text
document_extraction_runs
document_extraction_attempts
document_evidence_spans
paper_reference_sections
paper_references
paper_reference_identifiers
paper_reference_matches
```

Do not rely only on `Base.metadata.create_all()` in production. Tests may use it only for isolated model tests; actual DB initialization must upgrade through Alembic.

## 3A.5 Gate tests

Before Phase 3B:

- fresh temporary SQLite DB upgrades to `head`;
- `PRAGMA foreign_keys` returns 1;
- `PRAGMA foreign_key_check` returns no rows;
- all expected tables/indexes exist;
- a second `alembic upgrade head` is a no-op;
- downgrade/upgrade is tested at least across the two Phase 3 migrations on a temporary DB;
- no Zotero DB/PDF is needed for these tests.

Commit Phase 3A separately.

---

# 2. Phase 3B — Hashes, diff engine and Zotero persistence

## 3B.1 Split canonical hashes

Refactor `CanonicalZoteroItem` hashing without changing the Zotero reader contract.

Expose deterministic methods/properties conceptually equivalent to:

```text
bibliographic_payload/hash
organization_payload/hash
attachment_payload/hash
canonical_payload/hash
```

Keep `content_hash()` temporarily as a compatibility alias only if existing tests/scripts require it; new persistence code must use the split hashes.

Add regression tests proving:

```text
title/DOI/creator change -> bibliographic_hash changes
collection/tag change    -> organization_hash changes only
attachment record change -> attachment_hash changes only
local_exists change      -> none of the three semantic hashes changes
zotero_version/dateModified-only change -> no semantic hash changes
```

## 3B.2 Diff model

Implement an explicit diff result object, not ad-hoc conditionals buried in repository code.

Suggested model:

```text
ItemChange
- identity
- change_type: NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED
- changed_dimensions: set[BIBLIOGRAPHIC, ORGANIZATION, ATTACHMENT]
- previous hashes
- current hashes
```

## 3B.3 Scan service

Implement a service that consumes canonical records and persists one scan atomically.

Suggested API shape:

```python
persist_zotero_scan(
    session_factory,
    canonical_items,
    scan_metadata,
) -> ScanResult
```

Do not make the persistence layer execute Zotero-specific SQL. The caller supplies `CanonicalZoteroItem` records produced by the validated reader.

## 3B.4 Projection rules

For NEW item:

- create `papers` row;
- create `zotero_item_state`;
- append NEW `zotero_item_versions`;
- populate creator/tag/collection/attachment projections;
- create/update PDF `paper_documents` rows.

For MODIFIED:

- retain paper identity;
- update only affected projections where practical;
- append one MODIFIED version with changed dimensions;
- do not create a new paper row.

For UNCHANGED:

- update `last_seen_run_id`/presence bookkeeping as needed;
- do not append an item version;
- do not churn current child rows unnecessarily.

For REMOVED:

- set source state and paper inactive;
- append REMOVED version;
- retain paper/evidence/history;
- never cascade-delete the scholarly record.

For RESTORED:

- reuse the same `paper_id` and `zotero_item_state_id`;
- set active/present true;
- append RESTORED version.

## 3B.5 No paper deduplication

Two Zotero items with the same DOI/title must remain two Phase 3 paper rows. Add an explicit test for this.

## 3B.6 Gate tests

Synthetic scan sequence must cover:

```text
scan 1: item A                         -> NEW
scan 2: identical A                   -> UNCHANGED
scan 3: A title changes               -> MODIFIED[BIBLIOGRAPHIC]
scan 4: only tag changes              -> MODIFIED[ORGANIZATION]
scan 5: only attachment record changes-> MODIFIED[ATTACHMENT]
scan 6: A absent                       -> REMOVED
scan 7: A reappears                   -> RESTORED
```

Also test:

- no duplicate paper rows after repeated scans;
- no version row for UNCHANGED;
- current creator order is preserved;
- deleted/absent attachment cannot be silently resurrected;
- transaction rollback leaves previous current state intact;
- duplicate `(library_id,item_key)` is rejected.

Commit Phase 3B separately.

---

# 3. Phase 3C — PDF document and evidence persistence

## 3C.1 Document state

Implement filesystem state collection only for resolved local PDF paths. Stat operations are read-only.

For every Zotero PDF attachment record, persist `paper_documents` even when the file is absent.

Document extraction eligibility is independent from bibliographic hashes.

Trigger conditions:

```text
first local availability
file/document change key change
extractor version change
meaningful prompt version/hash change
manual rebuild
```

A bibliography title/DOI change alone must not trigger PDF re-extraction.

## 3C.2 Extraction cycles

A document can have many extraction runs over its lifetime. Each run has at most three attempts.

Important correction from old design:

```text
UNIQUE(extraction_run_id, attempt_number)
```

not:

```text
UNIQUE(document_id, attempt_number)
```

This must be covered by a test where a document completes one Attempt-1 run, then later starts another extraction run whose first attempt is again `attempt_number=1`.

## 3C.3 Deterministic Attempt 1 persistence

Persist:

- extractor/backend version;
- prompt version/hash used for subsequent review;
- text source;
- selected `text_channel`;
- `channels_evaluated_json`;
- decision/status;
- evidence spans;
- reference section, raw section and segmented entries;
- parsed DOI/year identifiers;
- structure confidence and entry-text quality separately.

Frozen v3 internally evaluates sorted and content-stream text for references. Phase 3 must expose/persist enough provenance to know which channel produced the accepted reference result. Adding provenance metadata is allowed; do not change v3 parsing behavior without a new regression-driven parser version.

## 3C.4 AI-reviewed retry persistence

Use `prompts/local_ai/PDF_EVIDENCE_AGENT.md` and `schemas/pdf_evidence_review.schema.json` as the runtime review contract.

If Attempt 2/3 occurs:

- preserve earlier attempt rows;
- preserve candidate/rejected evidence;
- set accepted/superseded status deterministically;
- never let the AI open a direct database write connection as part of production review;
- persistence code consumes structured review output.

## 3C.5 Reference semantics

Persist raw references and identifiers, but do not match them to cited papers in Phase 3.

`paper_reference_matches` exists as an empty/reserved table after migration. No `CITES` graph is built yet.

## 3C.6 Gate tests

Synthetic PDF/evidence persistence must cover:

- document unavailable -> available transition;
- storage-hash change triggers a new extraction run;
- fallback file-size/mtime change key when storage hash absent;
- unchanged file does not create a duplicate extraction run;
- attempts 1..3 allowed, attempt 4 rejected;
- later extraction run may start at attempt 1 again;
- accepted Attempt 2 supersedes Attempt 1 outputs but does not delete them;
- `text_channel` and `channels_evaluated_json` persisted;
- HIGH segmentation + PARTIAL entry-text quality can coexist;
- raw reference section with zero entries persists successfully;
- grouped reference may persist multiple DOI/year identifier rows;
- foreign-key integrity remains clean.

Commit Phase 3C separately.

---

# 4. Phase 3D — Real-library validation

Only start after all synthetic/unit tests pass.

## 3D.1 Fresh real database

Create a new ignored runtime database, for example:

```text
data/phase3-validation/paperazzi.sqlite3
```

Do not commit it.

## 3D.2 Full Zotero metadata import

Run one full active-library scan from the real read-only Zotero snapshot.

Validate at least:

- Paperazzi item/paper counts correspond to the canonical reader output;
- no duplicate `(library_id,item_key)`;
- creator mention counts/order are plausible;
- PDF attachment/document availability states correspond to canonical attachment records;
- `PRAGMA foreign_key_check` is empty.

Then immediately run the same scan again with no source changes.

Expected second-run property:

```text
NEW=0
MODIFIED=0
REMOVED=0
RESTORED=0
all current items UNCHANGED
no duplicate papers
no new item-version rows
```

Do not mutate the real Zotero database merely to manufacture diff states. Diff transitions are covered by synthetic tests.

## 3D.3 PDF persistence validation sample

Use the same 200-document deterministic selection pattern as Phase 2.5c or a deterministic equivalent.

Persist deterministic v3 extraction/review results into the Phase 3 DB and verify database counts against the extraction run outputs.

At minimum check anchors:

```text
QuTiP-BoFiN
Rota 1964
Soriano & Palacios 2014
JACS parenthesized-footnote case
known Nature/two-column long-tail case
```

Do not require all 2161 local PDFs to complete AI review as a Phase 3 acceptance gate. Full-library evidence population is an operational run after persistence correctness is proven.

## 3D.4 Idempotency

Re-persist the same accepted extraction result and ensure it does not silently duplicate current accepted evidence/reference rows. Choose a clear repository contract: either reject duplicate run tokens/output hashes or detect and return an existing result.

## 3D.5 Failure injection

Using temporary/synthetic data, inject an exception during a scan/persistence transaction and verify:

- current projection rolls back;
- scan/extraction run records end as FAILED;
- prior accepted data remains queryable.

---

# 5. Required Phase 3 report

Commit only compact reports under:

```text
docs/phase3/runs/<timestamp>-phase3/
├── PHASE3_REPORT.md
└── phase3_report.json
```

Do not commit:

```text
paperazzi.sqlite3
Zotero snapshots
PDFs
full article text
full raw bibliographies
runtime AI scratch scripts
```

Report at least:

```text
migration_head
unit_tests
foreign_key_check
full_zotero_item_count
paper_count
creator_mention_count
pdf_document_count
local_pdf_available_count
first_scan NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED
second_scan NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED
item_version_rows_after_first_scan
item_version_rows_after_second_scan
extraction_run_count_sample
attempt_count_sample
evidence_span_count_sample
reference_section_count_sample
reference_entry_count_sample
reference_identifier_count_sample
idempotency_result
rollback_injection_result
```

---

# 6. Phase 3 acceptance

Phase 3 passes only if all are true:

1. migrations are reproducible on a fresh DB;
2. foreign keys/check constraints are enforced;
3. split hashes behave exactly by dimension;
4. repeated unchanged real scan is idempotent;
5. REMOVED/RESTORED preserve Paperazzi identity in synthetic tests;
6. local PDF availability is independent from bibliographic change detection;
7. multiple extraction cycles preserve bounded attempt history correctly;
8. text-channel provenance is persisted;
9. parser structural confidence and entry text quality are distinct;
10. raw references/evidence survive without semantic matching;
11. failed transactions roll back cleanly;
12. no Phase 4 author/citation identity assumptions were introduced.

On success record:

```text
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

---

# 7. Implementation discipline

If a real-library failure reveals a general persistence bug:

```text
reproduce with synthetic test
→ fix code
→ rerun affected gate
→ commit fix
```

Do not patch database rows manually to make a validation report pass. The system must be rebuildable from read-only Zotero/PDF evidence plus version-controlled code.