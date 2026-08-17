# Paperazzi Phase 5 Final Validation Report v4

PHASE_5_STATUS = INCOMPLETE
PAPERAZZI_MICROMAMBA_ENV = PASS
EXISTING_ANACONDA_ENV_MODIFIED = NO
PHASE_5_REAL_DB_SMOKE = PASS
PRODUCT_PATH_STATUS = PASS
ASGI_HARNESS_STATUS = PASS
FULL_CORPUS_AUTHOR_PROJECTION = PASS
BROWSER_SEMANTIC_SMOKE = INCOMPLETE
EXTENDED_SEARCH_VALIDATION = PASS
REAL_UNAVAILABLE_PDF_VALIDATION = PASS
IDENTITY_REVIEW_PERFORMANCE_RECHECK = PASS
MEANINGFUL_WARNINGS_REVIEWED = PASS
ZOTERO_SOURCE_MODIFIED = NO
IDENTITY_PRECISION_AUDIT = NOT_RUN_OPTIONAL
IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED

The final status is `INCOMPLETE`, not `PASS`, because this execution environment
does not provide an interactive real browser. The contract explicitly forbids
substituting ASGI/Uvicorn HTTP checks for the mandatory browser semantic smoke.
All other executable closeout stages were run against the real Paperazzi
database and passed.

## 1. Commit, branch, and working tree

```text
Validated commit: df3e3aea157ecefd91b8b2deca994655e537f431
Branch: main
Remote: origin/main
Working tree: understood; two pre-existing untracked directories remain
  pdf-evidence-output/
  phase2-output/
Tracked source changes during validation: none
```

The repository was fast-forwarded from `9291223` to `df3e3ae` before testing.
No Zotero source database, Zotero storage, or PDF was modified.

## 2. Environment proof

All authoritative commands ran through the dedicated micromamba environment.

```text
micromamba: 2.8.1
Environment: Paperazzi
Environment checker: PASS
Python: 3.13.15
SQLite runtime: 3.53.4
Separate from existing Anaconda/base: YES
Existing Anaconda environment modified: NO
pip check: PASS — No broken requirements found.
```

The pinned constraints matched without mismatch:

```text
SQLAlchemy 2.0.52
Alembic 1.19.1
PyMuPDF 1.28.2
FastAPI 0.141.1
Starlette 1.6.0
httpx 0.28.1
anyio 4.14.2
uvicorn 0.52.3
pydantic 2.13.4
```

## 3. Full regression suite and warning inventory

Command:

```text
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

```text
Result: PASS
Tests: 113/113
Elapsed: 34.056 seconds
```

The mandatory `test_identity_review_queue_is_ranked_with_one_select` and all
`test_phase5_closeout_report` tests passed. The suite produced no `SyntaxWarning`
from `local_evidence/pdf.py` and no unclosed SQLite `ResourceWarning` from the
migration tests.

Remaining project-originated warning:

```text
src/paperazzi/zotero_sqlite/__init__.py:9
DeprecationWarning: sqlite3.version is deprecated and will be removed in Python 3.14
```

This warning was recorded rather than suppressed. It did not fail any test.

## 4. Full-corpus real database validation

Command:

```text
micromamba run -n Paperazzi python scripts/validate_phase5.py \
  --db-path data/phase4-validation/paperazzi.sqlite3 --sample-papers 0
