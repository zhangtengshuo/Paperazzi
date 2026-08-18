# Local AI Task Contract — WoS CR Reconciliation After Schema v3

Read first:

- root `AGENTS.md`
- `docs/wos/WOS_IMPORT_MERGE_POLICY.md`
- `docs/architecture/WOS_BACKGROUND_CORPUS.md`

## Mission

Upgrade the existing local WoS corpus to schema v3, re-observe retained source exports, and measure cited-reference completeness without rebuilding or discarding the corpus.

The existing canonical WoS database may already contain useful references. Preserve them.

## Rules

- Work on existing `main`; no branch and no PR.
- Use micromamba environment `Paperazzi` only.
- Do not modify Zotero or source PDFs.
- Do not edit WoS export text files.
- Repeated `UT` is expected and must be merged, not rejected.
- A later export with missing `CR` must never erase earlier canonical references.
- `NR>0` with no `CR` is `MISSING_FROM_EXPORT`, not a zero-reference paper.
- CR incompleteness is not a Paperazzi-wide failure condition.

## Execution

### 1. Preflight and tests

```bash
git branch --show-current
git status --short
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
micromamba run -n Paperazzi python -m unittest discover -s tests -p "test_wos_*.py" -v
```

Stop on implementation-test failure and report the exact traceback.

### 2. Upgrade the independent WoS DB

Any v3 command initializes/migrates the independent DB in place:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 stats
```

Verify that the corpus record count does not unexpectedly decrease.

### 3. Re-import retained historical exports

Re-import the unchanged source exports retained under:

```text
imports/wos/done/
```

Use the importer normally. Do not pre-deduplicate by UT. Existing UTs should report as `updated_count` / `merged_count` rather than creating duplicate canonical records.

If `imports/wos/new/` also contains genuinely new exports, process them after the historical reconciliation pass.

### 4. Verify merge invariants

Check concrete repeated UT examples in both directions:

1. complete CR observed earlier, missing CR observed later -> canonical references remain;
2. missing CR observed earlier, complete CR observed later -> canonical references are added and status improves;
3. later observation lacks an abstract/keyword/funding/RP field -> existing non-empty canonical information remains;
4. later observation contributes new metadata -> it appears in the merged canonical record.

### 5. Measure CR completeness

Run:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 stats
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 cr-gaps --limit 500
```

Inspect representative histories with:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 observations WOS:XXXXXXXXXXXXXXX
```

Report counts for:

```text
record_observations
records_cr_complete
records_cr_missing
records_cr_partial_or_unverified
cited_references
resolved_citation_edges
```

Also report import-level counts of:

```text
cr_complete_count
cr_complete_zero_count
cr_missing_from_export_count
cr_partial_count
cr_present_unverified_count
cr_unknown_count
```

### 6. Preserve ordinary Paperazzi use

Do not require CR completion before WoS metadata can be linked to Zotero/Paperazzi. The record can still supply authors, RP, keywords, affiliations, funding, abstract and other fields while its CR status remains incomplete.

## Final report

Return:

- test and migration result;
- corpus counts before/after reconciliation;
- number of repeated UTs merged;
- CR quality counts;
- at least three concrete missing-CR observations where `NR>0`;
- at least one complementary re-import example if available;
- any implementation defect discovered;
- top CR gaps worth attempting to re-export later.

Do not claim all cited references are complete merely because the database contains many CR rows.
