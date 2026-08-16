# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

The project treats Zotero's local `zotero.sqlite` database and `storage/` directory as read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 3 — Paperazzi persistence: ready to implement.**

Completed foundations:

```text
Phase 1   Zotero SQLite reconnaissance                         PASS
Phase 2   production read-only Zotero schema adapter/reader    PASS
Phase 2.5 local PDF evidence + AI-supervised adaptive parsing  PASS
           deterministic PDF baseline                          FROZEN_V3
```

Phase 3 now builds the first durable `paperazzi.sqlite3`: Zotero scan/diff state, current paper/creator/attachment projections, document availability, extraction attempts, evidence spans, raw reference sections/entries and provenance.

Start Phase 3 here:

- [`docs/phase3/README.md`](docs/phase3/README.md) — Phase 3 entry point.
- [`docs/architecture/PERSISTENCE_MODEL.md`](docs/architecture/PERSISTENCE_MODEL.md) — normative persistence schema and semantics.
- [`docs/phase3/PHASE3_IMPLEMENTATION.md`](docs/phase3/PHASE3_IMPLEMENTATION.md) — four gated implementation milestones and acceptance tests.
- [`prompts/local_ai/PHASE3_IMPLEMENTATION_AGENT.md`](prompts/local_ai/PHASE3_IMPLEMENTATION_AGENT.md) — operating prompt for the local implementation AI.
- [`schemas/phase3_report.schema.json`](schemas/phase3_report.schema.json) — final machine-readable validation report contract.
- [`DESIGN.md`](DESIGN.md) — overall system design; where its older v0.4 persistence sketch conflicts with the Phase 3 normative persistence document, `PERSISTENCE_MODEL.md` governs Phase 3.

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
│   └── phase3/
├── prompts/local_ai/
├── schemas/
├── src/paperazzi/
│   ├── zotero_sqlite/      # read-only Zotero access + schema adapters
│   ├── ingest/             # canonical records and scan/diff semantics
│   ├── local_evidence/     # frozen-v3 local PDF evidence extraction
│   ├── database/           # Phase 3 SQLAlchemy persistence
│   ├── identity/           # Phase 4
│   ├── enrichment/         # later online enrichment protocol
│   ├── graph/              # later derived graph
│   └── api/                # later backend API
├── migrations/             # Phase 3 Alembic migrations
├── frontend/               # later React/TypeScript web UI
├── scripts/
├── tests/
├── requests/
├── imports/
└── data/                   # local runtime state; ignored by Git
```

Only directories needed by the current phase need to exist. Zotero-specific SQL remains isolated inside `zotero_sqlite`; PDF parsing remains isolated inside `local_evidence`; Paperazzi persistence belongs in `database`.

## Phase 3 boundary

Phase 3 deliberately stores **paper-local creator mentions**, not resolved author identities. It also stores raw references without matching them to cited papers.

Author identity, author-affiliation/correspondence resolution, citation matching, graph construction, API/UI and online enrichment begin only after Phase 3 persistence passes.

## Safety rule

The Zotero source database and Zotero PDFs are **read only**. Any persistent state must write only to Paperazzi-owned paths.