# Phase 4 Implementation Plan

This document defines the gated implementation sequence for author identity and local reference resolution.

## 0. Branch rule

**All Phase 4 work is performed directly on `main`. Do not create a branch.**

Before any modification:

```bash
git branch --show-current
```

Expected:

```text
main
```

If the branch is not `main`, return to `main` before changing files. Do not create `codex/*`, `agent/*`, `feature/*`, PR or experiment branches for Phase 4.

Commits should remain small and milestone-oriented, but they are committed directly to `main` after each gate passes.

---

## 1. Preflight guard cleanup

Before Phase 4A, add two workflow guards identified during Phase 3.1 review:

1. extraction run `final_status` must derive from the latest review decision rather than accepting a contradictory caller-supplied status;
2. Attempt 2 may be created only after Attempt 1 was reviewed `RETRY`; Attempt 3 only after Attempt 2 was reviewed `RETRY`.

Add regression tests. This is a small Phase-3 workflow guard carried into Phase 4 preflight; do not reopen Phase 3 architecture.

Gate:

```text
all existing tests PASS
new review/attempt-order tests PASS
```

---

## 2. Phase 4A — identity schema and normalization

### 2.1 Migration

Add a new Alembic migration, expected to become something like:

```text
0004_identity_resolution
```

Do not rewrite frozen Phase-3 migrations `0001..0003`.

Implement durable identity tables based on `IDENTITY_AND_REFERENCE_RESOLUTION.md`.

Minimum required persisted concepts:

```text
authors
author_name_variants
author_identity_memberships
author_identity_decisions
author_identity_evidence
authorships
authorship_evidence
```

`author_external_ids` may be included now if cleanly supported.

### 2.2 Identity constraints

Tests must enforce:

- one creator mention may have at most one active `ACCEPTED` author membership;
- source mention FK is real;
- canonical author FK is real;
- rejected/superseded membership history is retained;
- manual identity lock is persisted;
- duplicate external IDs cannot silently map to multiple active authors when the identifier namespace requires uniqueness.

### 2.3 Name normalization

Implement pure deterministic normalization functions in `src/paperazzi/identity/`.

Required tests:

- Unicode normalization;
- punctuation/whitespace normalization;
- initials handling;
- family/given-order blocking forms;
- diacritic-insensitive search form;
- original sourced name preserved exactly;
- normalization does not itself write identity decisions.

Gate 4A ends when schema + normalization tests pass.

---

## 3. Phase 4B — author candidate generation and reversible decisions

### 3.1 Candidate generation

Generate possible same-person clusters from creator mentions using blocking features.

Allowed candidate evidence:

- normalized full-name compatibility;
- initials compatibility;
- coauthor overlap;
- publication chronology;
- accepted affiliation evidence;
- accepted correspondence/email evidence;
- explicit external IDs when present.

Do not use name similarity alone for automatic acceptance.

### 3.2 Conservative acceptance policy

Recommended first implementation:

```text
AUTO_ACCEPT
  only for uniquely strong, non-contradictory evidence

REVIEW_REQUIRED
  common-name/name-only or mixed evidence

AUTO_REJECT / CONFLICT
  explicit identifier contradiction or locked not-same-person decision
```

Persist score components and reason codes; never persist only an opaque score.

### 3.3 Reversible merge/split

Implement service operations for:

```text
link mention
unlink mention
merge identity
split identity
not-same-person
lock / unlock
```

Operations must preserve source mentions and previous decisions.

### 3.4 Authorship projection

Build/update `authorships` from accepted mention memberships.

Tests:

- order preserved;
- first author derived correctly;
- same author on multiple papers produces one canonical author with multiple authorships;
- changing a Zotero tag/attachment does not invalidate author membership;
- source creator mention remains traceable.

Gate 4B ends with a synthetic corpus containing namesakes, aliases, initials, repeated coauthors and explicit conflicts.

---

## 4. Phase 4C — accepted local evidence and authorship roles

### 4.1 Corresponding author

Corresponding-author resolution must require accepted evidence.

Test cases must include:

- clear `* Corresponding author: name, email` mapping;
- multiple corresponding authors;
- email present but not mapped to a creator -> unresolved;
- publisher/customer-service email -> rejected;
- candidate/unreviewed evidence -> must not assign corresponding author.

### 4.2 Affiliation evidence

Persist author-paper affiliation evidence only when mapping is defensible.

