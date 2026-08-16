# Phase 4 Stage 1 Status

Date: 2026-08-17 05:02:30 Asia/Shanghai

## Current repository

- Branch: `main`
- Local/remote commit: `ae3019c Document accelerated parallel Phase 4 execution policy`
- Local `main` is synchronized with `origin/main`.
- No tracked code changes are pending. The existing `pdf-evidence-output/` and `phase2-output/` directories remain untracked and were not included.

## Tests and schema

- Full regression suite: **92 passed, 0 failed**.
- Migration head: `0005_identity_history_constraints (head)`.
- `PRAGMA foreign_key_check`: 0 rows.
- Reversibility checks: merge/split and manual-lock behavior passed.

## Stage 1 real-library validation

The fresh validation database imported 12,381 creator mentions and produced:

- 7,482 canonical authors;
- 9,750 accepted memberships;
- 2,631 candidate memberships / unresolved mentions;
- 9,750 active authorships;
- 1,914 first-author rows;
- 0 candidate-evidence corresponding-author assignments;
- 0 duplicate active memberships;
- 0 candidate reference inputs matched.

The overall Stage 1 report is `FAIL` because identity rerun idempotency is not yet satisfied:

```text
duplicate_identity_decisions_on_rerun = 194
duplicate_identity_memberships_on_rerun = 0
duplicate_reference_matches_on_rerun = 0
```

The second identity pass linked 194 previously-candidate mentions and appended decisions. This must be resolved before declaring the real-library identity gate passed. The absence of `ACCEPTED` references is recorded separately and is not treated as the current blocker; it only prevents the final real-reference minimum gate.

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
PHASE_4_STATUS = IN_PROGRESS
BLOCKER = IDENTITY_RERUN_IDEMPOTENCY
```
