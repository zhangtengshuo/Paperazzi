# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

The project treats Zotero's local `zotero.sqlite` database and `storage/` directory as read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 4 — Author identity and local reference resolution: IN PROGRESS.**

Completed foundations:

```text
Phase 1   Zotero SQLite reconnaissance                         PASS
Phase 2   production read-only Zotero schema adapter/reader    PASS
Phase 2.5 local PDF evidence + AI-supervised adaptive parsing  PASS
           deterministic PDF baseline                          FROZEN_V3
Phase 3   relational persistence + incremental scan state      PASS
Phase 3.1 persistence hardening                                PASS
           database schema                                     PHASE3_V1
```

Phase 4 runtime implementation has started directly on `main`.

Implemented Phase 4 surface currently includes:

```text
0004_identity_resolution
0005_identity_history_constraints

canonical authors + name variants + external IDs
creator-mention identity memberships/decisions/evidence
conservative name/coauthor candidate resolution
reversible link/unlink/merge/split/not-same-person/lock operations
authorship projection and first-author status
accepted-PDF corresponding/affiliation evidence mapping
accepted-reference-only local paper resolution
DOI/title/author-year-journal/journal-volume-page-year match classes
versioned resolution thresholds
review queues
Phase 4 synthetic/regression tests
staged real-library validation tooling
```

Phase 4 is **not yet declared PASS**. The new code must pass the full local test suite and staged real-library validation, including explicitly reviewed real PDF/reference anchors.

Phase 4 entry points:

- [`docs/phase4/README.md`](docs/phase4/README.md) — Phase 4 entry point and hard branch policy.
- [`docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md`](docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md) — normative identity/reference semantics.
- [`docs/phase4/PHASE4_IMPLEMENTATION.md`](docs/phase4/PHASE4_IMPLEMENTATION.md) — implementation plan and gates.
- [`docs/phase4/PHASE4_REAL_VALIDATION.md`](docs/phase4/PHASE4_REAL_VALIDATION.md) — staged real-library validation workflow.
- [`prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md`](prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md) — current parallel implementation/validation instructions.
- [`prompts/local_ai/PDF_EVIDENCE_AGENT.md`](prompts/local_ai/PDF_EVIDENCE_AGENT.md) — mandatory PDF review contract.
- [`schemas/phase4_report.schema.json`](schemas/phase4_report.schema.json) — final validation report contract.
- [`schemas/phase4_anchor_reviews.schema.json`](schemas/phase4_anchor_reviews.schema.json) — explicit anchor-review interchange contract.
- [`docs/architecture/PERSISTENCE_MODEL.md`](docs/architecture/PERSISTENCE_MODEL.md) — frozen Phase 3 persistence semantics that Phase 4 must preserve.

## Phase 4 branch policy

**Phase 4 is developed directly on `main`. Do not create new development branches or PR branches.**

Independent implementation tasks may proceed in parallel when they have no real dependency, but integration correctness and final validation gates remain mandatory.

## Repository layout

```text
Paperazzi/
├── DESIGN.md
├── README.md
├── pyproject.toml
├── docs/
│   ├── architecture/
│   ├── phase1/
│   ├── phase2/
│   ├── phase2_5/
│   ├── phase3/
│   └── phase4/
├── prompts/local_ai/
├── schemas/
├── src/paperazzi/
│   ├── zotero_sqlite/      # read-only Zotero access + schema adapters
│   ├── ingest/             # canonical records and scan/diff semantics
│   ├── local_evidence/     # frozen-v3 local PDF evidence extraction
│   ├── database/           # PHASE3_V1 persistence + extraction workflow
│   ├── identity/           # Phase 4 identity/authorship/reference resolution
│   ├── enrichment/         # later online enrichment protocol
│   ├── graph/              # later derived graph
│   └── api/                # later backend API
├── migrations/
├── frontend/               # later React/TypeScript web UI
├── scripts/
├── tests/
├── requests/
├── imports/
└── data/                   # local runtime state; ignored by Git
```

Zotero-specific SQL remains isolated inside `zotero_sqlite`; PDF parsing remains isolated inside `local_evidence`; Paperazzi-owned persistence belongs in `database`; identity and semantic resolution belong in `identity`/resolver services.

## Phase 4 boundary

Phase 4 deliberately separates source records from semantic decisions:

```text
paper_creator_mention != canonical author
paper_reference       != cited paper
```

Normalized names may generate identity candidates but may not by themselves auto-merge authors. Only accepted PDF/reference evidence may participate as authoritative semantic evidence. Only accepted reference matches may later produce derived `CITES` edges.

Broad author profile enrichment (photos, education, social profiles, age/gender, monthly monitoring), graph visualization, API and frontend are later phases.

## Safety rule

The Zotero source database and Zotero PDFs are **read only**. Any persistent state must write only to Paperazzi-owned paths.
