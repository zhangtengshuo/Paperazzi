# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

The project treats Zotero's local `zotero.sqlite` database and `storage/` directory as read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 5 — Backend and minimal web UI: IN PROGRESS.**

Completed foundations:

```text
Phase 1   Zotero SQLite reconnaissance                         PASS
Phase 2   production read-only Zotero schema adapter/reader    PASS
Phase 2.5 local PDF evidence + AI-supervised adaptive parsing  PASS
           deterministic PDF baseline                          FROZEN_V3
Phase 3   relational persistence + incremental scan state      PASS
Phase 3.1 persistence hardening                                PASS
           database schema                                     PHASE3_V1
Phase 4   author identity + authorship/reference resolution    PASS
           author identity model                               PHASE4_V1
           reference resolution model                          PHASE4_V1
```

Phase 4 closeout is documented in [`docs/phase4/PHASE4_CLOSEOUT.md`](docs/phase4/PHASE4_CLOSEOUT.md). Zero accepted references is a valid corpus state; Paperazzi does not manufacture reviewed references to satisfy a quota.

## Phase 5 MVP

The first usable browser product is now being implemented directly on `main`.

Current Phase 5 surface:

```text
PaperazziQueryService
FastAPI backend
paper list + paper detail
ALL source authors displayed, including unresolved identity
FIRST / CORRESPONDING additive role labels
author profile + publication chronology
coauthor listing
identity review queue
paper/author/DOI/journal search
local PDF open endpoint
minimal dependency-free browser UI
```

Install the web extra:

```bash
python -m pip install -e ".[pdf,web]"
```

Start Paperazzi:

```bash
paperazzi-web
```

Default address:

```text
http://127.0.0.1:8765
```

Default database:

```text
data/paperazzi.sqlite3
```

Override it with `PAPERAZZI_DB=/path/to/paperazzi.sqlite3`.

Phase 5 entry point:

- [`docs/phase5/README.md`](docs/phase5/README.md) — backend/UI architecture, API surface and run instructions.
- [`docs/architecture/AUTHOR_RECORDING_AND_ENRICHMENT_SCOPE.md`](docs/architecture/AUTHOR_RECORDING_AND_ENRICHMENT_SCOPE.md) — all-author recording vs priority enrichment semantics.
- [`docs/phase4/PHASE4_CLOSEOUT.md`](docs/phase4/PHASE4_CLOSEOUT.md) — frozen Phase 4 completion state.

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
│   ├── phase4/
│   └── phase5/
├── prompts/local_ai/
├── schemas/
├── src/paperazzi/
│   ├── zotero_sqlite/      # read-only Zotero access + schema adapters
│   ├── ingest/             # canonical records and scan/diff semantics
│   ├── local_evidence/     # frozen-v3 local PDF evidence extraction
│   ├── database/           # Paperazzi persistence + extraction workflow
│   ├── identity/           # identity/authorship/reference resolution
│   └── web/                # Phase 5 query service, FastAPI and minimal UI
├── migrations/
├── scripts/
├── tests/
├── requests/
├── imports/
└── data/                   # local runtime state; ignored by Git
```

Zotero-specific SQL remains isolated inside `zotero_sqlite`; PDF parsing remains isolated inside `local_evidence`; Paperazzi-owned persistence belongs in `database`; identity and semantic resolution belong in `identity`; product read semantics belong in the Phase 5 query/service layer.

## Core semantic boundaries

```text
paper_creator_mention != canonical author
paper_reference       != cited paper
```

Every Zotero paper author is retained and shown even when canonical identity is unresolved. First/corresponding status is additive role metadata, not an author-inclusion filter. Normalized names may generate identity candidates but may not by themselves auto-merge authors. Only accepted PDF/reference evidence may participate as authoritative semantic evidence. Only accepted reference matches may later produce derived `CITES` edges.

Broad public-profile enrichment is a later phase and defaults to first and corresponding authors; ordinary coauthors remain fully recorded in paper/author/network relations without proactive biographical enrichment.

## Safety rule

The Zotero source database and Zotero PDFs are **read only**. Any persistent state must write only to Paperazzi-owned paths.