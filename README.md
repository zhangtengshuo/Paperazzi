# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

The project treats Zotero's local `zotero.sqlite` database and `storage/` directory as read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 4 — Author identity and local reference resolution: ready to implement.**

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

Phase 4 resolves paper-local creator mentions into reversible canonical author identities, projects authorships/roles from accepted evidence, and resolves accepted local reference entries to papers already present in the Paperazzi corpus.

Start Phase 4 here:

- [`docs/phase4/README.md`](docs/phase4/README.md) — Phase 4 entry point and hard branch policy.
- [`docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md`](docs/architecture/IDENTITY_AND_REFERENCE_RESOLUTION.md) — normative identity/reference semantics.
- [`docs/phase4/PHASE4_IMPLEMENTATION.md`](docs/phase4/PHASE4_IMPLEMENTATION.md) — gated Phase 4 implementation plan.
- [`prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md`](prompts/local_ai/PHASE4_IMPLEMENTATION_AGENT.md) — operating prompt for the local implementation AI.
- [`schemas/phase4_report.schema.json`](schemas/phase4_report.schema.json) — final machine-readable validation contract.
- [`docs/architecture/PERSISTENCE_MODEL.md`](docs/architecture/PERSISTENCE_MODEL.md) — frozen Phase 3 persistence semantics that Phase 4 must preserve.

## Phase 4 branch policy

**Phase 4 is developed directly on `main`. Do not create new development branches or PR branches.**

All Phase 4 code, tests, documentation and validation reports are committed directly to `main` after their milestone tests pass. This project-specific rule overrides generic agent conventions that prefer feature branches.

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
│   ├── database/           # PHASE3_V1 persistence
│   ├── identity/           # Phase 4 identity/resolution logic
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
