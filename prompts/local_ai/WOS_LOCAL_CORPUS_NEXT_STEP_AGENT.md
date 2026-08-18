# Local AI Task Contract — First Real WoS Corpus Run

This task is the executable local-AI companion to:

`docs/wos/LOCAL_WOS_CORPUS_RUNBOOK.md`

Read that runbook and `docs/architecture/WOS_BACKGROUND_CORPUS.md` before doing any work.

Also obey the repository root `AGENTS.md`.

---

## Mission

Execute the first substantial real-data WoS background-corpus cycle on the user's local Paperazzi installation:

1. validate the local Paperazzi environment and WoS implementation;
2. migrate the Paperazzi database to the current schema;
3. import the user's manually exported WoS Plain Text / Full Record + Cited References files into the independent `data/wos.sqlite3`;
4. dry-run Paperazzi ↔ WoS matching;
5. inspect the result for correctness;
6. persist conservative match state if the dry run is credible;
7. validate WoS-first structured display and corresponding-author semantics;
8. generate a residual coverage / expansion report for the next manual WoS search round;
9. report actual corpus statistics, problems, and recommended broad searches.

The objective is **not** complete WoS coverage.

---

## Absolute constraints

- Work on the existing `main` branch. Never create a branch.
- Never create a pull request.
- Do not discard, reset, stash, overwrite, or rewrite unrelated user work.
- Use only the micromamba environment named `Paperazzi` for authoritative local execution.
- Do not modify Anaconda `base` or unrelated environments.
- Treat Zotero DB, Zotero storage, PDFs, and WoS export files as read-only source inputs.
- Do not automate Web of Science browser access. The user performs WoS searches and exports manually.
- Do not require all Zotero papers to have WoS records.
- Do not interpret `WOS_NOT_IN_LOCAL_CORPUS` as “not in Web of Science.”
- Do not promote ambiguous/fuzzy matches merely to increase coverage.
- Do not infer corresponding authors from `EM` alone.
- When a valid matched WoS record is available, its `RP` group semantics are the preferred structured correspondence source. Preserve PDF/Paperazzi role provenance separately.
- Do not alter the architecture to make a local run appear successful.

---

## Input discovery

Look for manually exported WoS Plain Text files in sensible local locations, especially:

```text
imports/incoming/wos/
imports/incoming/
data/
```

Do not scan the entire computer unnecessarily.

A valid source file should look like Clarivate tagged Plain Text and contain records with `PT ... ER`, normally including a stable `UT`.

If multiple plausible WoS text files exist, process the ones that clearly contain Full Record / Cited References data. Overlap is acceptable and expected.

If no real WoS export file is present, do not fabricate one and do not substitute synthetic fixtures for the real task. Run implementation tests, report that real import cannot proceed, and name the exact staging path the user should place exports into.

---

## Execution order

### A. Repository and environment preflight

Inspect:

```bash
git branch --show-current
git status --short
```

Do not modify unrelated dirty files.

Run:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

If the environment check fails, diagnose and repair only the `Paperazzi` environment when the repair is clearly scoped and safe. Do not touch unrelated environments.

### B. Targeted implementation tests

Run the WoS regression tests:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -p "test_wos_*.py" -v
```

Run migration tests as available.

Do not hide failures. If a WoS implementation test fails, fix the implementation on `main`, rerun the targeted tests, and report what changed.

### C. Database migration

Run the current Alembic upgrade against the real Paperazzi DB using the project's configured database path:

```bash
micromamba run -n Paperazzi alembic upgrade head
```

Verify that `paper_wos_links` and `paper_wos_match_state` exist afterward.

### D. Real WoS import

Import the discovered WoS Plain Text files into the independent WoS DB, normally:

```text
data/wos.sqlite3
```

Use the `paperazzi-wos` CLI. Preserve useful search provenance with `--label` and `--search-note` where it can be inferred from filenames or accompanying context; do not invent a detailed search query if it is unknown.

Heavy overlap across exports is normal. Use importer upsert behavior; do not pre-deduplicate files manually.

After all imports, run:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 stats
```

Capture actual counts.

