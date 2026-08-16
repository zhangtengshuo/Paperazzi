# Paperazzi Local AI — Phase 4 identity stability and author-scope addendum

This file is normative for all remaining Phase 4 implementation and validation work and supplements `PHASE4_IMPLEMENTATION_AGENT.md`.

## 1. Complete author recording

Paperazzi records **every Zotero paper author**, not only first/corresponding authors.

```text
all creator_type='author' rows
        ↓
paper_creator_mentions            complete source record
        ↓
identity resolution
        ↓
authors + authorships             accepted semantic projection
```

Never discard, hide or skip an ordinary coauthor because that person is not an enrichment target. If canonical identity is unresolved, the source author mention remains authoritative as the paper-local authorship record.

Non-author creator types such as editor remain source creator records but are outside the canonical author resolver.

## 2. First/corresponding are additive roles

First and corresponding authors are not separate author classes.

They are authorships with extra role metadata:

```text
is_first_author
is_corresponding_author
corresponding_status
```

Every ordinary author remains available for publication lists, author ordering, coauthor relations and network analysis.

## 3. Later enrichment target

Broad public-profile enrichment is outside Phase 4. When it is implemented, the default proactive target is:

```text
first author OR corresponding author
```

Ordinary coauthors remain recorded but do not trigger broad biography/profile retrieval unless they become first/corresponding somewhere in the local corpus or the user explicitly requests it.

## 4. Immutable-source identity scoring

The Phase 4 deterministic resolver must not use its own accepted identity/authorship results as evidence for another automatic identity decision.

Forbidden scoring dependency:

```text
accepted canonical membership
        ↓
canonical coauthor neighborhood
        ↓
score another unresolved mention
```

This creates order-dependent positive feedback and was observed in the first real-library Stage 1 run: a second resolver pass appended 194 identity decisions.

The current resolver uses:

```text
src/paperazzi/identity/source_collaboration.py
src/paperazzi/identity/source_seed.py
src/paperazzi/identity/stable_bootstrap.py
```

Collaboration evidence must come only from immutable Phase-3 source projections (`paper_creator_mentions`) plus explicit authoritative manual/external evidence.

`source_creator_id` remains a source-local provenance key, not a person identifier. Automatic linking still requires compatible name evidence plus source reuse plus repeated collaboration evidence and the versioned score/margin thresholds.

## 5. No resolver-created evidence feedback

For the same Zotero snapshot, same manual locks/negative decisions and same policy version:

```text
same source corpus
        ↓
same source features
        ↓
same candidate scores
        ↓
same semantic result
```

A deterministic link created during one run must not enlarge another candidate's evidence.

Do not replace this rule with `while new links: rerun until convergence`. Fixed-point propagation can amplify an early false merge and is intentionally prohibited for deterministic author resolution.

## 6. Required stability gates

Synthetic tests must retain all of these properties:

```text
cascade-trap case resolves on first pass
second pass: created = 0
second pass: linked = 0
second pass: new decisions = 0
second pass: new memberships = 0
logical identity partition independent of input item order
NOT_SAME_PERSON remains authoritative
same-paper identity collisions never silently choose a winner
```

## 7. Real-library rerun rule

After any identity scoring/seed-policy change, rerun Stage 1 from a **fresh** Phase 4 validation database:

```bash
python scripts/validate_phase4.py
```

Do not use `--reuse-db` to validate a changed identity resolver. `--reuse-db` is reserved for continuing the same validated identity state after explicit PDF/reference anchor review.

The identity Stage 1 gate requires:

```text
duplicate_identity_decisions_on_rerun = 0
duplicate_identity_memberships_on_rerun = 0
name_only_auto_merges = 0
duplicate_active_memberships = 0
source_author_recording_complete = true
all_creator_recording_complete = true
```

Report candidate-membership count and unresolved-author-mention count separately.

## 8. Role coverage metrics

Real validation must expose at least:

```text
source_author_mentions
total_creator_mentions
accepted_memberships
candidate_memberships
unresolved_author_mentions
active authorships
papers_with_resolved_first_author
papers_with_unresolved_first_author
papers_with_accepted_corresponding_author
papers_without_accepted_corresponding_author
```

Corresponding-author zero coverage is acceptable before reviewed PDF evidence exists; never promote candidate evidence simply to improve coverage.
