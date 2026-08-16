# Paperazzi repository architecture

This document fixes the repository/module boundaries before feature development expands.

## Top-level layout

```text
Paperazzi/
├── README.md
├── DESIGN.md
├── pyproject.toml
├── docs/
│   ├── architecture/
│   │   └── REPOSITORY_LAYOUT.md
│   └── phase1/
│       └── ZOTERO_SQLITE_PROBE.md
├── src/paperazzi/
│   ├── zotero_sqlite/
│   ├── ingest/
│   ├── identity/
│   ├── database/
│   ├── enrichment/
│   ├── graph/
│   └── api/
├── frontend/
├── scripts/
├── tests/
├── requests/
├── imports/
└── data/
```

Git does not preserve empty directories, so modules are created only when their first implementation file is added.

## Module responsibilities

### `src/paperazzi/zotero_sqlite/`

The only module allowed to know Zotero's internal SQLite schema.

Responsibilities:

- discover/configure the Zotero data directory;
- open `zotero.sqlite` strictly read-only;
- create transaction-consistent snapshots;
- probe schema/version compatibility;
- execute Zotero-specific SQL;
- resolve imported and linked attachment paths;
- expose stable Python records to `ingest`.

Future internal shape:

```text
zotero_sqlite/
├── source.py
├── snapshot.py
├── schema_probe.py
├── reader.py
├── attachments.py
└── adapters/
    ├── __init__.py
    └── zotero_<schema>.py
```

**Dependency rule:** no SQL referring to Zotero internal tables may appear outside this package.

### `src/paperazzi/ingest/`

Transforms Zotero-specific records into Paperazzi's stable canonical representation and computes scan-to-scan differences.

Planned objects:

- `CanonicalZoteroItem`;
- `CanonicalCreator`;
- `CanonicalAttachment`;
- scan manifest;
- content hashes;
- `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` diff.

This layer must not know how Zotero tables are joined.

### `src/paperazzi/identity/`

Author identity resolution and human overrides.

Responsibilities:

- normalized names/name variants;
- external-ID matching;
- coauthor/affiliation/topic evidence;
- candidate scoring;
- merge/split/not-same-person rules;
- identity locks;
- provenance for identity decisions.

Identity resolution never edits Zotero creators.

### `src/paperazzi/database/`

Paperazzi-owned persistence.

Responsibilities:

- SQLAlchemy models;
- Alembic migrations;
- repositories/query layer;
- transaction boundaries;
- Paperazzi DB schema versioning.

The primary database will initially be SQLite. The domain model should not depend on SQLite-specific behavior where avoidable.

### `src/paperazzi/enrichment/`

Offline/online AI interchange.

Responsibilities:

- generate enrichment/update requests;
- JSON Schemas for request/result contracts;
- ZIP manifest validation;
- evidence/claim validation;
- asset ingestion;
- conflict generation;
- deterministic merge proposals.

AI output is never granted direct database write access.

### `src/paperazzi/graph/`

Derived scholarly graph.

Responsibilities:

- coauthorship edges;
- first-author/corresponding-author relations;
- advisor/student and institution relations when evidenced;
- collaboration weights/time decay;
- topic similarity;
- path queries;
- graph projection payloads for the frontend.

The authoritative facts remain in normal relational tables; graph structures are derived views/caches in v1.

### `src/paperazzi/api/`

FastAPI application exposed to the local web frontend.

Responsibilities:

- author/paper/institution/topic endpoints;
- search;
- network explorer queries;
- review center actions;
- local PDF open/serve actions;
- update-run status.

It must call domain/service layers rather than embedding SQL or AI logic in route handlers.

### `frontend/`

React + TypeScript application.

Planned feature-oriented layout:

```text
frontend/src/
├── app/
├── features/
│   ├── dashboard/
│   ├── authors/
│   ├── papers/
│   ├── network/
│   ├── topics/
│   ├── institutions/
│   ├── updates/
│   └── review/
├── components/
└── lib/
```

Network visualization is a UI projection of backend graph data, not a second source of truth.

### `scripts/`

Thin operational entry points only. Business logic belongs in `src/paperazzi/`.

### `tests/`

Mirrors backend modules. Real Zotero databases and user PDFs must never become test fixtures in Git.

### `requests/`, `imports/`, `data/`

Local runtime working directories:

- `requests/` — generated packages for online AI;
- `imports/` — returned packages awaiting/after validation;
- `data/` — Paperazzi database, snapshots, caches, generated assets.

Their runtime contents are ignored by Git.

## Dependency direction

Preferred dependency flow:

```text
zotero_sqlite ──> ingest ──> identity ──> database
                         └──> enrichment ──> database
                         └──> graph ───────> database

api ──> service/domain layers above
frontend ──HTTP──> api
```

More precisely, domain dataclasses/interfaces may later be factored into a small `domain/` package if circular dependencies emerge. Do not create that abstraction prematurely.

## Development phases

1. **SQLite reconnaissance** — current phase.
2. **Zotero schema adapter + canonical importer.**
3. **Paperazzi relational schema + incremental scan state.**
4. **Author identity resolution.**
5. **Minimal backend + author/paper web UI + Open PDF.**
6. **AI enrichment request/result protocol + Review Center.**
7. **Relationship graph and research-topic timeline.**
8. **Monthly author watch / library-gap detection.**

Each phase must leave an auditable deterministic path from source evidence to stored facts.
