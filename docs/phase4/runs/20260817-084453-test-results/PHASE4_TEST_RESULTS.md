# Phase 4 Test Results

Date: 2026-08-17 08:44:53 Asia/Shanghai
Tested commit: `a010cde Update Phase 4 real validation for source-stable identity and all-author coverage`

## Regression tests

```text
python -m unittest discover -s tests -v
96 passed, 0 failed, 0 skipped
```

The suite includes the source-stable identity tests, including cascade convergence, strict rerun idempotency, input-order independence, complete author recording and additive role semantics.

## Real-library Stage 1 validation

- Migration head: `0005_identity_history_constraints (head)`
- Creator mentions: 12,381 total; 12,207 author mentions and 174 non-author creators
- Canonical authors: 7,398
- Accepted memberships: 10,448
- Candidate/unresolved author mentions: 1,759
- Active authorships: 10,448
- Papers with source authors: 2,485
- Resolved first-author rows: 2,028; unresolved first-author rows: 457
- Source/all-author recording: complete
- `PRAGMA foreign_key_check`: 0 rows
- Duplicate active memberships: 0
- Name-only auto-merges: 0
- Candidate reference inputs matched: 0
- Direct `CITES` edges written: 0

## Idempotency and reversibility

```text
duplicate_identity_decisions_on_rerun = 0
duplicate_identity_memberships_on_rerun = 0
duplicate_reference_matches_on_rerun = 0
identity_rerun_idempotency = PASS
merge_split_roundtrip = PASS
manual_lock = PASS
```

## Final status

The Stage 1 script reports `FAIL` only because there are currently 0 `ACCEPTED` references, while the final real-reference gate requires at least 5 reviewed references. This is the remaining validation gate; identity stability and database integrity pass.

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
PHASE_4_STATUS = IN_PROGRESS
REMAINING_GATE = 5_ACCEPTED_REAL_REFERENCES
```