### E. Corpus sanity checks

Inspect representative imported records. Confirm at least:

- title/DOI/UT retrieval works;
- authors are ordered correctly;
- RP group membership is correct;
- multiple corresponding-author cases are not reduced to only the name nearest `(corresponding author)`;
- repeated RP address groups do not create duplicate displayed people;
- CR rows were retained;
- internal citation targets are resolved only when DOI→UT is unique;
- keywords/classification/funding/abstract are present where the source record supplies them.

When known examples are present, explicitly verify:

```text
Xie, XY; Ma, HB (corresponding author)
```

as two corresponding authors.

### F. Dry-run matching

Run:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --unmatched-output data/wos-unmatched-dry-run.jsonl
```

Inspect summary counts and a sample of decisions before applying.

Review:

- DOI exact matches;
- title-based matches;
- ambiguous cases;
- no-local-record cases.

Look for false matches, not merely missed matches.

If matching looks suspicious, stop before `--apply`, diagnose with concrete examples, repair the matching rule conservatively, rerun tests, and repeat the dry run.

### G. Apply conservative matching

Only after the dry-run looks credible:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --apply \
  --unmatched-output data/wos-unmatched.jsonl
```

Re-run once to verify idempotence/stability: accepted links must not multiply.

### H. Web/API validation

Run the local web app or use the existing ASGI validation utilities.

Inspect representative matched and unmatched papers.

For a matched paper verify:

- WoS data is shown as structured primary scholarly metadata;
- WoS block precedes PDF fallback/audit in presentation;
- effective corresponding-author roles follow WoS RP when safe author mapping is complete;
- existing fallback roles remain available as source provenance;
- abstract, keywords, classifications, funding, identifiers/affiliations, citation counts, and references appear when present;
- CR targets distinguish local WoS / Paperazzi-Zotero / unresolved targets.

For an unmatched paper verify:

- the page still works normally;
- the UI says no local WoS record / not checked as appropriate;
- it never claims the paper is absent from Web of Science.

### I. Expansion planning

Generate:

```bash
micromamba run -n Paperazzi python scripts/plan_wos_expansion.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --limit 30 \
  --output data/wos-expansion-plan.json
```

Interpret, do not merely dump, the result.

Select the most useful residual clusters and recommend approximately 3–10 **broad human WoS searches** for the next export round. Favor queries that can recover many residual papers or a scientifically coherent neighboring corpus.

Do not convert the plan into automated WoS scraping.

---

## Required final report

Return a compact but data-rich report containing:

### 1. Environment

- current branch;
- whether unrelated local modifications existed;
- Paperazzi environment check result;
- migration result;
- targeted WoS test result.

### 2. Imported WoS corpus

For each import batch:

- filename;
- label/search note if used;
- record count;
- new count;
- updated count.

Corpus totals:

- records;
- authors;
- correspondence members;
- cited references;
- resolved citation edges;
- import batches.

### 3. Matching

- active Paperazzi/Zotero papers;
- matched;
- ambiguous;
- not in local corpus;
- not checked;
- coverage fraction;
- counts by match method, especially DOI exact vs title-based;
- any suspicious cases found.

### 4. Semantic spot checks

Report concrete examples for:

- multi-corresponding-author RP;
- title/DOI exact match;
- ambiguous/no-local record;
- local citation edge;
- unresolved citation-frontier target;
- WoS-first role presentation.

### 5. Next expansion

Report the strongest:

- topic clusters;
- repeated authors;
- repeated venues;
- Zotero tag/collection clusters;
- citation-frontier items;
- 3–10 recommended broad human WoS searches.

### 6. Problems / fixes

For any implementation defect discovered, state:

- failing example;
- root cause;
- exact code change;
- regression test added/updated;
- post-fix result.

Do not claim success solely because commands exited with code 0.

---

## Success condition

Success means the real local loop is demonstrably useful and safe:

```text
real WoS exports
→ independent WoS corpus
→ conservative linking
→ WoS-first structured consumption
→ normal fallback for missing coverage
→ actionable next broad-search plan
```

**100% local WoS coverage is explicitly not required.**
