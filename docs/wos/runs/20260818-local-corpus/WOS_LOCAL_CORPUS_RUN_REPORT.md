# WoS Local Corpus Run Report

Date: 2026-08-18  
Branch: `main`  
Status: **completed with conservative coverage and two implementation fixes**

This run used the user-provided Clarivate Plain Text exports as read-only input. It did not automate Web of Science access. The independent WoS database was written to `data/wos.sqlite3`; Paperazzi integration state was written to the existing 2,513-paper validation database at `data/phase5-validation/phase5_5/paperazzi-phase5_5.sqlite3`. The empty placeholder `data/paperazzi.sqlite3` was not used.

## Environment and regression gates

- Paperazzi environment check: **PASS** (`Paperazzi`, Python 3.13, constrained package set matched).
- WoS tests after fixes: **18/18 PASS**.
- Migration tests after updating the current head contract: **4/4 PASS**.
- Full regression suite: **173/173 PASS**.
- Paperazzi migration: `0007_similar_author_review_queue` → `0010_paper_wos_match_state`.
- Web service: **PASS** on `/health`, WoS statistics, coverage, matched-paper, unmatched-paper, and WoS-record endpoints.

## Imported WoS corpus

At the time of this run, the input location was `imports/incoming/wos/`. The
workspace has since been reorganized into the following local staging layout:

```text
imports/wos/
├── new/   # newly staged WoS exports awaiting import
└── done/  # exports already used/processed by the local corpus workflow
```

The `done/` directory currently contains **13** `savedrecs` exports, which are
the source files represented by the initial run below. The `new/` directory
contains **3** subsequently staged exports (`cui.txt`, `roland.txt`, and
`roos.txt`); these were imported in the follow-up cycle documented below, but
the original text files remain in place as read-only staging inputs.

The exports contained 1,507 tagged records. **1,485** had a stable WoS accession (`UT`) and were stored. **22** records had no `UT` (mostly `DT=CITED-REFERENCE` artifacts) and were skipped with an explicit count; they cannot be stored in the UT-keyed Full Record corpus.

Final corpus statistics:

| Metric | Count |
|---|---:|
| WoS records | 1,485 |
| WoS authors | 8,271 |
| corresponding-author members | 2,308 |
| cited references | 77,606 |
| resolved local citation edges | 29,915 |
| import batches recorded | 38 |

The 38 batches reflect the initial overlapping import, the successful full re-import after the UT-less-record fix, and the DOI-normalization repair re-import. Re-importing by `UT` remained idempotent: the final repair pass created no new records and only updated existing records.

### Follow-up import from `imports/wos/new/`

The three subsequently staged files were imported into the same independent
WoS database as batches **39–41**:

| File | Parsed records | New records | Updated records | Skipped without UT |
|---|---:|---:|---:|---:|
| `cui.txt` | 226 | 223 | 3 | 0 |
| `roland.txt` | 164 | 140 | 24 | 0 |
| `roos.txt` | 27 | 20 | 7 | 0 |
| **Total** | **417** | **383** | **34** | **0** |

The current database therefore contains **1,868** unique WoS records,
**10,489** authors, **2,933** corresponding-author members, **92,142** cited
references, and **31,080** resolved local citation edges. The 34 updates include
overlap with records imported earlier in this cycle; no duplicate `UT` records
were created.

## Paperazzi ↔ WoS matching

The final conservative run classified all **2,513** active Paperazzi papers:

| State | Count |
|---|---:|
| `WOS_MATCHED` | 554 |
| `WOS_MATCH_AMBIGUOUS` | 2 |
| `WOS_NOT_IN_LOCAL_CORPUS` | 1,957 |
| `WOS_NOT_CHECKED` | 0 |

Accepted local coverage is **554 / 2,513 = 22.05%**. This describes the current imported local corpus; it does not claim that the remaining papers are absent from Web of Science.

Match methods among the 554 accepted links:

- `DOI_EXACT`: **540**
- `TITLE_EXACT`: **14**
- no fuzzy promotion was used.

The two ambiguous records were intentionally not accepted:

- Paperazzi `177`, title `Singlet Fission`, is from 2010; the one exact-title WoS candidate is from 2018.
- Paperazzi `1668`, a 2021 arXiv record, has a one-title candidate from 2022 in the Journal of Physical Chemistry Letters.

The first dry run incorrectly reported 556 matches because the DOI parser truncated legacy DOI strings containing angle brackets and semicolons. Paperazzi `47` was temporarily shown as linked to an unrelated Favaro record. The parser now preserves the complete legacy DOI, the corrected dry run reports 554 matches, and the stale false links were superseded during the corrected apply pass.

### Follow-up matching dry run after batches 39–41

The new WoS corpus was matched against the same 2,513-paper validation database
without applying any Paperazzi-side state changes:

| State | Count |
|---|---:|
| `WOS_MATCHED` | 589 |
| `WOS_MATCH_AMBIGUOUS` | 3 |
| `WOS_NOT_IN_LOCAL_CORPUS` | 1,921 |
| `WOS_NOT_CHECKED` | 0 |

