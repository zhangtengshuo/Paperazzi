# Provenance and Retraction Architecture

## Purpose

Paperazzi must be able to answer two questions for every non-Zotero fact:

1. **Why is this fact currently believed?**
2. **If an upstream parse/source is later found wrong, exactly which downstream facts must stop being current?**

Corrections are therefore implemented as provenance-aware invalidation plus projection recomputation, not destructive deletion.

## Core invariant

> Raw source/extraction history is retained. Derived current facts are disposable projections over currently valid evidence.

A parser, local AI, online enrichment source, or manual operation must never create an irreversible fact whose source cannot be identified later.

## Current PDF lineage

The existing persistence model already records:

```text
PaperDocument
  -> DocumentExtractionRun
     -> DocumentExtractionAttempt
        -> DocumentEvidenceSpan
        -> PaperReferenceSection
           -> PaperReference
```

Downstream authorship evidence records `evidence_span_id`. References record their originating attempt/document. This lineage is now complemented by explicit retraction history.

## Document roles

PDF attachments belonging to one Zotero paper are not semantically equivalent.

```text
PRIMARY_ARTICLE
SUPPLEMENTARY
UNKNOWN
```

A `DocumentRole` row may be produced by `MANUAL` or `LOCAL_AI` authority. When no persisted row exists, Paperazzi uses a conservative filename classifier. Explicit stored roles always override heuristic roles.

The default filename classifier recognizes common SI/ESI/supplement markers. A PDF without such a marker is only a primary candidate; it does not become an immutable truth.

### Role policy

`SUPPLEMENTARY` documents:

- remain recorded and may retain raw extraction history;
- are not allowed to establish paper-level corresponding-author or affiliation roles;
- are not preferred by `Open local PDF` when an article/unknown candidate exists;
- may have paper-level derivations retracted when reclassified from a previously usable role.

Future evidence types may define their own role policy. Do not globally discard SI content.

## Retraction ledger

Two append-only tables record corrections.

### `retraction_events`

Records the root correction:

```text
root_type
root_id
scope
reason_code
reason_text
actor
created_at
```

Current roots include documents and extraction attempts.

### `retraction_impacts`

Records every downstream state change caused by the event:

```text
retraction_id
entity_type
entity_id
action
previous_state_json
resulting_state_json
```

This is the audit trail for answering “what changed because this source/parse was withdrawn?”

## Retraction semantics

### Document-level retraction

When a document is confirmed as supplementary, `set_document_role(..., SUPPLEMENTARY)` can trigger `retract_document_derivations()`.

The current implementation:

- keeps raw `DocumentEvidenceSpan` history;
- supersedes live `AuthorshipEvidence` derived from those spans;
- supersedes live reference sections/references from that document;
- rejects candidate/accepted reference matches derived from those references;
- dismisses now-invalid evidence-span review items;
- recomputes affected corresponding-author projections from remaining accepted evidence.

This scope is intentionally `PAPER_LEVEL_DERIVATIONS`: SI extraction itself is not erased.

### Attempt-level retraction

`retract_extraction_attempt()` is used when the **parse itself** is wrong.

It additionally supersedes the attempt's raw evidence outputs and clears the accepted-attempt pointer if that attempt was current. The extraction run becomes `UNRESOLVED` until a new reviewed attempt replaces it.

## Multi-source rule

Retraction of one source must not erase a fact supported independently by another valid source.

Example:

```text
main article evidence A -> corresponding author X
SI evidence B           -> corresponding author X
```

If B is withdrawn, A remains accepted, so the current projection remains `CORRESPONDING`.

Projection recomputation must always query remaining valid evidence rather than blindly toggling a boolean off.

## Status compatibility

Existing Phase 3/4 tables constrain evidence status to values such as `ACCEPTED`, `REJECTED`, and `SUPERSEDED`. Retraction therefore uses those existing storage states for compatibility and records the distinct semantic reason in `RetractionEvent`/`RetractionImpact` with action `INVALIDATE`.

Do not infer “ordinary version supersession” and “confirmed error withdrawal” from the status column alone; consult the retraction ledger.

## No automatic resurrection

Changing a document from `SUPPLEMENTARY` back to `PRIMARY_ARTICLE` does **not** reactivate superseded evidence. A new/reviewed extraction must recreate valid current evidence. This prevents an accidental role toggle from reviving a previously withdrawn bad parse.

## Operator interface

Use:

```text
scripts/manage_provenance.py
```

Mutating commands require an explicit `--apply` flag. Without it the tool emits a dry-run proposal.

Supported operations:

```text
inspect-paper
inspect-attempt
set-document-role
retract-attempt
```

The tool operates only on the Paperazzi-owned database and never writes Zotero.

## Extension to enrichment

Phase 6 enrichment should reuse the same principle. Online/local-AI results should be persisted as sourced assertions/run outputs first; visible author profile fields should be current projections over valid assertions.

Future enrichment design should support:

```text
EnrichmentRun
 -> sourced assertions
 -> provenance links
 -> current profile projection
```

A wrong-person enrichment run must then be retractable without manually editing each resulting affiliation, education, portrait, or public-profile field.

## Required invariants for tests

1. Every retraction creates an event.
2. Every changed downstream row has an impact record.
3. No raw source/extraction history is physically deleted by correction operations.
4. A supplementary document cannot create paper-level corresponding-author truth.
5. Retracting one of several independent evidence sources preserves a still-supported projection.
6. Retracting the last accepted corresponding-author evidence removes the current corresponding projection.
7. A bad accepted attempt can be withdrawn without losing its historical record.
8. Zotero source data is never mutated.
