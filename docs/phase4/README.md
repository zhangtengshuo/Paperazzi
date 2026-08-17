# Phase 4 — Identity and Resolution

**Status: PASS.** Phase 4 is closed; current development is Phase 5.

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```

Final closeout and real-library metrics are recorded in [`PHASE4_CLOSEOUT.md`](PHASE4_CLOSEOUT.md).

## Frozen semantics

Phase 4 established the conservative semantic layer above Phase 3 source records:

```text
paper_creator_mention
        ↓
identity candidate / decision
        ↓
canonical author

ACCEPTED paper_reference
        ↓
reference match candidate / decision
        ↓
local cited paper
```

A false author merge or false citation edge is worse than leaving data unresolved.

### Complete author coverage

Every Zotero `creator_type='author'` remains in `paper_creator_mentions`, whether canonical identity is resolved or not. `authors` + `authorships` are an accepted semantic projection, not the source author list.

First/corresponding status is additive role metadata:

```text
all source authors       always recorded
FIRST                    additional paper-specific role
CORRESPONDING            additional paper-specific role
```

Later broad profile enrichment defaults to first and corresponding authors; ordinary coauthors remain fully recorded in paper/network relations.

Normative detail: [`../architecture/AUTHOR_RECORDING_AND_ENRICHMENT_SCOPE.md`](../architecture/AUTHOR_RECORDING_AND_ENRICHMENT_SCOPE.md).

### Source-stable identity

Automatic identity scoring uses immutable source-corpus evidence. Resolver-generated canonical links do not become new evidence for later automatic links in the same or subsequent pass.

Validated invariants include:

```text
identity decisions added on immediate rerun   0
identity memberships added on rerun            0
name-only auto merges                          0
duplicate accepted membership per mention      0
```

Merge/split/unlink/relink, NOT_SAME_PERSON and lock/unlock history remain reversible and auditable.

### Reference semantics

Only `paper_references.acceptance_status='ACCEPTED'` may enter semantic reference resolution. Candidate/unreviewed references never do. Only accepted reference matches may later generate derived `CITES` edges; Phase 4 itself writes no graph edges.

**Zero accepted references is a valid corpus state.** It is represented as:

```text
REAL_REFERENCE_VALIDATION = NOT_APPLICABLE_NO_ACCEPTED_INPUT
```

There is no minimum real-reference quota. If accepted references naturally appear through the reviewed PDF workflow, the existing resolver and idempotency checks apply automatically.

## Final real-library baseline

```text
creator mentions                         12,381
author mentions                          12,207
non-author creators                         174
canonical authors                         7,398
accepted memberships                     10,448
unresolved author mentions                1,759
papers with source authors                2,485
resolved first-author papers              2,028
unresolved first-author papers              457
foreign-key violations                        0
```

The regression suite at Phase 4 closeout was 96/96 green; Phase 5 subsequently extended the suite.

## Historical implementation documents

The following describe how Phase 4 was built and should be read as historical implementation records where they conflict with the closeout decision above:

- `PHASE4_IMPLEMENTATION.md`
- `PHASE4_REAL_VALIDATION.md`
- `prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md`
- earlier run reports under `docs/phase4/runs/`

The closeout document and this README supersede any earlier requirement for a fixed count of accepted real references.