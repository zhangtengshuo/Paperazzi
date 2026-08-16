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
│   │   ├── REPOSITORY_LAYOUT.md
│   │   ├── ZOTERO_DATA_BOUNDARY.md
│   │   └── LOCAL_PDF_EVIDENCE.md
│   ├── phase1/
│   ├── phase2/
│   └── phase2_5/
├── src/paperazzi/
│   ├── zotero_sqlite/
│   ├── ingest/
│   ├── local_evidence/
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

**Dependency rule:** no SQL referring to Zotero internal tables may appear outside this package.

### `src/paperazzi/ingest/`

Transforms Zotero-specific records into Paperazzi's stable canonical representation and computes scan-to-scan differences.

Core objects:

- `CanonicalZoteroItem`;
- `CanonicalCreator`;
- `CanonicalAttachment`;
- scan manifest;
- semantic content hashes;
- `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` diff.

This layer must not know how Zotero tables are joined.

### `src/paperazzi/local_evidence/`

Independent read-only evidence extraction from local documents. It must not contain Zotero SQL and must not mutate `CanonicalZoteroItem` to make PDF evidence look like Zotero metadata.

Initial responsibility:

```text
local_evidence/
└── pdf.py
```

- open local PDF files read-only;
- PyMuPDF text/blocks/metadata extraction;
- text-layer quality classification;
- first-page/front-matter evidence spans;
- affiliation/correspondence/e-mail candidates;
- reference-section detection;
- conservative reference segmentation;
- DOI/year extraction from references;
- non-fatal handling of missing/encrypted/scan-only/malformed PDFs.

Future adapters may include:

```text
zotero_fulltext_cache.py
ocr.py / mineru.py
```

All outputs are evidence with provenance. Semantic interpretation belongs in resolver/identity/graph layers.

### `src/paperazzi/identity/`

Author identity resolution and human overrides.

Responsibilities:

- normalized names/name variants;
- external-ID matching;
- coauthor/affiliation/topic evidence;
- local-PDF author/affiliation/correspondence evidence consumption;
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

Phase 3 must include first-class persistence for:

```text
paper_documents
document_evidence_spans
paper_references
paper_reference_matches
```

rather than hiding PDF-derived evidence in opaque JSON.

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
- accepted paper-to-paper `CITES` edges from `paper_reference_matches`;
- citation-derived author relations;
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
- network/citation explorer queries;
- review center actions;
- local PDF open/serve actions;
- update/extraction run status.

It must call domain/service layers rather than embedding SQL, PDF parsing, or AI logic in route handlers.

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
│   ├── citations/
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

Thin operational/validation entry points only. Business logic belongs in `src/paperazzi/`.

Current examples:

```text
probe_zotero.py
validate_zotero_reader.py
validate_pdf_evidence.py
```

### `tests/`

Mirrors backend modules. Real Zotero databases and user PDFs must never become committed test fixtures. Synthetic PDFs may be generated inside temporary directories during tests.

### `requests/`, `imports/`, `data/`

Local runtime working directories:

- `requests/` — generated packages for online AI;
- `imports/` — returned packages awaiting/after validation;
- `data/` — Paperazzi database, snapshots, evidence caches, generated assets.

Their runtime contents are ignored by Git.

## Dependency direction

Preferred dependency flow:

```text
zotero_sqlite ──> ingest ──────────────┐
                                        ├──> identity ──> database
local_evidence ─────────────────────────┤
                                        ├──> graph ─────> database
                                        └──> enrichment -> database

api ──> service/domain layers above
frontend ──HTTP──> api
```

More precisely:

- `zotero_sqlite` may know Zotero tables but not AI/PDF semantics;
- `local_evidence` may know PDF/text extraction but not Zotero tables;
- identity/graph/resolver layers are where these evidence channels meet;
- `database` persists accepted facts and evidence provenance.

Domain dataclasses/interfaces may later be factored into a small `domain/` package if circular dependencies emerge. Do not create that abstraction prematurely.

## Development phases

1. **Phase 1 — SQLite reconnaissance** — complete.
2. **Phase 2 — Zotero schema adapter + canonical reader** — complete after correctness fixes.
3. **Phase 2.5 — Local PDF Evidence validation** — current.
4. **Phase 3 — Paperazzi relational schema + incremental scan state + PDF evidence/reference persistence.**
5. **Phase 4 — author identity + local/online semantic resolution.**
6. **Phase 5 — minimal backend + author/paper/citation web UI + Open PDF.**
7. **Phase 6 — enrichment protocol, advanced relationship/citation graph, monthly watch and library-gap detection.**

Each phase must leave an auditable deterministic path from source evidence to stored facts.
