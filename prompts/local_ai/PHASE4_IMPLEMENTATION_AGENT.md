# Paperazzi Local AI Prompt — Phase 4 Implementation and Validation Agent

You are working on Phase 4 of Paperazzi: author identity, authorship evidence and local reference resolution.

## 1. Branch policy — absolute rule

**Work only on `main`. Do not create a Git branch or pull request.**

Before modifying anything:

```bash
git branch --show-current
```

Expected: `main`.

Forbidden:

```text
codex/*
agent/*
feature/*
phase4/*
PR branches
git switch -c
git checkout -b
```

Use `git pull --ff-only origin main` before work when remote `main` may have advanced.

---

## 2. Current implementation state

Phase 3/3.1 is frozen and passed. Phase 4 implementation is now **IN_PROGRESS**, not NOT_STARTED.

Do not recreate already implemented Phase 4 components. Inspect current `main` first.

Expected implemented surface includes:

```text
migrations/versions/0004_identity_resolution.py
migrations/versions/0005_identity_history_constraints.py

src/paperazzi/identity/
  models.py
  normalization.py
  policy.py
  service.py
  operations.py
  review.py
  authorship_evidence.py
  reference_resolution.py

scripts/
  validate_phase4.py
  seed_phase4_reference_anchors.py
  apply_phase4_anchor_reviews.py

tests/test_phase4_*.py
```

The migration head is expected to be:

```text
0005_identity_history_constraints (head)
```

If current `main` differs, trust the repository and inspect the latest commits rather than blindly reproducing this list.

---

## 3. Required reading

Read:

1. `docs/phase4/README.md`
2. `docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md`
3. `docs/phase4/PHASE4_IMPLEMENTATION.md`
4. `docs/phase4/PHASE4_REAL_VALIDATION.md`
5. `docs/architecture/PERSISTENCE_MODEL.md`
6. `docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md`
7. `prompts/local_ai/PDF_EVIDENCE_AGENT.md`
8. `schemas/phase4_report.schema.json`
9. `schemas/phase4_anchor_reviews.schema.json`
10. latest Phase 3.1 validation report.

`IDENTITY_AND_REFERENCE_RESOLUTION.md` is normative for Phase 4 semantics.

---

## 4. Execution strategy — parallel implementation, gated integration

The user explicitly requested aggressive progress.

**Independent tasks may and should proceed in parallel.** Do not wait for one milestone to be fully finished before inspecting or implementing another task that has no real dependency on it.

Examples that can proceed independently:

```text
identity normalization/tests
reference matching/tests
migration constraints
review queue
accepted authorship evidence mapping
validation/report tooling
documentation
```

Hard dependencies still apply where data contracts require them. For example, a final real reference match cannot precede accepted reference evidence.

The rule is:

```text
parallel implementation
        ↓
continuous synthetic/regression testing
        ↓
fix cross-module integration defects
        ↓
real-library staged validation
        ↓
final PASS only when every gate passes
```

Do not interpret parallel development as permission to bypass correctness gates.

---

## 5. Non-negotiable semantics

- Zotero `zotero.sqlite` and Zotero PDFs are read-only.
- Never rewrite source creator mentions to encode identity.
- A normalized-name match alone never auto-merges authors.
- Zotero `creatorID` is supporting source-local evidence, not a globally authoritative person identifier.
- One creator mention may have at most one accepted canonical author membership.
- Merge/split/unlink/relink history must remain auditable and repeatable.
- Manual `NOT_SAME_PERSON` and identity locks override automatic suggestions until explicitly reversed.
- Corresponding author is paper-specific.
- Only accepted PDF evidence may create authoritative corresponding-author/affiliation claims.
- Candidate/unreviewed PDF evidence must not leak into authoritative authorship facts.
- Only `paper_references.acceptance_status='ACCEPTED'` may enter semantic reference matching.
- Only accepted `paper_reference_matches` may later produce `CITES`; Phase 4 does not materialize graph edges.
- Ambiguous/unresolved is a valid outcome.
- False author merges and false citation edges are worse than missing links.

---

## 6. Extraction review state machine

The hardened workflow is:

```text
Attempt 1
  -> mandatory review
  -> RETRY only permits Attempt 2

Attempt 2
  -> only after Attempt 1 latest review = RETRY
  -> RETRY only permits Attempt 3

Attempt 3
  -> terminal review only; RETRY is invalid
```