Keep raw evidence span IDs and review provenance. Do not create a global institution identity system yet.

### 4.3 Batch PDF-review interaction

Phase 4 may consume accepted PDF evidence, but must not bypass the existing mandatory review gate.

If a real-library validation needs accepted reference/author evidence, use a **small explicitly reviewed anchor set** rather than silently accepting all deterministic candidates.

A full 2161-PDF review campaign is not required to validate Phase 4 infrastructure.

Gate 4C ends when role assignments can be reproduced from accepted evidence and remain absent for candidate-only evidence.

---

## 5. Phase 4D — local paper-reference resolution

### 5.1 Eligibility

Resolver query must begin from:

```text
paper_references.acceptance_status = 'ACCEPTED'
```

No candidate reference may be matched.

### 5.2 Normalized paper index

Build local lookup/index features for papers:

- normalized DOI;
- normalized title;
- publication year;
- venue/journal tokens;
- first-author/family-name tokens when available;
- volume/page/article number when represented in available metadata.

Do not edit Zotero source metadata to improve a match.

### 5.3 Matching ladder

Implement in this order:

1. `DOI_EXACT`;
2. `TITLE_EXACT_NORMALIZED` + corroborating fields;
3. `AUTHOR_YEAR_JOURNAL`;
4. `JOURNAL_VOLUME_PAGE_YEAR`;
5. `BIBLIOGRAPHIC_COMPOSITE`;
6. optional local-AI review for ambiguous candidates;
7. `UNRESOLVED`.

### 5.4 Acceptance requirements

- DOI exact must be unique and contradiction-free;
- title-only cannot auto-accept without corroboration;
- composite matches require a centralized versioned threshold and margin;
- self-match should be rejected unless the raw reference truly cites the same work in a legitimate edge case and is manually reviewed;
- multiple plausible candidates go to review queue.

Tests must include DOI errors, same-title papers, same-author same-year papers, title punctuation differences, missing DOI, old references, malformed entries and deliberately ambiguous cases.

Gate 4D ends when accepted matches are reproducible and false-positive synthetic cases remain unresolved/rejected.

---

## 6. Real-library validation

After all synthetic/unit tests pass, validate on the real Paperazzi database rebuilt/migrated from Phase 3.

Do not require every creator mention/reference to resolve. Measure coverage and ambiguity explicitly.

Required report sections:

```text
schema / migration
unit tests
identity counts
identity candidate counts
accepted/rejected/unresolved membership counts
namesake conflict cases
authorship counts
first/corresponding author coverage
accepted PDF evidence used
eligible accepted references
reference-match counts by match_type
ambiguous/unresolved reference counts
manual/AI decision counts
foreign-key integrity
idempotency
reversibility tests
```

### Required real-library anchors

Select several known repeat authors and several common/initial-only names. Verify that name-only collisions are not silently merged.

For references, use a small accepted anchor set spanning:

- DOI-bearing reference;
- title match without DOI;
- old author-year bibliography;
- multiline/two-column reference;
- ambiguous/no-match reference.

---

## 7. Idempotency and re-resolution

Running the same resolver version twice over unchanged evidence must not create duplicate accepted decisions.

When resolver policy/version changes:

- retain old decisions;
- create new candidate/decision provenance as appropriate;
- never rewrite source history;
- manual locks remain authoritative unless explicitly unlocked.

---

## 8. Tests required before PASS

At minimum:

```text
Phase 3 regression suite still passes
attempt/review workflow guards
identity migration/FKs/uniqueness
name-normalization purity
name-only never auto-merges
namesake negative cases
accepted membership uniqueness
merge/split reversibility
manual lock behavior
creator-mention stability across Zotero nonbibliographic changes
authorship order and first-author logic
corresponding-author accepted-evidence boundary
candidate PDF evidence excluded
reference resolver accepted-reference boundary
DOI exact unique match
same-title ambiguity
composite threshold/margin behavior
no direct CITES graph writes
resolver idempotency
foreign_key_check = 0
```

---

## 9. Commit discipline on main

Suggested direct-to-main milestone commits:

```text
Phase 4 preflight: enforce extraction review workflow
Phase 4A: identity schema and normalization
Phase 4B: author identity resolution and reversible decisions
Phase 4C: authorship role evidence resolution
Phase 4D: local reference resolution
Phase 4 validation: real-library report
```

Again: **do not create a branch for any of these commits.**

---

## 10. PASS condition

Only after all gates pass:

```text
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```
