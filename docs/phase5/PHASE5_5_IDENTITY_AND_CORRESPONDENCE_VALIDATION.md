# Paperazzi Phase 5.5 — Identity Reconciliation and Correspondence Validation

## Authority

This document governs validation of the interactive author-identity reconciliation work and the
next correspondence-coverage gate. It supplements `PHASE5_POST_FIX_VALIDATION.md`.

Use only the dedicated micromamba environment `Paperazzi` with Python 3.13.
Do not modify Zotero or the live Paperazzi database during validation.

---

## 1. Safety and database copy

Create a SQLite Backup API copy of the current live Paperazzi DB. Upgrade the copy to Alembic head.
Expected head for this validation is:

```text
0007_similar_author_review_queue
```

All manual identity actions, name-variant reconciliation, similar-name queue refresh and PDF evidence
rebuilds in this validation must target the copy.

Required final safety statements:

```text
PYTHON_313_CONTRACT = PASS
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO
```

---

## 2. Synthetic regression gate

Run:

```bash
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

The suite must include tests for:

- source spelling reconciliation into `AuthorNameVariant`;
- `Tengshuo Zhang` / `Teng-Shuo Zhang` / abbreviated-name recording;
- review-only structured given/family name reversal;
- manual canonical merge retaining spellings, publications and decision history;
- persistent canonical **Different people** decision preventing repeat suggestions;
- unresolved mention comparison and manual link;
- same-paper merge guard;
- multiple canonical candidates returned on one review detail page;
- interactive review API routes;
- Paperazzi ID display marker;
- `IDENTITY UNRESOLVED` explanatory UI;
- sticky/direct-page pagination UI;
- sourced author evidence filtering;
- correspondence benchmark scoring where any false positive is a hard failure.

Record count/runtime/failures/errors/skips and Paperazzi-originated warnings.

---

## 3. Source-name variant reconciliation on the copy

Preview:

```bash
micromamba run -n Paperazzi python scripts/sync_author_name_variants.py \
  --db-path <TEST_COPY>
```

Then apply only to the test copy:

```bash
micromamba run -n Paperazzi python scripts/sync_author_name_variants.py \
  --db-path <TEST_COPY> --apply
```

Required:

- no `PaperCreatorMention` row changes;
- accepted identity membership count unchanged;
- active authorship count unchanged;
- distinct source spellings increase or remain unchanged;
- rerunning `--apply` adds zero additional variants;
- source variants include abbreviations/full names/hyphenated forms when they exist in the corpus;
- searching by a recorded variant resolves to the same canonical author profile after merge.

Report at least 20 real canonical authors with more than one recorded spelling, prioritizing East
Asian names, hyphen/space variants, reversed structured order, and initial/full-name combinations.

---

## 4. Similar-name review candidate generation

Dry-run first:

```bash
micromamba run -n Paperazzi python scripts/refresh_identity_review_candidates.py \
  --db-path <TEST_COPY>
