# Paperazzi persistence model — Phase 3 normative design

**Status:** Normative for Phase 3. Where this document conflicts with the older persistence sketch in `DESIGN.md` v0.4, this document takes precedence for Phase 3 implementation.

Phase 2.5 is complete and the deterministic PDF baseline is frozen at v3 (`e06e2bf` included). Phase 3 turns the already validated Zotero/PDF pipelines into durable, incrementally updateable Paperazzi state.

The goal is not to implement author identity, citation matching, API, UI, or online enrichment. The goal is to persist source projections and evidence without losing provenance.

---

# 1. Core invariants

1. `zotero.sqlite` and Zotero PDFs remain **READ ONLY**.
2. Paperazzi writes only its own SQLite database, default `data/paperazzi.sqlite3`.
3. A missing DOI, creator, PDF, text layer, affiliation, reference list, or correspondence signal is valid data state.
4. Zotero stable identity is `(library_id, item_key)`.
5. Phase 3 does **not** merge Zotero items by DOI/title and does **not** resolve two creator mentions into one author.
6. Runtime AI output never writes SQL directly. It produces structured review results consumed by deterministic persistence code.
7. Failed/superseded extraction attempts remain auditable.
8. Raw reference evidence is stored independently from future `paper_reference_match` interpretation.
9. `HIGH` parser confidence is not equivalent to AI acceptance and is not equivalent to clean bibliographic text.
10. Database writes are transactional; a failed scan/extraction persistence operation must not leave a half-applied current projection.

---

# 2. Technology and connection policy

Phase 3 uses synchronous SQLAlchemy 2.x and Alembic with SQLite. Keep the persistence layer synchronous; async database code is unnecessary for the local-first Phase 3 workload.

Required SQLite connection behavior:

```text
PRAGMA foreign_keys = ON        every connection
PRAGMA busy_timeout = 5000      every connection
journal_mode = WAL              Paperazzi-owned writable DB only
```

Do not apply Paperazzi PRAGMAs to Zotero's source connection.