```

```text
REAL_DATABASE_QUERY = PASS
ASGI_IN_PROCESS = PASS
UVICORN_LOCALHOST_HTTP = PASS
product_path_status = PASS
Database: data/phase4-validation/paperazzi.sqlite3
Full-corpus projection check: true
Papers: 2513
Active canonical authors: 7398
Source author mentions: 12207
Accepted author mentions: 10448
Unresolved author mentions: 1759
Unresolved source authors visible in full corpus: 1759
Source-author projection mismatches: 0
Foreign-key check rows: 0
PDF_AVAILABLE rows: 2161
Reachable PDF rows: 2161
Stale PDF rows: 0
```

Database stage timings:

```text
REAL_DATABASE_QUERY elapsed: 7040.581 ms
list_papers(limit=20): 19.223 ms
list_authors(limit=20): 83.759 ms
paper detail requests: 2513
paper detail p50: 1.519 ms
paper detail p95: 1.952 ms
paper detail mean: 1.553 ms
paper detail max: 23.079 ms
```

Source-author semantics were preserved across the full corpus: all source
mentions remained visible to the projection check, and unresolved mentions
were not merged or hidden. A real unresolved-source candidate identified for
manual inspection was paper ID `7`; it was not browser-checked in this run.

## 5. ASGI and Uvicorn route timings

The standard real-database validator returned HTTP 200 for every listed route.
Times below are the individual request timings from the full-corpus run.

| Route | ASGI status | ASGI ms | Uvicorn status | Uvicorn ms |
| --- | ---: | ---: | ---: | ---: |
| `/` | 200 | 3.556 | 200 | 1.303 |
| `/health` | 200 | 1.386 | 200 | 0.995 |
| `/api/papers?limit=5` | 200 | 10.527 | 200 | 19.489 |
| `/api/authors?limit=5` | 200 | 25.999 | 200 | 28.458 |
| `/api/search?q=test&limit=5` | 200 | 34.954 | 200 | 35.267 |
| `/api/reviews/identity?limit=5` | 200 | 5.607 | 200 | 8.127 |
| `/api/papers/1` | 200 | 3.458 | 200 | 3.733 |
| `/api/authors/{author_id}` | 200 | 7.906 | 200 | 7.051 |
| `/api/authors/{author_id}/papers` | 200 | 6.094 | 200 | 8.051 |
| `/api/authors/{author_id}/coauthors?limit=10` | 200 | 6.196 | 200 | 6.473 |
| `/api/papers/1/pdf` | 200 | 41.722 | 200 | 38.196 |

The ASGI stage elapsed time was 148.117 ms. The Uvicorn stage elapsed time was
675.499 ms, with an empty server log tail and proxy inheritance disabled via
`trust_env=false`.

## 6. Identity-review before/after measurements

The required one-SELECT synthetic regression passed:

```text
test_identity_review_queue_is_ranked_with_one_select = PASS
```

Previous real-Uvicorn baseline:

```text
447.136 ms for /api/reviews/identity?limit=5
```

After one warm-up request, five consecutive real-Uvicorn requests returned:

```text
sample 1: 4.245 ms, HTTP 200
sample 2: 3.787 ms, HTTP 200
sample 3: 4.026 ms, HTTP 200
sample 4: 3.734 ms, HTTP 200
sample 5: 3.868 ms, HTTP 200
median: 3.868 ms
minimum: 3.734 ms
maximum: 4.245 ms
improvement ratio: 115.599x versus 447.136 ms
reduction: 99.135%
```

```text
IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED
```

The median is more than 30% below the old baseline and is not a regression.

## 7. Extended real search validation

All cases used values present in the real corpus and were sent through the real
Uvicorn `/api/search` endpoint with `limit=100`.

| Case | Query | Expected object | HTTP | Found | Time |
| --- | --- | --- | ---: | :---: | ---: |
| Distinctive full/long title | `Unraveling structural dynamics in isoenergetic excited S1 and multi-excitonic 1(TT) states of 9,10-bis(phenylethynyl)anthracene (BPEA) in solution via ultrafast Raman loss spectroscopy Electronic supplementary information (ESI) available: Summary of the concentration-dependent kinetics of TA of BPEA, and the molecular structure of BPEA along with its numbering on each atom. See DOI: 10.1039/c8cp06658b` | paper `2086` | 200 | true | 83.738 ms |
| DOI | `10.1021/acs.jpca.4c03213` | paper `1` | 200 | true | 28.090 ms |
| Venue fragment | `Physical Chemistry A` | paper `1` | 200 | true | 163.140 ms |
| Canonical author | `Damiano Aliverti-Piuri` | author `01M067NANX00Y8V8F8NBQ9MJ0G` | 200 | true | 31.522 ms |
| Non-ASCII author | `Dana Nachtigallová` | author `01M067NAP8RAK9524EK5CZ4N6G` | 200 | true | 30.732 ms |
| Punctuation-heavy title | `Slater-Condon Rules and Spin-Orbit Couplings: 2-(2-(2,5-Dimethoxybenzylidene)hydrazineyl)-4-(trifluoromethyl)thiazole a Test Case` | paper `2463` | 200 | true | 29.035 ms |

```text
EXTENDED_SEARCH_VALIDATION = PASS
```

## 8. Real PDF positive and negative paths

```text
Positive reachable PDF:
  paper ID: 1
  endpoint: /api/papers/1/pdf
  status: 200
  content type: application/pdf
  response bytes: 4815152
  elapsed: 41.808 ms

