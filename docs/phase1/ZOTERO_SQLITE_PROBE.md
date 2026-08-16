# Phase 1 — Real Zotero SQLite reconnaissance

## Purpose

Before Paperazzi implements a production Zotero importer, inspect the user's **actual** `zotero.sqlite` database and verify that the planned read-only snapshot architecture works on that machine.

This phase answers five questions:

1. Can Python open the real Zotero database read-only while Zotero is closed?
2. Can SQLite Backup API create a consistent Paperazzi-owned snapshot?
3. Does the same process still work while Zotero Desktop is open and may have WAL/SHM sidecars?
4. What exact Zotero schema/version, table columns and row populations exist in this library?
5. Can we correctly reconstruct bibliographic items, creator order/types and PDF storage paths from SQLite alone?

The result of this phase will be used to implement `ZoteroSQLiteReader` and the first schema adapter. **Do not implement the production importer before this report has been reviewed.**

---

## Safety constraints

The test program is intentionally conservative:

- opens source `zotero.sqlite` with SQLite URI `mode=ro`;
- immediately enables `PRAGMA query_only=ON`;
- never executes INSERT/UPDATE/DELETE, VACUUM, checkpoint, schema modification, or any write PRAGMA against Zotero;
- when `--snapshot` is requested, writes only a new database under `probe-output/` using SQLite Backup API;
- never copies a bare `zotero.sqlite` file as a substitute for a transactional snapshot;
- does not require Zotero Desktop or Zotero Local API;
- uses only the Python standard library.

`probe-output/` and `*.sqlite*` are ignored by Git so the Zotero database/snapshot cannot be accidentally committed through the normal workflow.

---

# Test procedure for the local AI

The local AI should execute this task from the Paperazzi repository root and **must not modify the Zotero database or Zotero data directory**.

## Step 0 — Identify the source database

Preferred explicit path:

```text
<ZOTERO_DATA_DIR>/zotero.sqlite
```

The common default desktop data directory is usually `~/Zotero`, but a custom Zotero data directory is fully supported. If uncertain, locate the actual file before executing the probe.

Do not use a manually copied database for this test; the point is to exercise read-only access to the real source.

## Step 1 — Run Paperazzi's self-tests

From the repository root:

```bash
python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 3 tests
OK
```

The tests verify that:

- the source connection rejects SQL writes;
- SQLite Backup API produces a readable independent snapshot;
- a Zotero-like fixture can be reconstructed into item/creator/PDF samples.

If these tests fail, stop and return the complete terminal output. Do not alter Zotero in an attempt to fix the test.

## Step 2 — Probe with Zotero CLOSED

Close Zotero Desktop completely, then run:

```bash
python scripts/probe_zotero.py --db "<FULL_PATH_TO_ZOTERO.SQLITE>" --snapshot --quick-check --label zotero-closed
```

The command creates a timestamped directory similar to:

```text
probe-output/
└── 20260816-213500-zotero-closed/
    ├── REPORT.md
    ├── report.json
    └── zotero_snapshot.sqlite
```

Expected properties:

- command exits with code 0;
- `query_only = 1`;
- `quick_check = ["ok"]`;
- snapshot creation succeeds;
- important Zotero tables/views are identified;
- counts for items/creators/attachments are plausible;
- recent bibliographic samples contain the expected titles and ordered creator lists;
- imported-PDF samples resolve to `storage/<attachment-key>/<filename>` and normally report `exists=True`.

Do **not** delete or edit anything if an attachment reports `exists=False`; simply preserve the report for diagnosis.

## Step 3 — Probe with Zotero OPEN

Start Zotero normally and leave it open. It is acceptable to browse the library during this test, but avoid intentionally making a large batch edit while the snapshot is being created.

Run:

```bash
python scripts/probe_zotero.py --db "<FULL_PATH_TO_ZOTERO.SQLITE>" --snapshot --quick-check --label zotero-open
```

This is a deliberate concurrency test. Depending on Zotero/SQLite state, `zotero.sqlite-wal` and `zotero.sqlite-shm` may or may not exist. Their absence is not a failure.

Expected result: the probe and snapshot still succeed without requiring the Zotero process to stop.

