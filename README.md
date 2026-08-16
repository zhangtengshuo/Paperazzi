# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

The project treats Zotero's local `zotero.sqlite` database and `storage/` directory as read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 1 — Zotero SQLite reconnaissance.**

Before implementing the importer against assumptions about Zotero's internal schema, the repository contains a read-only probe that inspects a real local Zotero database, optionally creates a transaction-consistent SQLite snapshot, and emits Markdown/JSON reports for schema adaptation.

Start here:

- [`DESIGN.md`](DESIGN.md) — system design.
- [`docs/phase1/ZOTERO_SQLITE_PROBE.md`](docs/phase1/ZOTERO_SQLITE_PROBE.md) — first local test procedure.
- [`src/paperazzi/zotero_sqlite/probe.py`](src/paperazzi/zotero_sqlite/probe.py) — probe implementation.
- [`scripts/probe_zotero.py`](scripts/probe_zotero.py) — zero-install entry point.

## Planned repository layout

```text
Paperazzi/
├── DESIGN.md
├── README.md
├── pyproject.toml
├── docs/
│   ├── phase1/
│   └── architecture/
├── src/paperazzi/
│   ├── zotero_sqlite/      # read-only Zotero access + schema adapters
│   ├── ingest/             # canonical records and incremental import
│   ├── identity/           # author identity resolution
│   ├── database/           # Paperazzi DB models/migrations
│   ├── enrichment/         # online-AI request/result protocol
│   ├── graph/              # author/paper/institution relations
│   └── api/                # backend API
├── frontend/               # React/TypeScript web UI
├── scripts/                # operational entry points
├── tests/
├── requests/               # generated enrichment requests (ignored)
├── imports/                # returned enrichment packages (ignored)
└── data/                   # local databases/cache/snapshots (ignored)
```

Only directories needed by the current phase are created initially. Later phases should fill the planned modules without mixing Zotero-specific SQL into application logic.

## Safety rule

The Zotero source database is **read only**. Any code that needs persistent state must write to Paperazzi-owned paths only.
