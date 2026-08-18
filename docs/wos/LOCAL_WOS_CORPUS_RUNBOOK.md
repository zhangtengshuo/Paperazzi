# Paperazzi Local WoS Corpus Runbook

**Purpose:** execute the first real local Web of Science background-corpus ingestion, matching, inspection, and expansion-planning cycle after the WoS architecture implementation.

**Architecture contract:** `docs/architecture/WOS_BACKGROUND_CORPUS.md`

This is an operational runbook. It does not redefine the architecture.

---

## 1. Scope of the next local run

The next local task is **not** to search Web of Science automatically and is **not** to make every Zotero paper have a WoS record.

The task is to prove the production loop on the user's real Paperazzi/Zotero data:

```text
manually exported WoS Plain Text files
        ↓
independent data/wos.sqlite3
        ↓
conservative Paperazzi ↔ WoS matching
        ↓
WoS-first structured paper presentation
        ↓
unmatched/ambiguous analysis
        ↓
manual broad-search plan for the next WoS export
```

Missing local WoS coverage is a normal state. `WOS_NOT_IN_LOCAL_CORPUS` must never be treated as a validation failure or as proof that the paper is absent from Web of Science.

---

## 2. Absolute local-work rules

1. Work on the existing `main` branch. **Do not create a branch or pull request.**
2. Do not reset, discard, overwrite, or rewrite unrelated local user work.
3. Use the dedicated micromamba environment named exactly `Paperazzi`; do not modify Anaconda `base` or other environments.
4. Zotero database, Zotero storage, PDFs, and manually exported WoS text files are source data and should be treated as read-only inputs.
5. Persistent WoS state belongs in Paperazzi-owned `data/wos.sqlite3`.
6. WoS exports may be placed under an ignored local path such as `imports/incoming/wos/`; do not commit them unless the user explicitly requests that.
7. Do not automate access to the Web of Science website in this task. Search/export remains human-triggered.
8. Do not promote fuzzy/ambiguous matches. DOI exact and conservative exact-title matching are the automatic production rules implemented for this stage.
9. Do not use PDF correspondence parsing to override a successfully matched WoS `RP` result. PDF evidence remains provenance/fallback.

---

## 3. Pre-flight

From the repository root, first inspect state without modifying it:

```bash
git branch --show-current
git status --short
```

Expected branch:

```text
main
```

If unrelated local changes exist, do not discard them. Record them and avoid touching those paths.

Check the Paperazzi environment:

```bash
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The authoritative result should report:

```json
{"pass": true}
```

If the environment is unhealthy, repair only the `Paperazzi` environment.

---

## 4. Run targeted WoS regression tests before touching real data

Run the WoS-specific tests first:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -p "test_wos_*.py" -v
```

Also verify migration behavior:

```bash
micromamba run -n Paperazzi python -m unittest tests.test_phase3_migrations -v
```

If the test module invocation is unavailable because of local test-package layout, use unittest discovery for the migration file as well.

Do not proceed silently after a failure. Capture the failing test and traceback.

---

## 5. Upgrade the Paperazzi database schema

The Paperazzi-side WoS bridge and match-state tables are created by Alembic migrations.

```bash
micromamba run -n Paperazzi alembic upgrade head
```

This upgrades `data/paperazzi.sqlite3` according to the configured Paperazzi database URL/path. If the real database is stored elsewhere, use the project's established `PAPERAZZI_DB_URL`/database configuration rather than copying the database.

Required Paperazzi-side tables after upgrade include:

```text
paper_wos_links
paper_wos_match_state
```

The independent WoS corpus itself is **not** an Alembic database.

---

## 6. Prepare the first real WoS export batch

Use Clarivate **Plain Text** with **Full Record and Cited References**.

Recommended local staging location:

```text
imports/incoming/wos/
```

This path is under an ignored `imports/incoming/` tree.

Do not rename or modify source exports merely to make parsing succeed. Keep the original exported files so import provenance remains recoverable.

It is acceptable—and expected—for batches to overlap heavily. The importer upserts records by WoS accession number (`UT`).