Recommended package boundary:

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
└── versions/
```

Operational scripts stay thin; persistence behavior belongs in `src/paperazzi/database/`.

---

# 3. Identifier policy

Phase 3 row identifiers may use SQLite `INTEGER PRIMARY KEY` values. They are Paperazzi-local database identities.

Do not misuse Zotero `itemID` as a Paperazzi identity. Preserve Zotero numeric IDs only as diagnostic/source join metadata.

Future `author_id` remains a Phase 4 UUIDv7/ULID decision. Do not create authors merely to satisfy foreign keys in Phase 3.

---

# 4. Zotero hash decomposition

The existing single `content_hash()` must be split before the persistent diff engine is considered complete.

For every `CanonicalZoteroItem`, compute four deterministic SHA-256 hashes:

```text
bibliographic_hash
organization_hash
attachment_hash
canonical_hash
```

## 4.1 `bibliographic_hash`

Include:

```text
library_id
item_key
item_type
fields{}
ordered creators[]
```

Exclude Zotero internal numeric IDs, sync counters, timestamps, local-file existence, tags, collections, and attachment state.

A bibliographic-hash change is the change class that future author enrichment/identity logic may care about.

## 4.2 `organization_hash`

Include normalized/sorted:

```text
collections[]
tags[]
```

Tag/collection-only changes must not masquerade as bibliographic changes.

## 4.3 `attachment_hash`

Include stable attachment record content:

```text
attachment library_id/item_key
link_mode/link_mode_name
content_type
stored path
storage_hash
```

Exclude local existence/resolution and volatile sync timestamps. Local availability is tracked separately in `paper_documents`.

## 4.4 `canonical_hash`

Hash a stable object containing the three component hashes only:

```text
bibliographic_hash
organization_hash
attachment_hash
```

Presence/removal/deleted operational state is tracked separately and must not be folded into the semantic content hash. `canonical_hash` is a convenient whole-item checksum, not the only diff signal.

---

# 5. Zotero scan persistence

## 5.1 `zotero_scan_runs`

One row per manually triggered Zotero scan.

Required columns:

```text
scan_run_id                 INTEGER PK
run_token                   TEXT UNIQUE
status                      STARTED / COMPLETED / FAILED
source_db_path              TEXT
source_db_size              INTEGER nullable
source_db_mtime_ns          INTEGER nullable
snapshot_path               TEXT nullable
adapter_name                TEXT
userdata_version            INTEGER nullable
global_schema_version       INTEGER nullable
started_at                  UTC timestamp
completed_at                UTC timestamp nullable
item_count                  INTEGER nullable
new_count                   INTEGER nullable
modified_count              INTEGER nullable
unchanged_count             INTEGER nullable
removed_count               INTEGER nullable
restored_count              INTEGER nullable
bibliographic_corpus_hash   TEXT nullable
canonical_corpus_hash       TEXT nullable
error_type                  TEXT nullable
error_message               TEXT nullable
```

A STARTED row should be committed before the main projection transaction. On failure, roll back projection changes and mark the run FAILED.

## 5.2 `papers`

Phase 3 creates one Paperazzi paper row for each Zotero bibliographic item and does **no DOI/title deduplication**.

Required current-projection columns:

```text
paper_id                    INTEGER PK
title                       TEXT nullable
doi                         TEXT nullable
publication_year            INTEGER nullable
publication_date_text       TEXT nullable
venue                       TEXT nullable
item_type                   TEXT nullable
active_in_zotero            BOOLEAN NOT NULL
created_at
updated_at
```

Index DOI, title, publication year, but **do not put a UNIQUE constraint on DOI**.

External/non-Zotero papers can be added in later phases without changing Zotero identity semantics.

## 5.3 `zotero_item_state`

Current durable state of a Zotero bibliographic item.

```text
zotero_item_state_id        INTEGER PK
paper_id                    FK papers
library_id                  INTEGER
item_key                    TEXT
zotero_item_id              INTEGER diagnostic only
item_type                   TEXT
zotero_version              INTEGER nullable
date_added                  TEXT nullable
date_modified               TEXT nullable
client_date_modified        TEXT nullable
deleted                     BOOLEAN
present_in_last_scan        BOOLEAN
first_seen_run_id           FK zotero_scan_runs
last_seen_run_id            FK zotero_scan_runs
bibliographic_hash          TEXT
organization_hash           TEXT
attachment_hash             TEXT
canonical_hash              TEXT
canonical_payload_json      TEXT
created_at
updated_at
```

Constraint:

```text
UNIQUE(library_id, item_key)
```

Do **not** make `paper_id` unique here. Phase 3 creates one paper per Zotero item, but future paper-identity consolidation may legitimately map multiple Zotero source items onto one Paperazzi paper without rewriting the source-state schema.

`canonical_payload_json` is an audit/rebuild convenience; it does not replace first-class creator/tag/collection/attachment tables.

## 5.4 `zotero_item_versions`

Append-only history written only when the logical state changes.

```text
zotero_item_version_id      INTEGER PK
zotero_item_state_id        FK
scan_run_id                 FK
change_type                 NEW / MODIFIED / REMOVED / RESTORED
changed_dimensions_json     TEXT
bibliographic_hash          TEXT nullable
organization_hash           TEXT nullable
attachment_hash             TEXT nullable
canonical_hash              TEXT nullable
canonical_payload_json      TEXT nullable
created_at
```

Constraint:

```text
UNIQUE(zotero_item_state_id, scan_run_id)
```

Do not create version rows for UNCHANGED items.

## 5.5 Paper-local creator mentions

Use `paper_creator_mentions`, not `authors`, in Phase 3.

```text
creator_mention_id          INTEGER PK
paper_id                    FK
zotero_item_state_id        FK
source_creator_id           INTEGER diagnostic only
creator_type                TEXT
order_index                 INTEGER
first_name                  TEXT nullable
last_name                   TEXT nullable
field_mode                  INTEGER nullable
display_name                TEXT
created_at
updated_at
```

These are source-local authorship/creator mentions. Phase 4 will map mentions to stable authors.

## 5.6 Tags and collections

Persist current first-class projections:

```text
zotero_item_tags
zotero_item_collections
```

Their rows are replaced transactionally when `organization_hash` changes.

## 5.7 `zotero_attachments`

Current attachment records:

```text
zotero_attachment_id       INTEGER PK
paper_id                    FK
zotero_item_state_id        FK
library_id                  INTEGER
item_key                    TEXT
zotero_item_id              INTEGER diagnostic only
link_mode                   INTEGER
link_mode_name              TEXT
content_type                TEXT nullable
stored_path                 TEXT nullable
resolved_path               TEXT nullable
resolution                  TEXT
local_exists                BOOLEAN nullable
storage_hash                TEXT nullable
storage_mod_time            INTEGER nullable
present_in_last_scan        BOOLEAN
last_seen_run_id            FK zotero_scan_runs
created_at
updated_at
```

Constraint:

```text
UNIQUE(library_id, item_key)
```

---

# 6. Scan diff semantics

For each current Zotero item:

```text
no prior state                         -> NEW
prior present=false                    -> RESTORED
prior present=true + any hash changed -> MODIFIED
otherwise                              -> UNCHANGED
```

For each previously present item not seen in the current active scan:

```text
REMOVED
```

A MODIFIED item must record changed dimensions independently:

```text
BIBLIOGRAPHIC
ORGANIZATION
ATTACHMENT
```

Examples:

```text
tag only changes        -> MODIFIED[ORGANIZATION]
new DOI/title change    -> MODIFIED[BIBLIOGRAPHIC]
attachment replacement -> MODIFIED[ATTACHMENT]
```

Do not delete historical state rows when an item disappears. Set `present_in_last_scan=false`, `papers.active_in_zotero=false`, append a REMOVED version, and retain evidence/history.

---

# 7. Local document state

## 7.1 `paper_documents`

Create a document row for every Zotero PDF attachment record, including PDFs not currently present on disk.

```text
document_id                  INTEGER PK
paper_id                     FK
zotero_attachment_id         FK UNIQUE
content_type                 TEXT
local_path                   TEXT nullable
availability_status          PDF_AVAILABLE / PDF_RECORD_ONLY / UNRESOLVED_PATH / FILE_UNAVAILABLE
file_size                    INTEGER nullable
file_mtime_ns                INTEGER nullable
zotero_storage_hash          TEXT nullable
document_change_key          TEXT nullable
present_in_last_scan         BOOLEAN
first_seen_run_id            FK zotero_scan_runs
last_seen_run_id             FK zotero_scan_runs
current_extraction_run_id    FK nullable
created_at
updated_at
```

`document_change_key`:

```text
preferred: "zotero:" + storage_hash
fallback when local file exists: "fs:" + file_size + ":" + file_mtime_ns
unavailable: NULL
```

A transition from unavailable to available triggers extraction even when the storage hash itself is unchanged.

---

# 8. Extraction runs and attempts

The old sketch `UNIQUE(document_id, attempt_number)` is intentionally superseded. A document may be re-extracted in the future after a file, extractor, or prompt change.

## 8.1 `document_extraction_runs`

One row per extraction cycle for a document.

```text
extraction_run_id            INTEGER PK
document_id                  FK
trigger                      FIRST_AVAILABLE / FILE_CHANGED / EXTRACTOR_CHANGED / PROMPT_CHANGED / MANUAL_REBUILD
status                       STARTED / COMPLETED / FAILED
document_change_key          TEXT nullable
extractor_version            TEXT
prompt_version               TEXT nullable
prompt_hash                  TEXT nullable
started_at
completed_at                 nullable
final_status                 PASS / ACCEPT_PARTIAL / UNRESOLVED / NEEDS_OCR / FAILED nullable
accepted_attempt_id          FK document_extraction_attempts nullable
error_type                   TEXT nullable
error_message                TEXT nullable
```

## 8.2 `document_extraction_attempts`

```text
attempt_id                    INTEGER PK
extraction_run_id             FK
attempt_number                INTEGER 1..3
actor                         DETERMINISTIC / LOCAL_AI_CONTROLLED / OCR
strategy                      TEXT
strategy_parameters_json      TEXT nullable
backend                       TEXT nullable
backend_version               TEXT nullable
text_source                   TEXT
text_channel                  TEXT nullable
channels_evaluated_json       TEXT nullable
prompt_version                TEXT nullable
prompt_hash                   TEXT nullable
decision                      PASS / ACCEPT_PARTIAL / RETRY / UNRESOLVED / NEEDS_OCR
problem_codes_json            TEXT
section_confidence            TEXT nullable
segmentation_confidence       TEXT nullable
entry_text_quality            TEXT nullable
front_matter_status           TEXT nullable
reference_status              TEXT nullable
output_hash                   TEXT nullable
quality_notes                 TEXT nullable
runtime_artifact_path         TEXT nullable
started_at
completed_at
```

Constraints:

```text
CHECK(attempt_number BETWEEN 1 AND 3)
UNIQUE(extraction_run_id, attempt_number)
```

### Text-channel provenance

Deterministic v3 evaluates at least two PyMuPDF text variants for references:

```text
PYMUPDF_SORTED
PYMUPDF_CONTENT_STREAM
```

The selected result must record `text_channel`. `channels_evaluated_json` records the variants considered. This is provenance, not an additional AI attempt.

`HIGH` segmentation confidence means the structural split is plausible; it does not promise that every raw entry is free from two-column/body-text contamination. Preserve `entry_text_quality` separately.

---

# 9. Evidence and references

## 9.1 `document_evidence_spans`

```text
evidence_span_id             INTEGER PK
document_id                  FK
attempt_id                   FK
kind                         TEXT
page_start                   INTEGER
page_end                     INTEGER nullable
bbox_json                    TEXT nullable
raw_text                     TEXT
raw_text_hash                TEXT
text_source                  TEXT
text_channel                 TEXT nullable
acceptance_status            CANDIDATE / ACCEPTED / REJECTED / SUPERSEDED
created_at
```

Rejected/superseded evidence remains stored.

## 9.2 `paper_reference_sections`

```text
reference_section_id         INTEGER PK
paper_id                     FK
document_id                  FK
attempt_id                   FK
heading                      TEXT
is_explicit_heading          BOOLEAN
start_page                   INTEGER
end_page                     INTEGER
parse_method                 TEXT
section_confidence           TEXT
segmentation_confidence      TEXT nullable
entry_text_quality           TEXT nullable
text_source                  TEXT
text_channel                 TEXT nullable
acceptance_status            CANDIDATE / ACCEPTED / REJECTED / SUPERSEDED
raw_text                     TEXT
raw_text_hash                TEXT
created_at
```

Reference-section recovery and reference-entry segmentation are different success levels. Raw accepted sections are valid even with zero segmented entries.

## 9.3 `paper_references`

```text
reference_id                 INTEGER PK
citing_paper_id              FK
reference_section_id         FK
document_id                  FK
originating_attempt_id       FK
ordinal                      INTEGER nullable
raw_text                     TEXT
raw_text_hash                TEXT
acceptance_status            CANDIDATE / ACCEPTED / REJECTED / SUPERSEDED
created_at
```

Constraint:

```text
UNIQUE(reference_section_id, ordinal)
```

SQLite permits multiple NULL values, so unnumbered records remain possible later.

## 9.4 `paper_reference_identifiers`

Strong parsed identifiers are first-class rows, not a single DOI column:

```text
reference_identifier_id      INTEGER PK
reference_id                 FK
identifier_type              DOI / YEAR / other future type
identifier_value             TEXT
normalized_value             TEXT
extractor                    TEXT
created_at
```

Constraint:

```text
UNIQUE(reference_id, identifier_type, normalized_value)
```

This accommodates grouped references that contain more than one DOI/year.

## 9.5 `paper_reference_matches`

Create the table/schema in Phase 3, but do not implement matching policy yet.

```text
reference_match_id           INTEGER PK
reference_id                 FK
cited_paper_id               FK
match_type                   TEXT
match_score                  REAL nullable
status                       CANDIDATE / ACCEPTED / REJECTED
resolver                     TEXT
created_at
```

Phase 4 owns DOI/title/composite/AI matching. Phase 3 must not generate `CITES` edges.

---

# 10. Transaction and replacement rules

## Zotero scan

- scan-run STARTED row is durable;
- one transaction applies current item projections and REMOVED/RESTORED state;
- on failure, roll back projection transaction and mark run FAILED;
- on success, mark run COMPLETED with counts/hashes.

## Current child projections

When a changed Zotero item is persisted, replace its current creator/tag/collection projection transactionally. Attachment rows are upserted by stable attachment identity and absent children are marked not present rather than silently resurrected.

## Extraction run

Persist attempt history append-only. When a later attempt is accepted:

- do not delete Attempt 1/2 rows;
- mark their candidate evidence/reference outputs `SUPERSEDED` or `REJECTED` as appropriate;
- accepted evidence points to the accepted attempt;
- `paper_documents.current_extraction_run_id` points to the latest completed accepted cycle.

---

# 11. Phase boundaries

Phase 3 explicitly does **not** implement:

```text
author identity merge/split
author_id creation from creator mentions
author-affiliation semantic assignment
corresponding-author semantic assignment
reference-to-paper matching logic
citation graph edges
online enrichment
FastAPI/UI
FTS search
OCR engine integration
```

Only persistence interfaces/table placeholders needed for the next phase may be created.

---

# 12. Required indexes and integrity checks

At minimum index:

```text
papers(doi)
papers(title)
papers(publication_year)
zotero_item_state(library_id, item_key) UNIQUE
zotero_item_state(last_seen_run_id)
paper_creator_mentions(paper_id, order_index)
zotero_attachments(library_id, item_key) UNIQUE
paper_documents(paper_id)
paper_documents(document_change_key)
document_extraction_runs(document_id, started_at)
document_extraction_attempts(extraction_run_id, attempt_number) UNIQUE
document_evidence_spans(document_id, kind)
paper_reference_sections(document_id, acceptance_status)
paper_references(citing_paper_id)
paper_references(reference_section_id, ordinal) UNIQUE
paper_reference_identifiers(identifier_type, normalized_value)
paper_reference_matches(reference_id, status)
```

Tests must execute `PRAGMA foreign_key_check` and expect no rows.

---

# 13. Design principle

The persistent database is not a cache of guessed facts. It is a durable ledger of:

```text
source projection
+ extraction history
+ evidence
+ acceptance state
+ later interpretations
```

That separation is the foundation required before Paperazzi can safely perform identity resolution, citation matching, graph construction, and online enrichment.