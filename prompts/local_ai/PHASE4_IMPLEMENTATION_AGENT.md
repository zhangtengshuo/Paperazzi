# Paperazzi Local AI Prompt — Phase 4 Implementation Agent

You are implementing Phase 4 of Paperazzi: author identity and local reference resolution.

## 1. Branch policy — absolute rule

**Work only on `main`. Do not create a new Git branch.**

Before modifying anything, verify the current branch is exactly `main`.

Do not create or use:

```text
codex/*
agent/*
feature/*
phase4/*
PR branches
```

Do not run `git switch -c` or `git checkout -b`.

If your environment/tool automatically places work on another branch, return to `main` before changing files. All Phase 4 commits are direct commits to `main` after their milestone tests pass.

This instruction overrides generic agent conventions that prefer feature branches or pull requests.

## 2. Required reading

Read before implementation:

1. `docs/phase4/README.md`
2. `docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md`
3. `docs/phase4/PHASE4_IMPLEMENTATION.md`
4. `docs/architecture/PERSISTENCE_MODEL.md`
5. `docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md`
6. `prompts/local_ai/PDF_EVIDENCE_AGENT.md`
7. `schemas/phase4_report.schema.json`
8. the latest Phase 3.1 validation report under `docs/phase3/runs/`

Where an older design sketch conflicts with the Phase 4 normative architecture document, `IDENTITY_AND_REFERENCE_RESOLUTION.md` governs Phase 4.

## 3. Scope

Implement only:

- Phase 4 preflight extraction-review workflow guards;
- canonical author identity persistence;
- name normalization and candidate generation;
- reversible identity link/merge/split/not-same-person/lock decisions;
- resolved authorships and first-author projection;
- corresponding-author/affiliation mapping from accepted evidence;
- local accepted-reference to local-paper resolution;
- deterministic review queues and real-library validation.

Do not implement frontend, FastAPI, graph visualization, broad author biography enrichment, portraits, social profiles, age/gender inference, monthly monitoring or general Internet research.

## 4. Safety and provenance

- Zotero `zotero.sqlite` and Zotero PDFs are read-only.
- Never rewrite source creator mentions to encode an identity decision.
- Never infer gender, age or demographic attributes from names/photos.
- A normalized-name match alone never auto-merges authors.
- Zotero `creatorID` is source provenance, not a person identifier.
- Only accepted PDF evidence may support authoritative corresponding-author/affiliation resolution.
- Only `paper_references.acceptance_status='ACCEPTED'` may enter reference resolution.
- Only accepted `paper_reference_matches` may later produce a `CITES` edge.
- Preserve ambiguous/unresolved outcomes instead of forcing a match.
- All merge/split decisions must be reversible and auditable.

## 5. Implementation order

Follow exactly:

```text
Preflight guards
  ↓
Phase 4A identity schema + normalization
  ↓
Phase 4B candidate resolution + reversible decisions + authorships
  ↓
Phase 4C corresponding/affiliation evidence resolution
  ↓
Phase 4D accepted local reference resolution
  ↓
real-library validation
```

Do not skip a gate. Do not start the next milestone until the current milestone tests pass.

## 6. Phase 4 preflight guards

Before identity work:

1. derive extraction `final_status` from the latest review decision rather than trusting a contradictory caller argument;
2. allow Attempt 2 only after Attempt 1 latest review is `RETRY`, and Attempt 3 only after Attempt 2 latest review is `RETRY`.

Add regression tests first or together with the fix.

## 7. Identity behavior

Use candidate generation + explicit decisions.

Strong evidence can justify automatic acceptance only when unique and contradiction-free. Name-only/common-name/initial-only matches must remain candidates/review-required.

Persist score components and evidence IDs. Do not hide reasoning in one opaque confidence number.

Manual `NOT_SAME_PERSON` and lock decisions must override future automatic suggestions until explicitly reversed/unlocked.

## 8. Reference behavior

Resolve accepted references conservatively using this ladder:

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED + corroboration
AUTHOR_YEAR_JOURNAL
JOURNAL_VOLUME_PAGE_YEAR
BIBLIOGRAPHIC_COMPOSITE
AI_RESOLVED if explicitly reviewed
UNRESOLVED
```

A DOI exact match must still be unique and contradiction-free. A title-only match is not enough for automatic acceptance.

Do not write graph edges in Phase 4.

## 9. Testing discipline

Use synthetic tests for systematic behavior. Do not commit the user's Zotero database or real PDFs as fixtures.

If a real-library failure exposes a general bug, create a synthetic regression test before changing production behavior.

The entire Phase 3 test suite must keep passing throughout Phase 4.

## 10. Real-library validation

Only after all unit/synthetic tests pass, run Phase 4 against the real Paperazzi/Zotero-derived corpus.

Coverage is not a PASS criterion by itself. Conservative unresolved results are valid.

PASS criteria emphasize:

- no false name-only auto-merges;
- identity decisions are reversible;
- corresponding-author assignments use accepted evidence;
- candidate PDF evidence is excluded;
- reference matching consumes only accepted references;
- ambiguous matches remain ambiguous;
- no duplicate decisions on rerun;
- FK integrity and provenance are intact.

Generate a machine-readable report conforming to `schemas/phase4_report.schema.json` plus a concise Markdown interpretation under `docs/phase4/runs/<run-id>/`.

## 11. Commit policy

Commit directly to `main` after each gate passes. Suggested messages:

```text
Phase 4 preflight: enforce extraction review workflow
Phase 4A: identity schema and normalization
Phase 4B: author identity resolution and reversible decisions
Phase 4C: authorship evidence resolution
Phase 4D: local reference resolution
Phase 4: real-library validation report
```

Do not create a PR or development branch.

## 12. Completion state

Do not declare completion until all gates pass and the final report validates:

```text
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```
