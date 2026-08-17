# Phase 5 — Backend and Minimal Web UI

## Objective

Turn the validated Paperazzi database into a usable local research tool without changing the source/provenance semantics established in Phases 1–4.

```text
open browser
  ↓
search papers / authors
  ↓
open paper
  ↓
see ALL source authors, including unresolved identities
  ↓
open resolved author profile
  ↓
see publications + roles + coauthors
  ↓
open local PDF when available
```

## Architecture

```text
paperazzi.sqlite3
    ↓
PaperazziQueryService
    ↓
FastAPI
    ↓
minimal browser UI
```

The query/service layer is authoritative for read semantics. HTTP handlers stay thin.

## Mandatory local environment

All local Phase 5 development and real-database validation must run in a dedicated micromamba environment named `Paperazzi`.

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
dependency baseline = constraints/phase5-test.txt
```

Never install Paperazzi's pinned dependencies into the user's Anaconda `base` or another existing general-purpose environment.

From the repository root:

```bash
micromamba create -y -f environment/Paperazzi.yml
micromamba run -n Paperazzi python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The environment checker must pass before authoritative local testing. If `Paperazzi` already exists, modify only that environment.

GitHub Actions is separately isolated and does not need micromamba.

## Author inclusion rule

Paper detail pages start from `paper_creator_mentions`, not `authorships`.

This is mandatory because every Zotero paper author must be displayed, unresolved canonical identity must never hide a source author, first-author status can exist even when identity is unresolved, and corresponding-author status remains accepted evidence attached to the author-paper relationship.

```text
source author mention           always visible
canonical author identity       optional
FIRST / CORRESPONDING roles     additive
```

## MVP query surface

```text
list_papers
get_paper
list_authors
get_author
get_author_publications
get_coauthors
list_identity_review_queue
search
get_pdf_path
```

## HTTP surface

```text
GET /
GET /health
GET /api/papers
GET /api/papers/{paper_id}
GET /api/papers/{paper_id}/pdf
GET /api/authors
GET /api/authors/{author_id}
GET /api/authors/{author_id}/papers
GET /api/authors/{author_id}/coauthors
GET /api/reviews/identity
GET /api/search?q=...
```

## PDF security boundary

The API never accepts an arbitrary path from the client. A PDF is served only when the requested paper exists, a persisted `paper_documents` row belongs to it, the row says `PDF_AVAILABLE`, and the persisted local path still exists as a file.

The endpoint is read-only and does not require Zotero Desktop.

## Identity review priority

```text
unresolved corresponding author   highest
unresolved first author           high
identity conflict                 high
ordinary unresolved coauthor      lower
```

This ranking affects review presentation only. It does not weaken automatic identity thresholds.

## Search

The first usable implementation searches paper title/DOI/venue and canonical author names/name variants through SQLAlchemy/SQLite. FTS5 remains a later optimization that requires measured real-corpus evidence.

## Run

```bash
micromamba run -n Paperazzi paperazzi-web
```

Default address: `http://127.0.0.1:8765`

Default database: `data/paperazzi.sqlite3`

Overrides:

```text
PAPERAZZI_DB=/path/to/paperazzi.sqlite3
PAPERAZZI_HOST=127.0.0.1
PAPERAZZI_PORT=8765
```

## Validate

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
micromamba run -n Paperazzi python scripts/validate_phase5.py --db-path data/phase4-validation/paperazzi.sqlite3
```

See `docs/phase5/PHASE5_TESTING.md` for the failure-isolated ASGI/Uvicorn validation model.

## Phase 5 status

```text
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
PHASE_5_STATUS = IN_PROGRESS
```

Next milestones:

1. complete real-library validation in the `Paperazzi` micromamba environment;
2. add pagination/filter controls and FTS5 only if measurements justify it;
3. add explicit review actions rather than read-only review display;
4. begin Phase 6 priority-author enrichment package generation.
