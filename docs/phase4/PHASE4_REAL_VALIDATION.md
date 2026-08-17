# Phase 4 — Real-library validation

**Archived final semantics.** Phase 4 is PASS; see `PHASE4_CLOSEOUT.md`.

## Validation command

A fresh validation run remains available for diagnostics:

```bash
python scripts/validate_phase4.py
```

It validates:

- migration head and foreign keys;
- complete Zotero creator/author recording;
- conservative source-stable identity resolution;
- immediate rerun idempotency;
- duplicate accepted-membership protection;
- name-only auto-merge protection;
- candidate-PDF evidence isolation;
- accepted-reference-only semantic matching;
- reference resolver rerun idempotency;
- absence of direct Phase 4 `CITES` materialization.

## Accepted references

There is **no minimum accepted-reference count**.

```text
eligible ACCEPTED references = 0
    → REAL_REFERENCE_VALIDATION = NOT_APPLICABLE_NO_ACCEPTED_INPUT
    → valid corpus state

eligible ACCEPTED references > 0
    → resolver executes normally
    → safety + idempotency invariants apply
```

Paperazzi never promotes candidate PDF/reference data merely to create validation input.

Historical anchor utilities (`seed_phase4_reference_anchors.py`, `apply_phase4_anchor_reviews.py`) remain available for targeted diagnostics, but they are not Phase 4 completion requirements.

## Frozen real-library closeout baseline

```text
12,381 total creator mentions
12,207 source author mentions
7,398 canonical authors
10,448 accepted memberships
1,759 unresolved author mentions
2,485 papers with source authors
2,028 papers with resolved first author
457 papers with unresolved first author
0 foreign-key violations
0 duplicate active memberships
0 name-only auto-merges
0 identity decisions on immediate rerun
0 identity memberships on immediate rerun
0 candidate reference inputs matched
0 direct CITES edges
```

## Status

```text
PHASE_4_STATUS = PASS
AUTHOR_IDENTITY_MODEL = PHASE4_V1
REFERENCE_RESOLUTION_MODEL = PHASE4_V1
NEXT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
```