Example batch layout:

```text
imports/incoming/wos/
    sf-main.txt
    pentacene.txt
    tetracene.txt
    sf-theory.txt
```

A small `savedrecs10.txt`-style file can be imported first as a smoke test if available, but the goal of this run is a larger real corpus batch.

---

## 7. Initialize/import the independent WoS corpus

Initialization is optional because `import` initializes the DB automatically, but it may be run explicitly:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 init
```

Import each exported text file. Attach a human-readable label and, when useful, the search rationale:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 import \
  imports/incoming/wos/sf-main.txt \
  --label "SF broad" \
  --search-note "Broad singlet-fission topic export; Full Record + Cited References"
```

Multiple files may be supplied to one invocation:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 import \
  imports/incoming/wos/sf-main.txt \
  imports/incoming/wos/pentacene.txt \
  imports/incoming/wos/tetracene.txt \
  --label "Initial SF corpus"
```

Overlap is safe. Re-import is expected to produce `updated_count` rather than duplicate records.

After import:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 stats
```

Record at least:

```text
records
authors
corresponding_members
cited_references
resolved_citation_edges
import_batches
```

A non-zero corpus is required; a particular coverage percentage is not.

---

## 8. Sanity-check the imported corpus

Inspect a few known records using title, DOI, author, or UT search:

```bash
micromamba run -n Paperazzi paperazzi-wos --db data/wos.sqlite3 search "singlet fission" --limit 20
```

For records already used to validate RP semantics, check that group-level correspondence behavior remains correct. In particular:

```text
RP Xie, XY; Ma, HB (corresponding author), ...
```

must represent both Xie and Ma as corresponding authors.

Likewise, repeated address groups must not create duplicate people in the Paperazzi presentation layer.

Do not infer corresponding authors from `EM` alone.

---

## 9. Run Paperazzi ↔ WoS matching as a dry run

Always inspect the dry run before persisting match state:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --unmatched-output data/wos-unmatched-dry-run.jsonl
```

Review the summary:

```text
papers
matched
ambiguous
not_in_local_corpus
not_checked
links_written = 0
states_written = 0
```

Expected semantics:

- `matched`: conservatively matched to a local WoS UT.
- `ambiguous`: candidates exist but no safe automatic decision was made.
- `not_in_local_corpus`: the current imported local corpus has no match.
- `not_checked`: should mainly occur when no local WoS database is available; after an actual dry-run against an available corpus, the dry-run decisions themselves still report what would be stored.

Do **not** optimize the result to eliminate `not_in_local_corpus`.

Spot-check a sample of DOI matches, title matches, ambiguous cases, and no-local-record cases before applying.

---

## 10. Persist accepted matches and explicit match state

If the dry-run result is credible:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --apply \
  --unmatched-output data/wos-unmatched.jsonl
```

This writes:

```text
paper_wos_links       accepted links only
paper_wos_match_state matched / ambiguous / not-in-local-corpus state
```

It must not copy the entire WoS record into `paperazzi.sqlite3`.

Re-running the same apply operation should be stable and should not create duplicate accepted links.

---

## 11. Validate WoS-first correspondence presentation

For matched papers, the effective corresponding-author presentation should prefer WoS `RP` when WoS authors can be mapped safely onto the Paperazzi source-author list.

The API should preserve both layers:

```text
source_roles                  existing Paperazzi/PDF role provenance
roles                         effective presentation roles
correspondence_resolution     tells which source won
```

Expected effective source when the mapping is complete:

```text
WOS_RP
```

When only a partial safe mapping is possible, WoS may augment but must not destructively erase fallback evidence.

Use the web app:

```bash
micromamba run -n Paperazzi paperazzi-web
```

Then inspect several matched and unmatched papers in the browser.

Check that:

1. WoS information appears before the PDF audit/fallback block.
2. Matched records show WoS accession, correspondence, authors, identifiers, affiliations, keywords/classifications, funding, abstract, citation counts, and cited references where available.
3. No-local-record papers remain normally usable.
4. The UI does not say that a paper is absent from Web of Science merely because it is absent from the local corpus.
5. Cited references distinguish locally resolved WoS targets, Zotero/Paperazzi targets, and unresolved/external references.

---

## 12. Measure real local coverage

The relevant question is not "Did every Zotero paper obtain WoS?" but:

```text
How much useful structured coverage did this import create?
Which residual clusters are worth another broad export?
```

Inspect:

```text
/api/wos/coverage
```

or the WoS Corpus page.

Capture at least:

```text
active_zotero_papers
matched
not_in_local_corpus
ambiguous
not_checked
coverage_fraction
```

Coverage is descriptive, not a pass/fail gate.

---

## 13. Generate the next manual WoS expansion plan

Run:

```bash
micromamba run -n Paperazzi python scripts/plan_wos_expansion.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --limit 30 \
  --output data/wos-expansion-plan.json
```

The report includes:

```text
match_states
clusters.title_bigrams
clusters.title_terms
clusters.venues
clusters.authors
clusters.zotero_tags
clusters.zotero_collections
suggested_manual_searches
citation_frontier
```

Use the clusters to choose a **small number of broad WoS searches**. Good next searches recover many residual Zotero papers or an important surrounding scholarly neighborhood at once.

Individual-title search is a residual/high-value strategy, not the default expansion method.

---

## 14. What must be returned after the local run

The local operator/AI should report the following, with actual numbers from the real corpus:

### Environment and migration

```text
Paperazzi environment check: PASS/FAIL
Alembic upgrade: PASS/FAIL
WoS regression tests: PASS/FAIL
```

### WoS import

```text
input files
import batches
records
new_count / updated_count per batch
authors
corresponding_members
cited_references
resolved_citation_edges
```

### Paperazzi ↔ WoS coverage

```text
active papers
matched
ambiguous
not in local corpus
not checked
coverage fraction
match-method counts (especially DOI_EXACT vs title-based)
```

### Spot checks

At minimum inspect and report:

- several DOI exact matches;
- several title-based matches if any;
- all or a representative set of ambiguous matches;
- several `WOS_NOT_IN_LOCAL_CORPUS` papers;
- known multi-corresponding-author RP cases;
- several citation edges whose target Full Records are local;
- several unresolved citation-frontier targets.

### Next expansion

Return the top useful:

- topic clusters;
- repeated authors;
- repeated journals;
- Zotero semantic clusters;
- citation-frontier DOI targets;
- 3–10 recommended broad/manual WoS searches.

Do not claim completion by saying only that scripts ran. The goal is to produce a trustworthy real-corpus coverage/expansion assessment.

---

## 15. Stop conditions

Stop and report rather than silently changing architecture when any of the following occurs:

- parser fails on a valid WoS Plain Text file;
- `UT` is absent from a record that otherwise appears to be a Full Record;
- duplicate DOI records cause ambiguous citation targets;
- many apparently obvious DOI matches are not found;
- title matching produces suspicious cross-paper matches;
- author mapping is incomplete enough that WoS RP cannot be safely projected;
- database migration fails;
- web integration breaks when `wos.sqlite3` is missing;
- a proposed fix would require fuzzy automatic promotion or PDF evidence overriding a valid WoS record.

In these cases preserve the data, record the failing examples, and repair the implementation deliberately.

---

## 16. Definition of success for this next local stage

The stage is successful when:

1. a non-trivial real WoS corpus has been imported into the independent `wos.sqlite3`;
2. repeated/overlapping imports remain stable;
3. Paperazzi papers are conservatively classified as matched / ambiguous / not-local;
4. matched paper detail uses WoS structured information and WoS-first RP semantics without destroying fallback provenance;
5. ordinary Paperazzi operation remains valid for papers without local WoS records;
6. WoS cited references produce useful local citation edges and an unresolved frontier;
7. the expansion planner produces actionable broad-search clusters for the next human WoS export.

**Do not use 100% WoS coverage as a success criterion.**