```

Record runtime and proposed review count. Then apply to the test copy.

Hard requirements:

- no automatic author merge occurs;
- no accepted identity membership is changed merely because names are similar;
- same-paper co-occurring canonical authors are not offered as an executable merge pair;
- similar-name suggestions use the dedicated `SIMILAR_AUTHOR_IDENTITY` queue type and do not overwrite `IDENTITY_CONFLICT` rows used for stronger conflicts such as external IDs;
- one queue item may open a compare view containing several similar canonical identities;
- compare view exposes each candidate's recorded names, recent publications, coauthors, similarity score and same-paper conflict state;
- canonical pairs previously marked **Different people** do not reappear after refresh.

Measure runtime on the real corpus. A full refresh should be operationally reasonable for an
interactive maintenance action. If runtime is dominated by per-pair SQL queries or exceeds 5 s on
the current ~7k-author corpus, preserve a profile and treat it as a performance defect before live use.

Review at least 30 suggestions and classify:

```text
SAME_PERSON
DIFFERENT_PERSON
UNCERTAIN
```

Do not merge uncertain pairs.

---

## 5. Interactive Identity Review actions

Start Paperazzi against the test copy.

For an unresolved creator-mention review, confirm the UI displays:

- exact source spelling;
- Paperazzi paper ID and title;
- ranked similar canonical identities;
- all candidate name variants;
- recent candidate publications;
- top coauthors;
- similarity score as a review hint, not an automatic decision.

Exercise on safe/known test-copy cases:

### Link mention to identity

After clicking Link:

- review item becomes RESOLVED;
- accepted membership points to selected canonical author;
- active authorship points to selected canonical author;
- exact source spelling appears as a SOURCE `AuthorNameVariant`;
- `AuthorIdentityDecision(operation='LINK_MENTION', actor='MANUAL')` exists.

### Not same person — mention versus canonical author

After clicking Not same on an unresolved mention candidate:

- negative membership/evidence is recorded with `NOT_SAME_PERSON`;
- future automatic linking of that mention to that candidate is blocked;
- other candidates remain reviewable.

### Create separate identity

- a new active canonical author is created;
- exact source spelling is retained;
- review item closes.

### Merge canonical identities

Use only a pair the reviewer is confident represents one person. Confirm:

- source canonical author becomes `MERGED`;
- target remains `ACTIVE`;
- all accepted paper mentions/publications move to target;
- all distinct source name variants remain visible on target;
- merge decision history exists;
- searching by either former spelling returns the merged canonical identity;
- no source `PaperCreatorMention` is rewritten;
- same-paper co-occurrence blocks merge with HTTP 409/UI error.

### Different people — canonical pair

For a similar-name pair that the reviewer is confident represents different people, click
**Different people** and confirm:

- a manual `AuthorIdentityDecision(operation='NOT_SAME_PERSON')` exists with both canonical author IDs and no creator mention;
- the review item closes;
- neither canonical identity is merged or rewritten;
- all publications and source spellings remain unchanged;
- rerunning **Refresh similar names** does not offer that unordered pair again.

---

## 6. Browser/UI fixes

Verify:

### Pagination

- pager is visible near the top while scrolling;
- direct page-number input works for Papers and Authors;
- Previous/Next still work;
- direct jump to last page works;
- page totals match API totals.

### Paper traceability

- paper list shows `ID <paper_id>`;
- paper detail clearly shows `Paperazzi ID`;
- reports can be cross-referenced to the visible ID.

### Identity wording

For an unresolved mention, UI says `IDENTITY UNRESOLVED`, not simply `UNRESOLVED`, and explains
that the source name is known but canonical-person linkage is pending.

### Author names

Author profile shows all recorded name variants and explicitly states that canonical grouping does
not overwrite source spellings.

### Multi-candidate identity comparison

Open a `SIMILAR_AUTHOR_IDENTITY` item and require:

- source canonical identity shown once;
- several plausible candidates shown when available;
- per-candidate publications/name variants/coauthors visible;
- `Merge source → candidate` and `Merge candidate → source` available only when not same-paper blocked;
- `Different people` available to persist a negative pair decision.

---

## 7. Sourced affiliation/contact evidence

Call:

```text
GET /api/authors/{author_id}/evidence
```

for authors with accepted/candidate PDF authorship evidence (paper 2467 is a known anchor in the
validation copy after rebuild).

Require:

- every row includes paper ID/title, evidence type, status and raw value;
- CANDIDATE affiliation text is visibly distinguishable from ACCEPTED facts;
- endpoint and Author UI do not create canonical current affiliation/email fields from candidate evidence;
- no evidence from SUPERSEDED/retracted authorship evidence is shown as current.

This is an inspection bridge to Phase 6 assertions, not a claim that current affiliation is solved.

---

## 8. Real-PDF correspondence benchmark

The current corpus has not yet populated correspondence evidence across all reachable primary PDFs.
Do not bulk-accept correspondence until this benchmark passes.

Build an 80-paper venue-diverse sample:

```bash
micromamba run -n Paperazzi python scripts/build_correspondence_benchmark.py \
  --db-path <TEST_COPY> \
  --sample-size 80 \
  --output data/phase5-validation/correspondence-benchmark-v1.json
