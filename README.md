# Paperazzi

Paperazzi is a local-first scholarly author knowledge base built around a personal Zotero library.

Zotero's local `zotero.sqlite`, `storage/`, and PDF files are read-only source data. Paperazzi maintains its own database and never writes to Zotero.

## Current status

**Phase 5 — Backend and minimal web UI: IN PROGRESS.**

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
Phase 5   backend + minimal web UI                             IN_PROGRESS
```

Phase 4 closeout: `docs/phase4/PHASE4_CLOSEOUT.md`.

## Mandatory local Python environment

Local Paperazzi development, real-database validation, Zotero/PDF integration tests, and local-AI execution **must use a dedicated micromamba environment named `Paperazzi`**.

The user's existing Anaconda `base` or other general-purpose Python environments are not Paperazzi dependency targets and must not be upgraded, downgraded, or otherwise modified for this project.

Canonical local environment:

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
dependency baseline = constraints/phase5-test.txt
```

Create the environment from the repository root:

```bash
micromamba create -y -f environment/Paperazzi.yml
micromamba run -n Paperazzi python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The third command must report `"pass": true` before authoritative local testing begins. If an environment named `Paperazzi` already exists, repair or update that environment only; do not delete or modify unrelated environments.

GitHub Actions is already an isolated ephemeral environment and is not required to use micromamba. CI currently validates the canonical dependency set on Python 3.11 and 3.13.

## Phase 5 MVP

Current surface:

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

Start Paperazzi without activating or modifying another Python environment:

```bash
micromamba run -n Paperazzi paperazzi-web
```

Default address: `http://127.0.0.1:8765`

Default database: `data/paperazzi.sqlite3`

Override it with `PAPERAZZI_DB=/path/to/paperazzi.sqlite3`.

## Phase 5 validation

All authoritative local commands should be executed through `micromamba run -n Paperazzi ...`.

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3
```

Environment and validation contracts:

- `environment/Paperazzi.yml`
- `constraints/phase5-test.txt`
- `scripts/check_paperazzi_environment.py`
- `docs/phase5/PHASE5_TESTING.md`
- `prompts/local_ai/PHASE5_REAL_DB_TEST_AGENT.md`

## Repository layout

```text
Paperazzi/
├── DESIGN.md
├── README.md
├── pyproject.toml
├── environment/
│   └── Paperazzi.yml
├── constraints/
├── docs/
├── prompts/local_ai/
├── schemas/
├── src/paperazzi/
│   ├── zotero_sqlite/
│   ├── ingest/
│   ├── local_evidence/
│   ├── database/
│   ├── identity/
│   └── web/
├── migrations/
├── scripts/
├── tests/
├── requests/
├── imports/
└── data/
```

## Core semantic boundaries

```text
paper_creator_mention != canonical author
paper_reference       != cited paper
```

Every Zotero paper author is retained and shown even when canonical identity is unresolved. First/corresponding status is additive role metadata, not an author-inclusion filter. Normalized names may generate identity candidates but may not by themselves auto-merge authors. Only accepted PDF/reference evidence may participate as authoritative semantic evidence. Only accepted reference matches may later produce derived `CITES` edges.

Broad public-profile enrichment is a later phase and defaults to first and corresponding authors; ordinary coauthors remain fully recorded in paper/author/network relations without proactive biographical enrichment.

## Safety rule

Zotero source data are read-only. Persistent state may write only to Paperazzi-owned paths. Local environment setup may modify only the dedicated micromamba environment `Paperazzi`, never the user's existing Anaconda/base environment.