Negative unavailable-PDF case:
  paper ID: 22
  endpoint: /api/papers/22/pdf
  status: 404
  content type: application/json
  response bytes: 48
  elapsed: 1.198 ms
```

The unavailable case returned the controlled 404 response rather than a 500
or another paper's PDF.

```text
REAL_UNAVAILABLE_PDF_VALIDATION = PASS
```

## 9. Real browser semantic smoke

No interactive browser tool is available in this execution environment. The
following checks were therefore not performed in a real browser:

```text
home and paper-list render: NOT RUN
search interaction: NOT RUN
paper detail and source-order authors: NOT RUN
unresolved source-author visibility: NOT RUN
FIRST role on unresolved first author: NOT RUN
accepted CORRESPONDING display: NOT RUN
resolved author profile: NOT RUN
publication list and coauthor list: NOT RUN
identity-review ranked page: NOT RUN
reachable PDF opening: NOT RUN
unavailable PDF controlled browser failure: NOT RUN
```

Automated HTTP checks are not counted as browser evidence. The API identified
paper `7` as an unresolved-source candidate. No accepted corresponding-author
Authorship record exists in this real corpus, so a corresponding-author paper
ID is `NOT_AVAILABLE_IN_CORPUS`. The high-publication author below is a
candidate profile ID, not a browser-checked ID.

```text
BROWSER_SEMANTIC_SMOKE = INCOMPLETE
```

## 10. Targeted author-scale performance

High-publication author:

```text
author ID: 01M067NEW7ZJBS41VF2965N9CJ
name: Michael R. Wasielewski
publication count: 35
profile endpoint status: 200
profile elapsed: 17.667 ms
```

High-degree author:

```text
author ID: 01M067NGYVKC7M86JB3XQ6YPCF
name: Stefan Jakobs
coauthor degree: 147
paper count: 26
coauthor endpoint status: 200
returned coauthor count: 147
maximum shared-paper count: 17
coauthor endpoint elapsed: 16.741 ms
```

These are diagnostic measurements; no arbitrary latency threshold was applied.

## 11. Identity precision audit

```text
IDENTITY_PRECISION_AUDIT = NOT_RUN_OPTIONAL
```

No deterministic precision audit was requested or executed in this closeout.

## 12. Source and environment safety

```text
ZOTERO_SOURCE_MODIFIED = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO
```

The real DB validation used the existing Phase 4 Paperazzi-owned validation
database read-only. No Zotero `zotero.sqlite`, Zotero `storage/`, or PDF was
changed. No package operation targeted Anaconda base or an unrelated Python
environment.

## 13. Machine gate

The required machine gate was run against this report before commit. Because
the report truthfully uses `INCOMPLETE` for the mandatory browser stage, the
strict PASS-only checker rejects it; this is expected and prevents an omitted
browser test from being mislabeled as a formal Phase 5 PASS. The report must
remain `INCOMPLETE` until a real browser semantic smoke is performed.

## 14. Findings recorded from the user-facing review

The web service was made available at `http://127.0.0.1:8765` for the user's
browser inspection. The following findings were then reproduced against the
real Phase 4 validation database and are recorded as open product/test issues.
No implementation change was made in this closeout follow-up.

### 14.1 Canonical-author list starts with A-names