```

The builder is read-only. It records source authors, primary document, extracted emails,
correspondence candidate text and current deterministic prediction.

The local AI must inspect the actual primary PDF for every benchmark case and fill:

```json
"ground_truth_corresponding_authors": ["exact source-author names"],
"review_status": "REVIEWED",
"review_notes": "brief evidence/style note"
```

Use source-author names from the case; do not invent normalized names.

The benchmark must deliberately identify styles such as:

- `*`, `**`, dagger/double-dagger markers;
- superscript numbers/letters;
- `Corresponding author`, `Correspondence to`, `For correspondence`;
- email-only footnotes;
- multiple corresponding authors;
- author initials in Zotero versus full names in email local parts;
- East Asian hyphenated/space-separated names;
- publisher/service emails that must not map to authors.

Score:

```bash
micromamba run -n Paperazzi python scripts/score_correspondence_benchmark.py \
  data/phase5-validation/correspondence-benchmark-v1.json
```

Gate:

```text
false positives = 0          HARD
precision = 1.0              HARD under this benchmark
recall >= 0.90               REQUIRED before population
```

If the gate fails:

1. preserve failing paper IDs and candidate text;
2. group failures by PDF style;
3. add the smallest synthetic regression reproducing each style;
4. fix parser/matcher conservatively;
5. rerun the full Python 3.13 suite;
6. rebuild the benchmark from a clean DB copy and rescore.

Do not weaken the false-positive gate to increase coverage.

---

## 9. Full correspondence population decision

Only after Section 8 passes may the local AI propose a controlled full-corpus population tool/run.
That population must:

- use selected PRIMARY/eligible documents only;
- preserve extraction run/attempt lineage;
- require reviewed extraction acceptance;
- create provenance-bearing `AuthorshipEvidence`;
- send ambiguous cases to review instead of guessing;
- be rerunnable/idempotent;
- support attempt/document retraction;
- run on a copy first and report before/after coverage/FP audit.

Until then:

```text
FULL_CORRESPONDENCE_POPULATION = BLOCKED_BY_BENCHMARK
```

---

## 10. Required report

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-phase5_5-identity-correspondence/
  PHASE5_5_VALIDATION_REPORT.md
```

Required status block:

```text
PYTHON_313_CONTRACT = PASS|FAIL
SYNTHETIC_REGRESSION = PASS|FAIL
NAME_VARIANT_RECONCILIATION = PASS|FAIL
SIMILAR_NAME_CANDIDATES = PASS|FAIL
IDENTITY_REVIEW_ACTIONS = PASS|FAIL
IDENTITY_REVIEW_REAL_SAMPLE = PASS|FAIL|PENDING_USER_REVIEW
CANONICAL_DIFFERENT_PAIR_PERSISTENCE = PASS|FAIL
PAGINATION_UX = PASS|FAIL
PAPER_ID_TRACEABILITY = PASS|FAIL
IDENTITY_UNRESOLVED_EXPLANATION = PASS|FAIL
SOURCED_AUTHOR_EVIDENCE_API = PASS|FAIL
CORRESPONDENCE_BENCHMARK = PASS|FAIL|INCOMPLETE
CORRESPONDENCE_BENCHMARK_FP = <integer>
CORRESPONDENCE_BENCHMARK_RECALL = <float>
FULL_CORRESPONDENCE_POPULATION = BLOCKED_BY_BENCHMARK|READY_FOR_COPY_POPULATION|PASS
ZOTERO_SOURCE_MODIFIED = NO|YES
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO|YES
EXISTING_ANACONDA_ENV_MODIFIED = NO|YES
```
