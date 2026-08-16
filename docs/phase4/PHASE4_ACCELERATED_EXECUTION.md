# Phase 4 accelerated execution policy

This file defines the execution-order policy for the active Phase 4 implementation.

## Branch rule

**Phase 4 is main-only. Do not create a new branch or PR branch.**

All implementation, tests, fixes, validation tooling and reports are committed directly to `main`.

## Parallel implementation rule

The user explicitly requested aggressive progress. Therefore independent Phase 4 tasks should proceed in parallel whenever there is no real data-contract dependency.

Examples that may proceed concurrently:

```text
identity schema / ORM
name normalization
identity candidate scoring
manual correction operations
authorship evidence mapping
reference matching
review queues
synthetic tests
validation/report tooling
documentation
```

A milestone number such as `4A`, `4B`, `4C` or `4D` describes a logical responsibility and final gate. It does **not** require all implementation work to wait serially for the previous milestone when the code has no hard dependency.

Where older Phase 4 wording implies a strictly serial implementation order, **this execution policy governs the active Phase 4 work**.

## Gated integration rule

Parallel implementation does not weaken correctness requirements.

```text
parallel implementation
        ↓
continuous unit/regression CI
        ↓
integration fixes
        ↓
local real-library staged validation
        ↓
Phase 4 PASS
```

Hard dependencies remain hard dependencies. Examples:

- authoritative corresponding-author claims require accepted PDF evidence;
- semantic citation matching requires `paper_reference.acceptance_status='ACCEPTED'`;
- final real-reference validation requires explicit PDF review anchors;
- graph/CITES materialization remains outside Phase 4.

No task may bypass provenance or acceptance state merely to unblock another task.

## Current status

```text
CURRENT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
PHASE_4_STATUS = IN_PROGRESS
```

The implementation may advance broadly in parallel, but `PHASE_4_STATUS = PASS` is written only after the complete synthetic suite and staged real-library validation both pass.
