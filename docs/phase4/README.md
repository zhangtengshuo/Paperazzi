# Phase 4 — Identity and Resolution

Phase 4 starts after `PHASE3_V1` persistence has passed Phase 3.1 hardening.

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

## Branch policy — mandatory

**Phase 4 is main-only. Do not create a new Git branch.**

All Phase 4 implementation, tests, validation reports and documentation updates are committed directly to `main`.

Forbidden during Phase 4:

```text
git switch -c ...
git checkout -b ...
agent/* branches
codex/* branches
feature/* branches
Phase-4 pull-request branches
```

Before modifying the repository, a local implementation agent must verify that the current branch is exactly `main`. If an external tool automatically creates another branch, stop using that branch and return to `main` before making Phase 4 changes.

The user explicitly chose this workflow; it overrides generic branch/PR conventions for Phase 4.

---

## Objective

Phase 3 deliberately persisted paper-local creator mentions and raw/accepted reference evidence without pretending that names were people or references were citation edges.

Phase 4 converts those durable source records into **reviewable semantic resolution**:

```text
paper_creator_mention
        ↓
author identity candidate / decision
        ↓
canonical author

accepted paper_reference
        ↓
reference match candidate / decision
        ↓
local cited paper
```

The phase must remain conservative and reversible. A false author merge or false citation edge is worse than leaving an item unresolved.

---

## Phase 4 milestones

### Phase 4A — author identity persistence and normalization

Create the durable identity layer for:

- canonical `authors`;
- normalized name variants;
- creator-mention membership/link rows;
- external identifiers when explicitly available;
- identity candidate scores and evidence;
- merge/split/not-same-person decisions;
- decision provenance and manual locks.

A normalized name is a blocking/candidate-generation feature, **not an identity assertion**.

### Phase 4B — authorship roles and accepted local evidence

Project resolved authors onto papers while preserving source creator mentions.

Phase 4B covers:

- ordered authorship;
- deterministic first-author status from accepted creator order;
- corresponding-author status only from accepted evidence or explicit structured metadata;
- author-paper affiliation evidence from accepted PDF spans;
- evidence provenance for role/affiliation assignments.

Corresponding author is a property of an author-paper relationship, not a permanent property of the person.

### Phase 4C — local reference resolution

Resolve **accepted** `paper_references` against papers already present in the local Paperazzi corpus.

Required match classes:

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED
AUTHOR_YEAR_JOURNAL
JOURNAL_VOLUME_PAGE_YEAR
BIBLIOGRAPHIC_COMPOSITE
AI_RESOLVED
UNRESOLVED
```

Only an accepted `paper_reference_match` may later generate a derived `CITES` edge. Phase 4 does not materialize the graph itself.

### Phase 4D — real-library validation and review queues

Validate the identity and reference layers against the real Zotero-derived Paperazzi database.

The final report must distinguish:

- automatically accepted high-confidence decisions;
- ambiguous candidates requiring review;
- explicit conflicts;
- unresolved creator mentions/references;
- reversible manual decisions.

---

## Normative documents

Read in this order:

1. `docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md`
2. `docs/phase4/PHASE4_IMPLEMENTATION.md`
3. `docs/architecture/PERSISTENCE_MODEL.md`
4. `docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md`
5. `prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md`
6. `schemas/phase4_report.schema.json`

Phase 4 code must continue to respect all Phase 3 provenance and acceptance semantics.

---

## Inputs

Author identity may consume:

- `papers`;
- `paper_creator_mentions`;
- accepted local PDF evidence spans;
- accepted extraction review results;
- explicit external identifiers already present in trusted local/returned structured evidence;
- coauthor, affiliation, publication and topic context as supporting evidence.

Reference resolution may consume:

- `paper_references` with `acceptance_status='ACCEPTED'` only;
- normalized local paper metadata;
- DOI/year identifiers extracted from accepted references;
- bibliographic text and local author metadata.

Candidate/unreviewed PDF output must not silently participate as accepted semantic evidence.

---

## Non-goals

Phase 4 does **not** implement:

- author portraits/photos;
- age or gender enrichment;
- education history;
- social networks/profile pages;
- broad online biographical enrichment;
- monthly author monitoring;
- frontend UI;
- FastAPI endpoints;
- graph materialization or visualization;
- automatic Internet research.

Those remain later enrichment/UI/graph work.

---

## Required end state

Phase 4 is complete only when:

```text
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```

The system must be able to answer, with provenance:

1. which canonical author a creator mention is linked to, or why it remains unresolved;
2. which authorship roles are known for a paper;
3. which accepted raw reference points to which local paper, or why it remains unresolved;
4. which decisions were automatic, AI-reviewed or manual;
5. how to reverse an incorrect identity merge or reference decision without rewriting source history.
