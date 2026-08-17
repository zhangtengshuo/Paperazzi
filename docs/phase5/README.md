# Phase 5 — Backend and Minimal Web UI

## Objective

Turn the validated Paperazzi database into a usable local research tool without changing the source/provenance semantics established in Phases 1–4.

The Phase 5 MVP must support this end-to-end workflow:

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

The query/service layer is authoritative for read semantics. HTTP handlers must stay thin.

## Author inclusion rule

Paper detail pages start from `paper_creator_mentions`, not `authorships`.

This is mandatory because:

- every Zotero paper author must be displayed;
- unresolved canonical identity must never hide a source author;
- first-author status can exist even when identity is unresolved;
- corresponding-author status remains accepted evidence attached to the author-paper relationship.

The UI therefore distinguishes:

```text
source author mention           always visible
canonical author identity       optional
FIRST / CORRESPONDING roles     additive
```

## MVP query surface

`PaperazziQueryService` provides:

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

The API never accepts an arbitrary path from the client. A PDF is served only when:

1. the requested paper exists in Paperazzi;
2. a persisted `paper_documents` row belongs to that paper;
3. `availability_status='PDF_AVAILABLE'`;
4. the persisted local path still exists as a file.

The endpoint is read-only and does not require Zotero Desktop.

## Identity review priority

The first UI ranking is:

```text
unresolved corresponding author   highest
unresolved first author           high
identity conflict                 high
ordinary unresolved coauthor      lower
```

This ranking affects review presentation only. It does not weaken automatic identity thresholds.

## Search

The first usable implementation searches paper title/DOI/venue and canonical author names/name variants through SQLAlchemy/SQLite. FTS5 is a later performance/indexing enhancement once the product query contract is stable.

## Run

Install:

```bash
python -m pip install -e ".[pdf,web]"
```

Start:

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

Override with:

```text
PAPERAZZI_DB=/path/to/paperazzi.sqlite3
PAPERAZZI_HOST=127.0.0.1
PAPERAZZI_PORT=8765
```

## Phase 5 status

```text
CURRENT_PHASE = PHASE_5_BACKEND_AND_WEB_UI
PHASE_5_STATUS = IN_PROGRESS
```

Next milestones after the MVP is green on CI:

1. validate against the real Paperazzi database;
2. add pagination/filter controls and FTS5 if needed;
3. add explicit review actions rather than read-only review display;
4. begin Phase 6 priority-author enrichment package generation.
