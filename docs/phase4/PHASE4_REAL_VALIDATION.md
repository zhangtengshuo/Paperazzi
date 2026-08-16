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
- **immutable source-corpus collaboration scoring**;
- **cascade-trap first-pass resolution + strict rerun idempotency**;
- **logical identity partition independence from source item order**;
- **complete source recording of every Zotero author**;
- non-author creators retained as source creators but excluded from canonical author resolution;
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

### Fresh DB is mandatory after identity-policy changes

After any change to identity scoring, source seeding, candidate blocking or policy version, Stage 1 **must** start from a fresh validation database. Do not use `--reuse-db` to validate a changed identity algorithm.

`--reuse-db` is reserved for continuing the *same already-validated identity state* after explicit PDF/reference anchor review.

The fresh command above recreates the ignored database under:

```text
data/phase4-validation/paperazzi.sqlite3
```

It then:

1. migrates to current head;
2. creates a transaction-consistent read-only Zotero snapshot;
3. imports the full canonical Zotero corpus;
4. verifies complete source creator/author recording;
5. runs the source-stable author identity bootstrap;
6. reruns identity resolution to test strict idempotency;
7. measures first-author resolution coverage separately from overall author coverage;
8. consumes only already-accepted authorship evidence;
9. runs local reference resolution only for already-`ACCEPTED` references;
10. checks FKs, duplicate accepted memberships, candidate-input leakage and resolver idempotency.

### Identity stability requirement

For the same source snapshot and policy, the second identity run must add no new semantic state:

```text
second_run.created = 0
second_run.linked = 0
duplicate_identity_decisions_on_rerun = 0
duplicate_identity_memberships_on_rerun = 0
```

The deterministic resolver must not rely on canonical memberships/authorships produced by its own earlier decisions. Collaboration evidence comes from immutable Phase-3 `paper_creator_mentions` source structure.

### Complete author-recording requirement

Every Zotero creator whose `creator_type='author'` must exist as a Paperazzi source author mention, regardless of identity resolution success.

The report distinguishes:

```text
total_creator_mentions
source_author_mentions
non_author_creator_mentions
accepted_memberships
candidate_memberships
unresolved_author_mentions
```

`candidate_memberships` and `unresolved_author_mentions` are intentionally different metrics: one unresolved author mention may have multiple candidate identities.

First/corresponding author coverage is reported separately:

```text
papers_with_resolved_first_author
papers_with_unresolved_first_author
papers_with_accepted_corresponding_author
papers_without_accepted_corresponding_author
```

Corresponding-author coverage may be zero before accepted PDF evidence exists; this is not permission to consume candidate evidence.

### Expected first-run final status

On a fresh Phase 4 validation DB there will normally be **zero accepted PDF references**, because deterministic PDF extraction is review-gated.

Therefore, even when the complete identity/integrity Stage 1 gate passes, the overall command is expected to end with a nonzero exit code and a report note similar to:

```text
Final real-reference gate not met: 0 accepted references; need at least 5.
```

This is deliberate. It prevents a synthetic-only reference test from being presented as a real-library Phase 4 PASS.

Inspect:

```text
data/phase4-validation/phase4_report.json
```

Identity Stage 1 is ready to advance only when at minimum:

```text
source_author_recording_complete = true
all_creator_recording_complete = true
name_only_auto_merges = 0
duplicate_active_memberships = 0
duplicate_identity_decisions_on_rerun = 0
duplicate_identity_memberships_on_rerun = 0
```

---

## 3. Stage 2 — seed deterministic PDF candidates for anchor selection

Only after the identity Stage 1 metrics above are stable, run:

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

Rerun against the same validation DB **only if the identity resolver/policy has not changed since Stage 1**:

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
complete source author recording
accepted author membership uniqueness holds
name-only auto-merge violations = 0
identity rerun creates no decisions/memberships
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
