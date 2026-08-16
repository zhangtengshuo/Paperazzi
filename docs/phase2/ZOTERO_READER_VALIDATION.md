# Phase 2 — Production ZoteroSQLiteReader validation

## Objective

Phase 1 proved that Paperazzi can safely snapshot and inspect the real Zotero database.
Phase 2 validates the first **production mapping layer**:

```text
zotero.sqlite (read-only)
        ↓
transaction-consistent snapshot
        ↓
userdata125-global42 schema adapter
        ↓
ZoteroSQLiteReader
        ↓
CanonicalZoteroItem
```

The goal is not yet to populate `paperazzi.sqlite3`. We first require a deterministic,
fully reconstructable Zotero-side canonical corpus.

## Important correction from Phase 1

The Phase 1 summary stated that an `annotations` table was absent. The real schema
actually contains `itemAnnotations`; the probe looked for the wrong object name.
This does not affect Phase 1 acceptance because annotations were not required by the
bibliographic reconstruction test. Phase 2 deliberately treats notes/annotations as
optional child-domain data and excludes item types `attachment`, `note`, and
`annotation` from the bibliographic parent corpus.

## Validated schema target

The first adapter is intentionally explicit:

```text
version.userdata     = 125
version.globalSchema = 42
observed full schema fingerprint:
7740b572c59e3caa976528b24edf074382add503730a5898aec732de9c8ecd10
```

Paperazzi validates the exact tables/columns used by the reader. If Zotero upgrades
the internal schema version, the reader refuses to guess and requests a new probe +
adapter validation.

## Canonical identity rule

The Phase 1 database contains both a user library and a group library. Therefore a
Zotero item is identified as:

```text
(libraryID, itemKey)
```

and represented as:

```text
zotero:<libraryID>:<itemKey>
```

`itemID` is retained only as a local diagnostic/internal join key. It is deliberately
excluded from the canonical content hash.

## Attachment modes

The reader uses Zotero's own attachment link-mode semantics:

```text
0 imported_file
1 imported_url
2 linked_file
3 linked_url
4 embedded_image
```

Any path beginning with `storage:` is resolved directly as:

```text
<ZOTERO_DATA_DIR>/storage/<ATTACHMENT_KEY>/<relative path>
```

A linked-file path beginning with `attachments:` is **not guessed**. It is reported as
`linked-base-directory-required`; a later configuration layer will supply Zotero's
linked attachment base directory if the real library requires it.

---

# Procedure for the local AI

Run from the Paperazzi repository root.

## Step 1 — Pull and run all unit tests

```bash
python -m unittest discover -s tests -v
```

Expected: the original Phase 1 tests plus the new reader tests all pass.

The new tests verify:

- userdata 125 / globalSchema 42 adapter selection;
- unknown schema rejection;
- fields → canonical field names;
- ordered creators and creator types;
- nested collection key reconstruction;
- tags;
- imported PDF path resolution;
- deleted item filtering/recovery;
- identical Zotero item keys in different libraries remain distinct;
- canonical hash ignores SQLite-internal `itemID`;
- linked attachment base-directory paths are not guessed.

If any test fails, stop and return the complete test output before modifying the real
Zotero data or weakening a validation rule.

## Step 2 — Run the production reader against the real library

On the already tested WSL2 setup:

```bash
python scripts/validate_zotero_reader.py \
  --db /mnt/d/zotero/zotero.sqlite \
  --data-dir /mnt/d/zotero \
  --label real-library
```

The command always creates a new Paperazzi-owned SQLite snapshot first. It then maps
the **entire** bibliographic corpus, not just a sample.

Output:

```text
phase2-output/<timestamp>-real-library/
├── READER_REPORT.md
├── reader_report.json
└── zotero_snapshot.sqlite
```

Never commit `zotero_snapshot.sqlite`.

## Step 3 — Inspect the report

Check at minimum:

1. Adapter is `userdata125-global42`.
2. Both library 1 (user) and library 2 (group) are represented when they contain
   bibliographic parents.
3. `journalArticle` count is plausible relative to Phase 1's 2430 raw journalArticle
   records; deleted records may reduce the active count.
4. Recent samples have correct title and creator order.
5. DOI values look like actual DOI metadata rather than some unrelated field mapping.
6. Collections and tags look correct on samples where they exist.
7. Stored PDFs report `zotero-storage` and correct local existence state.
8. The two recently synced-but-not-downloaded PDFs from Phase 1 may still report
   `local_exists=false`; that is valid state, not reader failure.
9. Record any `linked_file`, `unknown_*`, or `nonstandard-imported-path` attachment
   modes. These determine whether the attachment resolver needs another adapter before
   the web UI is built.
10. Record the counts of active items with no title or no creators. Do **not** assume
    every such record is corrupt; inspect item types first.

## Step 4 — Manual spot checks

For at least five recent records, compare Zotero Desktop with `reader_report.json`:

- title;
- item type;
- author order;
- DOI when present;
- collection membership;
- tags;
- PDF attachment filename/existence.

Also spot-check at least one group-library item if a bibliographic group item exists.

## Step 5 — Commit only the diagnostic reports

Copy:

```text
READER_REPORT.md
reader_report.json
```

into:

```text
docs/phase2/runs/<timestamp>-real-library/
```

and commit them with a message such as:

```text
Record Phase 2 Zotero reader validation results
```

Do not copy or commit the SQLite snapshot, Zotero database, PDFs, or storage files.

---

# Acceptance criteria

Phase 2 passes when:

- all unit tests pass;
- schema adapter validates the real snapshot without weakening its contract;
- the complete bibliographic corpus maps without exceptions;
- `(libraryID, itemKey)` identities are unique;
- recent title/creator reconstruction is manually correct;
- deletion filtering is plausible;
- attachment resolution states explain all observed attachment modes;
- missing files are represented as data state rather than causing crashes;
- no source Zotero file is modified.

After Phase 2 acceptance, development moves to **Phase 3: scan manifests, deterministic
content hashes, NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED diff, and the first
`paperazzi.sqlite3` persistence schema**.