Terminal accepted decisions:

```text
PASS
ACCEPT_PARTIAL
```

These may call `accept_attempt()` and promote evidence/reference rows to `ACCEPTED`.

Terminal unaccepted decisions:

```text
UNRESOLVED
NEEDS_OCR
```

These use `finalize_unaccepted_attempt()` and must not promote candidate evidence.

---

## 7. Identity behavior

Candidate evidence may include:

- normalized-name compatibility;
- initials;
- local Zotero creator reuse as supporting evidence;
- repeated coauthor neighborhood;
- accepted affiliation/correspondence evidence;
- explicit accepted external IDs.

Name evidence alone is blocking/candidate evidence, never sufficient automatic identity truth.

Persist component scores and provenance. Do not store only an opaque confidence score.

The identity layer must support:

```text
create identity
link mention
unlink mention
merge identities
split mention/identity
NOT_SAME_PERSON
lock / unlock
external-ID conflict
```

History must survive repeated correction cycles.

---

## 8. Reference behavior

Only accepted references are eligible.

Implemented/required deterministic classes:

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED
AUTHOR_YEAR_JOURNAL
JOURNAL_VOLUME_PAGE_YEAR
BIBLIOGRAPHIC_COMPOSITE
```

Policy is centralized in `src/paperazzi/identity/policy.py`.

Conservative rules:

- unique DOI exact may auto-accept;
- duplicate DOI is ambiguous;
- exact title still requires corroboration and score margin;
- `AUTHOR_YEAR_JOURNAL` is review-oriented and must not become truth from those three weak fields alone;
- unique strong `JOURNAL_VOLUME_PAGE_YEAR` may auto-accept under the versioned threshold/margin;
- DOI contradictions block bibliographic autoaccept;
- self-match is excluded by default;
- candidate inputs are never matched.

Do not write graph edges.

---

## 9. Testing discipline

Run frequently:

```bash
python -m unittest discover -s tests -v
```

All Phase 3 tests must remain green.

If a failure is a real implementation defect:

1. preserve/add a regression test;
2. fix the general code;
3. rerun the complete suite;
4. commit directly to `main`.

Do not patch one real Zotero item by name/key unless it is only a diagnostic anchor.

Synthetic tests should cover systematic logic; real Zotero databases/PDFs must not be committed as fixtures.

---

## 10. Real-library validation — staged, review-gated

Follow `docs/phase4/PHASE4_REAL_VALIDATION.md`.

Stage 1:

```bash
python scripts/validate_phase4.py
```

A fresh run may intentionally return nonzero because there are not yet enough real accepted reference anchors. Inspect the identity/integrity metrics; do not relabel this as PASS.

Stage 2:

```bash
python scripts/seed_phase4_reference_anchors.py --sample-size 120 --anchor-count 8
```

This only seeds deterministic `REVIEW_PENDING/CANDIDATE` attempts and selects useful review candidates.

Stage 3: inspect the actual PDFs using `PDF_EVIDENCE_AGENT.md` and create a review JSON conforming to `schemas/phase4_anchor_reviews.schema.json`.

Stage 4:

```bash
python scripts/apply_phase4_anchor_reviews.py data/phase4-validation/anchor_reviews.json
```

Stage 5:

```bash
python scripts/validate_phase4.py --reuse-db
```

Default final gate requires at least five real accepted references.

---

## 11. Scope exclusions

Do not implement in Phase 4:

- frontend or FastAPI product UI;
- broad online enrichment;
- portraits, education, social profiles;
- age/gender inference;
- monthly monitoring;
- graph visualization/materialization;
- automatic review of all 2161 PDFs merely to increase coverage.

A small explicitly reviewed real anchor set is enough to validate Phase 4 infrastructure.

---

## 12. Commit discipline

Work only on `main`. Keep commits small enough to diagnose regressions, but do not serialize independent work unnecessarily.

Useful commit categories:

```text
Phase 4A: ...
Phase 4B: ...
Phase 4C: ...
Phase 4D: ...
Phase 4: fix ... regression
Phase 4: real-library validation report
```

No PR, no feature branch.

---

## 13. Completion state

Do not declare Phase 4 complete until the full suite and staged real-library report pass:

```text
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_MINIMAL_UI
```

Until then:

```text
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
PHASE_4_STATUS = IN_PROGRESS
```
