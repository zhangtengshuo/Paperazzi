# Phase 1 — Probe execution results

Execution date: 2026-08-16. Procedure: [`ZOTERO_SQLITE_PROBE.md`](ZOTERO_SQLITE_PROBE.md).

## Environment

- Host: Zotero Desktop on Windows 11, data directory `D:\zotero` (reachable from
  WSL2 as `/mnt/d/zotero`); source database `/mnt/d/zotero/zotero.sqlite` (128 MB,
  2448 `storage/` attachment directories).
- Probe host: WSL2 Ubuntu, Python 3.13.9, SQLite 3.51.0, standard library only.

## Self-tests (Step 1)

`python -m unittest discover -s tests -v` → **Ran 3 tests, OK** (read-only connection
rejects writes; Backup API snapshot is independent and readable; fixture
item/creator/PDF reconstruction is correct). One harmless `DeprecationWarning`
for `sqlite3.version` under Python 3.13.

## Run 1 — Zotero OPEN (label `zotero-open`, 2026-08-16 21:56)

Verified before the run that three `zotero.exe` processes were active.

- Snapshot via Backup API: **PASS** (exit 0), `quick_check = ["ok"]`, `query_only = 1`.
- Sidecars: `-journal` present (1.5 MB); **no `-wal`/`-shm`** — this database runs in
  `journal_mode = delete`, so the WAL concurrency scenario does not apply here.
- Schema fingerprint `7740b572…c8ecd10`, 61 tables/views.
- Counts: items 5711 (library 1: 5673, library 2: 38), creators 7619,
  itemCreators 12518, attachments 2628, collections 121, tags 727.
- PDF samples: **20/20 exist** at `storage/<attachment-key>/…`.
- Recent-item reconstruction (title + ordered creators) correct on samples.

## Run 2 — Zotero CLOSED (label `zotero-closed`, 2026-08-16 22:00)

Verified before the run that no `zotero.exe` process remained.

- Snapshot: **PASS** (exit 0), `quick_check = ["ok"]`.
- Sidecars: none — the `-journal` disappeared with the clean shutdown, as expected
  for `journal_mode = delete`.
- Schema fingerprint identical to Run 1 (schema unchanged).
- Counts: items 5714, creators 7621, itemCreators 12522, attachments 2630.
- PDF samples: **18/20 exist** (see findings).

## Between-run differences

The closed run reports slightly **more** data than the open run (+3 items, +4
itemCreators, +2 attachments, +11 itemData, +1 collectionItems). This is not a probe
artifact: the source database mtime moved from 2026-08-13 23:47 to 2026-08-16 21:58
local time, i.e. Zotero itself imported a new item (itemID 5712, King et al. 2024,
"Bridging the Gap Between Molecules and Materials in Quantum Chemistry with Localized
Active Spaces", +2 attachments) between the two runs. The schema fingerprint is
unchanged, confirming structure-only stability.

## Findings

1. **`journal_mode = delete`, not WAL.** Snapshots succeed against the live database
   with no `-wal`/`-shm` handling required. The Backup API approach is validated for
   both Zotero-open and Zotero-closed states on this machine.
2. **Annotation-table naming correction.** The probe's key-object list checked for an
   `annotations` table, which does not exist, but the real schema does contain Zotero's
   `itemAnnotations` table. The earlier "annotations absent" wording was therefore a
   probe naming oversight, not a schema limitation. It does not affect Phase 1
   acceptance because annotation contents were outside the bibliographic reconstruction
   test.
3. **Two PDF attachments report `exists=false`** — both belong to the freshly imported
   item 5712 (metadata synced, attachment files not yet downloaded to `storage/`).
   Preserved as evidence per procedure; importer design must tolerate attachments
   whose files are not on disk yet.
4. **Reconstruction verified**: recent items show correct titles and `orderIndex`-sorted
   creators (e.g. itemID 5699 → King; Stanton; Kim; …), and stored-PDF paths resolve
   to `storage/<key>/<filename>`.
5. **Source integrity**: during the open run the source mtime was still 2026-08-13,
   proving the probe performed zero writes; the later mtime change was Zotero's own
   import. No Zotero file was modified by Paperazzi.

## Acceptance criteria (all PASS)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Unit tests pass | PASS (3/3) |
| 2 | Real source opened without write access | PASS (`mode=ro` + `query_only=1`) |
| 3 | Closed-Zotero snapshot succeeds | PASS |
| 4 | Open-Zotero snapshot succeeds | PASS |
| 5 | `quick_check` = ok on each snapshot | PASS (both runs) |
| 6 | Key schema objects/columns captured | PASS (61 objects, stable fingerprint) |
| 7 | Title + ordered-author reconstruction correct | PASS (samples verified) |
| 8 | Imported-PDF storage resolution correct | PASS (38/40 files on disk; 2 pending sync) |
| 9 | No Zotero source file modified | PASS |

**Phase 1 is accepted.** Phase 2 (production `ZoteroSQLiteReader` and canonical item
model) may start against the observed schema.

## Artifacts

Raw reports for both runs are committed under [`runs/`](runs/):

- `runs/20260816-215601-zotero-open/` — `REPORT.md`, `report.json`
- `runs/20260816-220013-zotero-closed/` — `REPORT.md`, `report.json`

SQLite snapshots (`zotero_snapshot.sqlite`) stay local under the git-ignored
`probe-output/` directory and are intentionally not committed.
