# Phase 3 — Persistence validation report

Run: `20260817-034335-phase3` (real-library validation per `PHASE3_IMPLEMENTATION.md` §3D).

## Status

```text
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

## Milestones (each committed separately)

```text
9494786  Phase 3A: SQLAlchemy/Alembic persistence foundation
         (16 tables, 13 indexes, dual migrations 0001/0002, all constraints live)
d11c2fc  Phase 3B: split hashes and Zotero scan/diff persistence
         (bibliographic/organization/attachment/canonical hashes, ItemChange,
          persist_zotero_scan with NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED)
2768216  Phase 3C: document extraction and evidence persistence
         (extraction runs/attempts 1..3, evidence spans, reference sections/entries/
          identifiers, text-channel provenance, accept/supersede semantics)
```

Unit tests: **39 passed / 0 failed** (gate tests per milestone + full suite).

## Real-library validation (Phase 3D)

Fresh ignored DB `data/phase3-validation/paperazzi.sqlite3`; read-only Zotero snapshot
`zotero_snapshot.sqlite` created via Backup API. Migration head
`0002_document_evidence_references`.

### Full Zotero scan ×2

```text
first scan : NEW 2513, MODIFIED 0, UNCHANGED 0, REMOVED 0, RESTORED 0
second scan: NEW 0, MODIFIED 0, UNCHANGED 2513, REMOVED 0, RESTORED 0
```

The second scan is entirely UNCHANGED: no duplicate papers, no new item-version rows
(2513 versions after scan 1, still 2513 after scan 2), no DOI/title deduplication
(2513 papers for 2513 Zotero items).

### Database contents

```text
full_zotero_item_count        2513
paper_count                   2513
creator_mention_count         12381
pdf_document_count            2567   (one per PDF attachment record, incl. absent files)
local_pdf_available_count     2175   (matches Phase 2/2.5 availability)
duplicate identities          0
foreign_key_check rows        0      (PRAGMA foreign_keys=ON enforced by engine)
```

### 200-PDF deterministic extraction sample

```text
selected_documents            200
extraction_run_count          200   (one run per available sampled PDF)
attempt_count                 200   (all Attempt 1; AI review not needed for these)
evidence_span_count           393
reference_section_count       153
reference_entry_count         7363
reference_identifier_count    8518  (DOI + YEAR rows)
```

Counts match the frozen-v3 200-doc run exactly (153 sections / 7363 entries).

### Anchor checks (persisted state, queried back from the DB)

```text
QuTiP-BoFiN  (I97Q72KK): implicit-numbered-punctuated HIGH ACCEPTED
                         text_channel=PYMUPDF_CONTENT_STREAM  p15-17  78 entries
Rota 1964    (MD8N7CDD): raw-author-year-or-unsegmented MEDIUM ACCEPTED
                         text_channel=PYMUPDF_SORTED         p26-28   0 entries (raw)
Soriano 2014 (QRV8DDP9): implicit-numbered-punctuated HIGH ACCEPTED
                         text_channel=PYMUPDF_CONTENT_STREAM p9-10   47 entries
JACS footnote (J99X9MWN): implicit-numbered-parenthesized HIGH ACCEPTED
                         text_channel=PYMUPDF_CONTENT_STREAM p1-2     9 entries
Nature-style (87JCS8EY): numbered-punctuated HIGH ACCEPTED
                         text_channel=PYMUPDF_SORTED         p29-31  64 entries
```

Text-channel provenance is persisted and correct for every anchor (content-stream
for the two-column recoveries, sorted for the single-column headings).

### Idempotency

Re-running extraction-trigger decisions over 20 sampled documents created **no new
extraction runs**; repeated full scans create no duplicate papers/versions.

### Failure injection

Duplicate-identity scan on a fresh temporary DB: scan FAILED, run row marked FAILED,
**zero** papers rows persisted — the projection transaction rolled back cleanly and
prior accepted data remained untouched.

## Acceptance criteria (all met)

1. migrations reproducible on fresh DB ✔ (alembic upgrade head; downgrade/upgrade roundtrip tested)
2. foreign keys/check constraints enforced ✔
3. split hashes behave exactly by dimension ✔ (3B gate tests)
4. repeated unchanged real scan idempotent ✔ (second scan 100% UNCHANGED)
5. REMOVED/RESTORED preserve Paperazzi identity ✔ (synthetic lifecycle test, same paper_id)
6. local PDF availability independent from bibliographic change detection ✔ (paper_documents; trigger rules)
7. multiple extraction cycles keep bounded attempt history ✔ (UNIQUE(run,attempt); new run restarts at 1)
8. text-channel provenance persisted ✔ (all 5 anchors + every section row)
9. structural confidence vs entry-text quality distinct ✔ (section vs attempt fields)
10. raw references/evidence survive without semantic matching ✔ (Rota raw section persisted, 0 entries)
11. failed transactions roll back cleanly ✔ (injection)
12. no Phase 4 author/citation identity assumptions ✔ (paper_creator_mentions; matches table empty)

## Artifacts

- `docs/phase3/runs/20260817-034335-phase3/phase3_report.json` (schema-validated)
- Runtime DB/snapshot kept under git-ignored `data/` — not committed.