The new total is **589 / 2,513 = 23.44%**, an increase of **35 newly matched
Zotero papers** over the initial 554. The accepted-match dry-run methods are
**574 DOI-exact** and **15 title-exact**. Of the 413 unique `UT`s in the three
new files, 39 correspond to matched Zotero papers; 4 were already accepted
before this import, so the net new coverage is 35 papers.

This was a dry run only: `paper_wos_links` and `paper_wos_match_state` were not
updated. The unmatched output was written to the local generated file
`tmp/wos-runs/wos-unmatched-after-new-20260818.jsonl`.

## Semantic and browser spot checks

- `WOS:000383410700048`, *Singlet Fission via an Excimer-Like Intermediate in 3,6-Bis(thiophen-2-yl)diketopyrrolopyrrole Derivatives*: the RP group `Schatz, GC; Marks, TJ; Wasielewski, MR (corresponding author)` preserved all three group members.
- Paperazzi `96`: DOI-exact match with complete author mapping; effective correspondence source is `WOS_RP`, and the displayed corresponding author is `Long Wang`.
- Across all 554 accepted links: **527** had complete `WOS_RP` mapping, **11** had partial safe mapping with fallback provenance, and **16** remained unresolved for presentation mapping.
- Paperazzi `47`: now correctly shows `WOS_NOT_IN_LOCAL_CORPUS`; it no longer displays the unrelated WoS record caused by the truncated legacy DOI.
- The browser displays a WoS Corpus page, WoS statistics, coverage state, structured WoS metadata before the PDF fallback block, and a plain-language “no local WoS record” state for unmatched papers.
- The service remained healthy with WoS available and normal Paperazzi behavior preserved for papers without a local WoS match.

## Citation frontier and next manual WoS searches

The generated expansion plan is `tmp/wos-runs/wos-expansion-plan.json`. The strongest residual themes were fluorescent proteins/carotenoid proteins, singlet fission, configuration interaction/active space, density-functional theory, charge transfer, intersystem crossing, CO2 reduction, DNA/proton transfer, and photodynamic therapy. The most frequent residual venues included JCTC, JACS, JCP, PCCP, Chemical Physics Letters, and Journal of Physical Chemistry A/B.

Recommended next broad, human-triggered WoS searches are:

1. `TS=("fluorescent protein" OR "carotenoid protein" OR "orange carotenoid")`
2. `TS=("singlet fission" OR "triplet pair" OR multiexciton)`
3. `TS=("configuration interaction" OR "active space" OR "density functional")`
4. `TS=("charge transfer" OR "intersystem crossing" OR ultrafast)`
5. `TS=("photocatalytic CO2" OR "CO2 reduction")`
6. `TS=(DNA AND ("proton transfer" OR "electron transfer"))`
7. Author-led broad searches for `Björn O. Roos`, `Roland Lindh`, `Ganglong Cui`, `Teng-Shuo Zhang`, and `Michael R. Wasielewski`.
8. Venue-plus-topic searches in JCTC/JCP/JACS/PCCP for the residual theory and singlet-fission clusters.

These are search suggestions, not automatic matching truth. The next export should remain Full Record + Cited References and may overlap this corpus.

## Problems and fixes

### UT-less WoS export records

The first import stopped on 22 records without `UT`. They were export artifacts that cannot be keyed in the independent WoS schema. The parser now skips them, returns `raw_record_count` and `skipped_without_ut`, and retains the strict UT requirement for stored records. Regression coverage was added.

### Legacy DOI truncation

The original DOI regular expression excluded `<`, `>`, and `;`, which truncated older WoS DOI forms and could create a false DOI match. The regex now captures the complete non-whitespace DOI token and strips only terminal punctuation. A regression test covers the legacy form `10.1562/0031-8655(2000)072<0632:PBOSAN>2.0.CO;2`.

### Migration test contract

An existing Phase 4 test hard-coded migration `0008` as the current head. The WoS implementation extends the head to `0010`; the test now asserts `0010_paper_wos_match_state` and verifies the WoS bridge tables.

### CLI packaging note

The documented `paperazzi-wos` executable was not present in the environment, although the Python module entry point worked. The run used the equivalent `python -m paperazzi.wos.cli` invocation. This is a packaging/usability issue to repair separately; it did not affect parsing or corpus correctness.

## Data boundary

- WoS source exports are now organized under local `imports/wos/new/` and
  `imports/wos/done/`; the 13 files in `done/` are the inputs for the initial
  run, and the 3 files retained in `new/` were imported in follow-up batches
  39–41 without modifying their contents.
- `data/wos.sqlite3` and the selected validation database are local runtime state;
  historical validation artifacts and WoS matching outputs are kept under
  `tmp/` and were not committed.
- No Zotero database, Zotero storage, or PDF file was modified.
- No ambiguous match was promoted automatically.