The real database contains `7,398` active canonical authors. The Authors API
and page currently request/display only the first `100` rows, while the query
sorts by `lower(preferred_name), author_id`. Therefore names such as `A Abate`
and `A. Jung` at the top of the page are the expected first alphabetic page;
the number `7,398` is the total count, not the number of rows currently shown.
This is a pagination/discoverability finding, not evidence that all other
initials were dropped from the database. The accepted design decision is to
keep Identity Review and Authors as separate views: Authors is the canonical
directory, while Identity Review is the review queue for unresolved or
ambiguous source-name mappings. No merge of those views was made.

```text
FINDING_CANONICAL_AUTHOR_FIRST_PAGE = CONFIRMED
DATABASE_CANONICAL_AUTHOR_TOTAL = 7398
AUTHORS_PAGE_LIMIT = 100
```

### 14.2 Paper 2468 selects Supporting Information as its PDF

For `Automated Active Space Selection with CASCI Dipole Moments` (paper
`2468`), the database has two reachable PDF documents:

```text
document 2324: ct6c00473_si_001.pdf; 56 pages; 14,341,800 bytes; Supporting Information
document 2325: Kaufold和Dong - 2026 - Automated Active Space Selection with CASCI Dipole Moments.pdf;
               18 pages; 4,424,956 bytes; main article
```

`get_pdf_path()` currently orders available documents by `document_id` and
returns the first existing path. Consequently `/api/papers/2468/pdf` returns
document `2324`, whose first page begins with `Supporting Information`, rather
than the article in document `2325`. This is a confirmed primary-document
selection issue, not a browser-only rendering issue.

```text
FINDING_PRIMARY_PDF_SELECTION = CONFIRMED
PAPER_2468_SERVED_DOCUMENT = 2324
PAPER_2468_EXPECTED_MAIN_DOCUMENT = 2325
```

### 14.3 Paper 2467 does not mark either corresponding author

For `Fermionic mean-field dynamics for spin systems beyond free fermions`
(paper `2467`, document `2323`), the PDF identifies `Rishab Dutta` and
`Marc Illa` with the correspondence markers and states that both should be
addressed at `rishab.dutta@pnnl.gov` and `marc.illasubina@pnnl.gov`. The real
database currently has no accepted correspondence evidence and no active
`is_corresponding_author=1` authorship for this paper, so the UI falls back to
`ORDINARY` for both rather than displaying `CORRESPONDING`.

The asterisk is not interpreted as a wildcard by the current correspondence
code. The parser did detect the correspondence candidate, but its email
extraction retained only the first address because the second address ended in
a period; the author-name matcher also matched `Dutta` but not `Illa` inside
`marc.illasubina`. This explains why the identity records themselves can look
normal while the corresponding-author role is absent. `ORDINARY` and
`UNRESOLVED` are separate dimensions: the former is a role fallback and the
latter is identity-resolution status.

```text
FINDING_CORRESPONDING_AUTHOR_EVIDENCE = CONFIRMED
PAPER_2467_EXPECTED_CORRESPONDING_AUTHORS = Rishab Dutta; Marc Illa
PAPER_2467_ACCEPTED_CORRESPONDING_AUTHOR_COUNT = 0
PAPER_2467_DOCUMENT_EVIDENCE_SPANS = 0
PAPER_2467_AUTHORSHIP_EVIDENCE_ROWS = 0
```

### 14.4 Reproduction fixtures

The three PDFs used for this investigation are committed beside this report
under `evidence/pdfs/`, with provenance, license notes, sizes, and SHA-256
checksums in its README. They are included so a remote AI or a later local
test can compare the main article against its SI and inspect the correspondence
front matter directly. Their inclusion is evidence packaging only; it does not
change `BROWSER_SEMANTIC_SMOKE` or the overall `PHASE_5_STATUS`.

```text
EVIDENCE_FIXTURES = 3 PDFs
IMPLEMENTATION_FIX_FOR_FINDINGS = NOT MADE
BROWSER_SEMANTIC_SMOKE = INCOMPLETE
PHASE_5_STATUS = INCOMPLETE
```