---

# What the probe records

## A. Runtime and source state

- OS/platform;
- Python version;
- SQLite library version used by Python;
- source database size and mtime;
- presence/size/mtime of `-wal`, `-shm`, `-journal` sidecars;
- whether the analysis used the source directly or a generated snapshot.

## B. SQLite/Zotero identity

Read-only PRAGMAs:

- `user_version`;
- `application_id`;
- `schema_version`;
- `data_version`;
- `journal_mode`;
- `page_count` / `page_size`;
- `query_only`;
- optional `quick_check`.

The program also records the Zotero `version` table when present.

## C. Schema map

For every table/view:

- object name and type;
- columns and declared SQLite types;
- foreign-key declarations when available.

A SHA-256 schema fingerprint is calculated from this structural description. This will later be used by Paperazzi's `schema_probe.py` to select a compatible adapter or refuse an unknown Zotero layout.

## D. Key table populations

The probe specifically checks/counts objects relevant to the first importer:

```text
items
itemTypes
itemData
itemDataValues
fields / fieldsCombined
creators
itemCreators
creatorTypes
itemAttachments
collections
collectionItems
tags
itemTags
deletedItems
libraries
version
fulltextItems
annotations
```

Missing objects are reported by absence rather than treated as proof of corruption; the purpose of this phase is to discover the real schema.

## E. Semantic joins

The probe attempts read-only joins for:

- counts by Zotero item type;
- counts by creator role/type;
- attachment counts by link mode/content type;
- item counts by library;
- several recently modified bibliographic items;
- creator ordering and creator type on those items;
- sample PDF attachments and filesystem resolution.

These are precisely the minimum joins needed before implementing `CanonicalZoteroItem`.

---

# What the local AI should return

Return the following files from **both** runs:

```text
zotero-closed/REPORT.md
zotero-closed/report.json
zotero-open/REPORT.md
zotero-open/report.json
```

Also return the terminal output from:

```text
python -m unittest discover -s tests -v
```

and the final console output of each probe command.

### Do not return

```text
zotero.sqlite
zotero.sqlite-wal
zotero.sqlite-shm
zotero_snapshot.sqlite
PDF files
```

The Markdown/JSON reports contain enough structural information for the next implementation step.

The reports intentionally contain a small sample of paper titles, creator names and attachment paths because this lets us verify that semantic reconstruction is correct. If those should not leave the local machine, run with `--no-content-samples`; however, the first Paperazzi development run should preferably keep the samples because this is a private repository/workflow and they are diagnostically useful.

---

# Local AI completion summary

After execution, the local AI should provide a concise summary in this form:

```text
Paperazzi Phase-1 probe

Self-tests: PASS / FAIL
Zotero source path: ...
Python: ...
SQLite: ...

Closed run:
- snapshot: PASS / FAIL
- quick_check: ...
- journal_mode: ...
- WAL/SHM present: ...
- schema fingerprint: ...
- items: ...
- creators: ...
- itemCreators: ...
- attachments: ...
- sampled stored PDFs existing: X/Y

Open run:
- snapshot: PASS / FAIL
- quick_check: ...
- journal_mode: ...
- WAL/SHM present: ...
- schema fingerprint: ...
- key count differences from closed run: ...

Warnings/errors:
- ...
```

Do not speculate about schema fixes. Preserve the evidence and return it; the next Paperazzi development step will turn the observed schema into a formal adapter.

---

# Acceptance criteria for Phase 1

Phase 1 passes when all of the following hold:

1. unit tests pass;
2. the real source is opened without write access;
3. closed-Zotero snapshot succeeds;
4. open-Zotero snapshot succeeds, or any failure is understood sufficiently to design a safe fallback;
5. `quick_check` reports `ok` on each generated analysis snapshot;
6. key Zotero schema objects/columns are captured;
7. recent article title + ordered author reconstruction is demonstrably correct on samples;
8. imported-PDF storage resolution is demonstrably correct on samples;
9. no Zotero source file is modified by Paperazzi.

Only after these criteria are reviewed should Phase 2 implement the production SQLite reader and canonical item model.
