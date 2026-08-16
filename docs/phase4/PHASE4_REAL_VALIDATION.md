# Phase 4 — Real-library validation workflow

This is the operational validation path for Phase 4 identity/authorship/reference resolution.

## Branch policy

**Work only on `main`. Do not create a branch.**

Before running or modifying anything:

```bash
git branch --show-current
```

Expected:

```text
main
```

Use `git pull --ff-only origin main` to update. Do not create `codex/*`, `agent/*`, `feature/*` or PR branches during Phase 4.

---

## 1. Pull and run the full regression suite

```bash
git pull --ff-only origin main
python -m unittest discover -s tests -v
```

Do not continue on a real correctness failure. Convert systematic failures into a regression test before fixing code.

Phase 4 tests now cover:

- migration `0004/0005` and downgrade/upgrade round-trip;
- extraction Attempt 1→3 state machine;
- terminal accepted vs terminal-unaccepted extraction semantics;
- name normalization and raw-name preservation;
- name-only collision protection;
- accepted-membership uniqueness;
- reversible merge/split/unlink/relink history;
- manual locks and explicit NOT_SAME_PERSON;
- external-ID conflicts;
- authorship order/first-author projection;
- accepted-only corresponding/affiliation evidence;
- accepted-reference-only citation matching;
- DOI, title, author-year-journal and journal-volume-page-year match paths;
- ambiguous, contradictory and self-match cases.

---

## 2. Stage 1 — fresh real Zotero corpus + identity resolution

Run:

```bash
python scripts/validate_phase4.py
```

This creates an ignored validation database under:

```text
data/phase4-validation/paperazzi.sqlite3
```

It then:

1. migrates to current head;
2. creates a transaction-consistent read-only Zotero snapshot;
3. imports the full canonical Zotero corpus;
4. runs the conservative author identity bootstrap;
5. reruns identity resolution to test idempotency;
6. consumes only already-accepted authorship evidence;
7. runs local reference resolution only for already-`ACCEPTED` references;
8. checks FKs, duplicate accepted memberships, candidate-input leakage and resolver idempotency.

### Expected first-run result

On a fresh Phase 4 validation DB there will normally be **zero accepted PDF references**, because deterministic PDF extraction is review-gated.

Therefore the first run is expected to end with a nonzero exit code and a report note similar to:

```text
Final real-reference gate not met: 0 accepted references; need at least 5.
```

This is deliberate. It prevents a synthetic-only reference test from being presented as a real-library Phase 4 PASS.

Inspect:

```text
data/phase4-validation/phase4_report.json
```

The identity/integrity sections should already be internally consistent even if the final status remains `FAIL` because the real-reference anchor gate has not yet been met.

---

## 3. Stage 2 — seed deterministic PDF candidates for anchor selection

Run:

```bash
python scripts/seed_phase4_reference_anchors.py --sample-size 120 --anchor-count 8
```

This script is intentionally non-authoritative. It may:

- run deterministic-v3 PDF extraction;
- create Attempt 1 rows;
- persist evidence/reference outputs as `CANDIDATE`;
- leave attempts as `REVIEW_PENDING`;
- propose high-value PDFs containing candidate DOI references that uniquely map to another local Paperazzi paper.

It **must not**:

- add an AI review;
- call `accept_attempt()`;
- change a reference to `ACCEPTED`;
- create an accepted citation match.

Output:

```text
data/phase4-validation/reference_anchor_candidates.json
```

A DOI hit is only useful for choosing a test PDF. It is not evidence that the PDF extraction itself is trustworthy.

---

## 4. Stage 3 — explicit local-AI review of the selected PDF attempts

For each selected anchor in `reference_anchor_candidates.json`:

1. open the actual local PDF read-only;
2. inspect the deterministic Attempt-1 result;
3. follow `prompts/local_ai/PDF_EVIDENCE_AGENT.md`;
4. assess front matter and especially the reference section/entry boundaries;
5. produce an explicit review decision.

For this fast Phase 4 anchor validation, prefer anchors whose Attempt 1 can defensibly terminate as:

```text
PASS
ACCEPT_PARTIAL
```

If an anchor requires `RETRY`, do **not** pretend it passed. Either execute the normal bounded adaptive Attempt-2/3 workflow or choose another anchor for this validation set.

Terminal negative outcomes are also valid:

```text
UNRESOLVED
NEEDS_OCR
```

Create a JSON file conforming to:

```text
schemas/phase4_anchor_reviews.schema.json
```

Example:

```json
{
  "reviews": [
    {
      "attempt_id": 123,
      "reviewer_type": "LOCAL_AI",
      "decision": "PASS",
      "section_confidence": "HIGH",
      "segmentation_confidence": "HIGH",
      "entry_text_quality": "GOOD",
      "problem_codes": [],
      "quality_notes": "Reference boundaries checked against the PDF tail pages.",
      "reviewer_runtime": "local-ai"
    }
  ]
}
```

Do not infer review quality from DOI matching. The reviewer must inspect the PDF evidence itself.

---

## 5. Stage 4 — import reviews through Paperazzi APIs

Apply the reviewed decisions with:

```bash
python scripts/apply_phase4_anchor_reviews.py \
  data/phase4-validation/anchor_reviews.json
```

This importer writes through the Paperazzi repository/service layer:

```text
PASS / ACCEPT_PARTIAL
    -> extraction run COMPLETED
    -> accepted_attempt_id set
    -> accepted evidence/reference rows

UNRESOLVED / NEEDS_OCR
    -> extraction run COMPLETED
    -> accepted_attempt_id remains NULL
    -> candidate evidence is not promoted
```

The importer never accepts `RETRY`; retries belong to the normal adaptive extraction state machine.

---

## 6. Stage 5 — final real-library Phase 4 validation

Rerun against the same validation DB:

```bash
python scripts/validate_phase4.py --reuse-db
```

Default final gate requires at least:

```text
5 accepted real PDF references
```

You may require more, for example:

```bash
python scripts/validate_phase4.py --reuse-db --min-accepted-references 10
```

A final PASS requires all of the following simultaneously:

```text
unit/regression suite PASS
migration head current
foreign_key_check = 0
accepted author membership uniqueness holds
name-only auto-merge violations = 0
identity rerun creates no duplicate decisions/memberships
corresponding-author assignment from candidate evidence = 0
candidate paper_reference inputs matched = 0
reference matching rerun creates no duplicate matches
real accepted-reference minimum reached
```

The report is:

```text
data/phase4-validation/phase4_report.json
```

and must conform to:

```text
schemas/phase4_report.schema.json
```

---

## 7. What is not required for Phase 4 validation

Do **not** block Phase 4 on:

- reviewing all 2161 local PDFs;
- resolving all 12381 creator mentions;
- forcing all same-name authors into one identity;
- resolving every bibliography entry;
- online author enrichment;
- author portraits/education/social profiles;
- UI/API;
- materialized graph/CITES tables.

Unresolved and review-required cases are expected outcomes. Precision and provenance have priority over coverage.

---

## 8. Final expected state

Only after the staged real-library run passes:

```text
PHASE_4_STATUS = PASS
PAPERAZZI_IDENTITY_SCHEMA = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_MINIMAL_UI
```

Until then:

```text
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
PHASE_4_STATUS = IN_PROGRESS
```
