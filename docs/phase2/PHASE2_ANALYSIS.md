# Phase 2 validation analysis

Date: 2026-08-16

## Status

**Phase 2 is technically successful at the corpus-mapping level, but acceptance is temporarily held for one reader correction and one focused rerun.**

The first full-library run demonstrates that the production reader can map the complete bibliographic corpus on the real Zotero database without exceptions. The observed schema remains `userdata=125 / globalSchema=42`, both user and group libraries are represented, and the canonical layer reconstructs titles, creators, collections, tags, DOI fields, deleted bibliographic records, and attachment metadata across the full library.

## Results from the first full-library run

- active bibliographic items: 2513
- deleted bibliographic items retained for audit: 43
- user-library active bibliographic items: 2494
- group-library active bibliographic items: 19
- active journal articles: 2388
- journal articles with DOI: 2293
- journal articles with creators: 2380
- active items missing title: 0
- active items without creators: 18
- attachment records attached to active bibliographic items: 2567 before the deleted-attachment correction
- local attachment files found: 2175
- local attachment files reported missing: 213
- unresolved/not-applicable local files: 179, all corresponding to URL-only attachment semantics in the first report

These numbers are internally plausible relative to the Phase 1 raw Zotero counts. In particular, the decrease from 2430 raw `journalArticle` rows to 2388 active journal articles is consistent with deleted bibliographic records being retained separately rather than treated as active corpus entries.

## Important reader issue discovered during review

The first Phase 2 reader query loaded child attachments using `itemAttachments` and `items`, but did not exclude attachment items that themselves appear in `deletedItems`.

This is semantically incorrect. A common Zotero operation is:

1. a bibliographic parent remains active;
2. an old PDF attachment is deleted;
3. another attachment may replace it;
4. the deleted attachment row can still be retained by Zotero for sync/deletion bookkeeping.

Without filtering child attachments through `deletedItems`, Paperazzi can accidentally reattach a deleted PDF to an active paper. Such rows can also inflate the apparent `missing local file` count after Zotero has removed the physical file.

The adapter has therefore been corrected so canonical items include only non-deleted child attachments. A regression test now creates an active parent with one live PDF and one deleted PDF and asserts that only the live attachment survives canonical reconstruction.

## Missing local files: interpretation

The original report counted 213 `storage:` attachments whose resolved files were absent on disk. This should **not yet be interpreted as 213 broken Zotero records**.

The count can contain several states:

- attachment metadata synced but binary file not downloaded locally;
- attachment deliberately removed/deleted while its Zotero deletion bookkeeping remains;
- storage file genuinely missing;
- historical Zotero attachment state no longer represented by a live file.

After the deleted-attachment correction, the validator now reports the remaining missing files by:

- attachment link mode;
- MIME/content type;
- `syncState`;
- library;
- detailed attachment key and parent metadata.

This will let Phase 3 preserve a precise attachment availability state instead of collapsing everything into a generic error.

## Items without creators

There are 18 active bibliographic items without creators, including 8 journal articles in the first run.

This is not by itself evidence of a reader bug because Zotero stores creators exclusively through the `itemCreators` relationship used by the reader. However, before treating these as ordinary source-data gaps, the rerun now records title, item type, DOI, date, publication title and Zotero identity for every no-creator item. These records can then be spot-checked directly in Zotero.

For Paperazzi, missing creators must remain a valid ingestion state. Such papers cannot yet seed author identities until creator metadata is repaired locally or enriched from an external source.

## Canonical model decisions confirmed

The full-library run supports the following design choices:

1. Zotero identity is `(libraryID, itemKey)`, not `itemID` and not `itemKey` alone.
2. Deleted bibliographic items should be retained for audit/diff history but excluded from the active corpus.
3. Deleted child attachments must never be reintroduced into an active canonical paper.
4. Missing local PDF files are data states, not ingestion failures.
5. `version`, `synced`, `dateModified`, internal numeric IDs and other Zotero bookkeeping fields remain available for audit/fast-path checks but do not define the semantic content hash.
6. The canonical content layer is sufficiently stable to serve as the input to Phase 3 persistence and scan-to-scan diffing once the corrected rerun passes.

## Required focused rerun

Run the current repository version again using the same Phase 2 procedure:

```bash
python -m unittest discover -s tests -v
python scripts/validate_zotero_reader.py \
  --db /mnt/d/zotero/zotero.sqlite \
  --data-dir /mnt/d/zotero \
  --label real-library-v2
```

The rerun must confirm:

- all tests pass, including deleted-child-attachment filtering;
- `deleted_attachments_filtered` is reported;
- canonical attachment count/local-file statistics are recomputed after filtering;
- the 8 journal articles without creators are listed with identifying metadata;
- no unexpected `linked_file`, `unknown_*`, or `nonstandard-imported-path` states appear.

If these checks pass, Phase 2 should be accepted and implementation can proceed directly to Phase 3: `paperazzi.sqlite3`, scan manifests, semantic hashes and deterministic `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` diffing.
