# Paperazzi Phase 5 Post-Fix Validation Report v5

PHASE_5_POST_FIX_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
PYTHON_313_CONTRACT = PASS
SYNTHETIC_REGRESSION = PASS
REAL_DB_COPY_MIGRATION = PASS
FULL_CORPUS_AUTHOR_PROJECTION = PASS
PAPER_2468_PRIMARY_PDF = PASS
PAPER_2468_RETRACTION = PASS
PAPER_2467_CORRESPONDING = PASS
CROSS_RUN_REPLACEMENT = PASS
MULTI_PDF_SANITY_SAMPLE = PASS
EXTENDED_SEARCH_VALIDATION = PASS
REAL_UNAVAILABLE_PDF_VALIDATION = PASS
IDENTITY_REVIEW_PERFORMANCE_RECHECK = PASS
PAGINATION_API = PASS
USER_BROWSER_CONFIRMATION = PENDING
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO

The local automated and real-data-copy stages are complete. The final status is
deliberately `AWAITING_USER_BROWSER_CONFIRMATION`: the browser checklist was
not marked by the local agent. A Paperazzi service using the test copy is left
running at `http://127.0.0.1:8765` for the user's inspection.

## 1. Code, branch, and runtime

```text
Pulled baseline commit: 66e4d656b5a71e6144c745aebc48a1fd67038c3b
Branch: main
Remote tracking state at start: main == origin/main
micromamba: 2.8.1
Python: 3.13.15
Environment: Paperazzi
Environment checker: PASS
pip check: PASS — No broken requirements found.
Migration head: 0006_document_roles_retractions
```

The post-fix worktree contains an uncommitted minimal change in
`src/paperazzi/identity/authorship_evidence.py` and its regression test in
`tests/test_phase5_provenance_retraction.py`. These changes were made only
after the real 2467 rebuild exposed that the pulled code accepted one of the
two corresponding authors. They have not been deployed to the live database.

## 2. Synthetic and regression suite

Command:

```text
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
```

The pulled baseline completed `121 tests in 39.732s` with `OK`. During real
post-fix validation, the original 2467 failure was preserved: the rebuild
accepted only one corresponding author. The smallest code fix was then made
and the full suite was rerun:

```text
Final result: 122 tests in 40.881s
Failures: 0
Errors: 0
Skips: 0
Result: OK
Paperazzi-originated warnings: none
```

The added regression covers initial-form source names `R Dutta` and `M Illa`
with `rishab.dutta@pnnl.gov` and `marc.illasubina@pnnl.gov`. The implementation
now supports a unique given-token/family-token mapping for dotted email local
parts while retaining the existing ambiguity guard.

## 3. Database safety and test-copy fingerprint

The real Paperazzi source database was:

```text
data/phase4-validation/paperazzi.sqlite3
size: 39124992 bytes
SHA-256 before validation: 9c7d294132e2122714cccc956c4d2c986a21b180410493cb8a803b3e1671cddd
SHA-256 after validation:  9c7d294132e2122714cccc956c4d2c986a21b180410493cb8a803b3e1671cddd
```

The validation copy was created with `sqlite3.Connection.backup()` at:

```text
data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3
size: 39124992 bytes
SHA-256: befcfec623aa9fd83fca38a7e02067560157bd428c886803c2ecf8495fabd8d6
```

The differing copy hash is expected for a SQLite Backup API copy; the size
matches and the copy was upgraded independently. The copy reached
`0006_document_roles_retractions`, and `PRAGMA foreign_key_check` returned
zero rows. The first failed 2467 post-fix attempt was preserved locally as
`data/phase5-validation/post-fix/paperazzi-post-fix-pre-fix-2467.sqlite3`.

```text
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO
```

## 4. Full-corpus copy validation

Command:

```text
micromamba run -n Paperazzi python scripts/validate_phase5.py \
  --db-path data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3 \
  --sample-papers 0
```

The final clean-copy run returned `status = PASS`:

```text
REAL_DATABASE_QUERY = PASS
ASGI_IN_PROCESS = PASS
UVICORN_LOCALHOST_HTTP = PASS
full_corpus_projection_check = true
source_author_projection_mismatch_count = 0
foreign_key_check_rows = 0
papers = 2513
active canonical authors = 7398
source author mentions = 12207
accepted author mentions = 10448
unresolved author mentions = 1759
PDF_AVAILABLE rows = 2161
reachable PDF rows = 2161
stale PDF rows = 0
```

Final database-stage timings included list-papers `58.758 ms`, list-authors
`82.773 ms`, paper-detail p50 `3.229 ms`, p95 `4.955 ms`, and maximum
`25.939 ms`.

## 5. Paper 2468: primary article versus SI

The clean-copy before state was:

```text
document 2324: ct6c00473_si_001.pdf
  effective role: SUPPLEMENTARY
  role source: HEURISTIC
  role confidence: 0.98
  evidence spans/authorship evidence/reference sections/references: 0/0/0/0
document 2325: Kaufold和Dong - 2026 - Automated Active Space Selection with CASCI Dipole Moments.pdf
  effective role: PRIMARY_ARTICLE
  role source: HEURISTIC
  role confidence: 0.60
selected_primary_document_id: 2325
```

The SI role was first previewed with `set-document-role` and then persisted
only on the test copy:

```text
role = SUPPLEMENTARY
source = LOCAL_AI
reason_code = CONFIRMED_SUPPORTING_INFORMATION
retraction_id = 1
retraction reason = DOCUMENT_RECLASSIFIED_AS_SUPPLEMENTARY
retraction impact count = 0
```

The zero impact count is valid because this clean copy had no live extraction
or paper-level derivations attached to document 2324. Raw spans and downstream
evidence remained present at count zero; no history was deleted. After the
role write, document 2324 remained `SUPPLEMENTARY`, document 2325 remained
`PRIMARY_ARTICLE`, and `selected_primary_document_id` remained `2325`.

The route was checked against the test copy:

```text
GET /api/papers/2468/pdf
HTTP = 200
content type = application/pdf
bytes = 4424956
pages = 18
first page = Automated Active Space Selection with CASCI Dipole Moments
```

The returned PDF is the main article, not `ct6c00473_si_001.pdf`.

## 6. Paper 2467: corresponding-author rebuild

The selected primary document was document `2323`,
`Dutta 等 - 2026 - Fermionic mean-field dynamics for spin systems beyond free fermions.pdf`.
The no-apply preview showed:

```text
page_count = 13
text_status = NATIVE_TEXT_GOOD
error = null
emails = rishab.dutta@pnnl.gov, marc.illasubina@pnnl.gov
correspondence candidate = ∗Authors to whom correspondence should be addressed:
  rishab.dutta@pnnl.gov, marc.illasubina@pnnl.gov.
previous_accepted_attempt_id = null
```

The actual primary PDF front matter was checked before applying the PASS
review to the test copy. The final rebuild evidence was:

```text
extraction_run_id = 1
attempt_id = 1
reviewer = LOCAL_AI
review decision = PASS
persisted front-matter spans = 2
replacement_retraction_id = null
corresponding_accepted = 2
unresolved = 0
current extraction run = 1
```

Final paper-level author roles:

| Order | Source name | Corresponding status |
| ---: | --- | --- |
| 0 | R Dutta | `CORRESPONDING` / `ACCEPTED` |
| 1 | M Illa | `CORRESPONDING` / `ACCEPTED` |
| 2 | N Govind | not corresponding |
| 3 | K Kowalski | not corresponding |

The clean test copy had no previous accepted extraction, so cross-run
replacement was not triggered. This is recorded as `CROSS_RUN_REPLACEMENT =
PASS` with the explicit condition `previous_accepted_attempt_id = null`; the
replacement-history branch remains covered by synthetic regression tests.

Pre-fix/post-fix evidence was kept separate:

```text
pre-fix real-copy attempt: corresponding_accepted = 1 (R Dutta only)
responsible layer: email local-part to initial-form author mapping
post-fix clean-copy attempt: corresponding_accepted = 2 (R Dutta and M Illa)
```

The asterisk is not treated as a wildcard. The defect was that
`marc.illasubina` did not match the source author’s initial-form `M Illa`; the
fix adds a unique dotted-token mapping without weakening the ambiguity guard.

## 7. Multi-PDF/SI sanity sample

There were `96` reachable real papers with at least two available PDF
documents. The following first 20 were prioritized by the product’s own
`SUPPLEMENTARY` filename classifier. `selected role` is the effective role of
the selected document; `failure` means a supplementary document was selected
while a non-supplementary candidate existed.

| Paper | Documents with effective roles | Selected | Selected role | Failure |
| ---: | --- | ---: | --- | :---: |
| 350 | `ct5c01695_si_001.pdf` [SUPPLEMENTARY]; `Stan 等 - 2026 - NOCI-F Electronic Couplings in Assemblies of Indolonaphthyridine Molecules From Dimers to the Full.pdf` [PRIMARY_ARTICLE] | 295 | PRIMARY_ARTICLE | No |
| 930 | `ct1c00476_si_001.pdf` [SUPPLEMENTARY]; `De Sousa和De Silva - 2021 - Unified Framework for Photophysical Rate Calculations in TADF Molecules.pdf` [PRIMARY_ARTICLE] | 903 | PRIMARY_ARTICLE | No |
| 973 | `Kathir 等 - 2020 - Reduced Common Molecular Orbital Basis for Nonorth.pdf` [PRIMARY_ARTICLE]; `Kathir 等 - 2020 - Reduced Common Molecular Orbital Basis for Nonorthogonal Configuration Interaction.pdf` [PRIMARY_ARTICLE]; `ct9b01144_si_001.pdf` [SUPPLEMENTARY] | 947 | PRIMARY_ARTICLE | No |
| 1850 | `jz8b02887_si_001.pdf` [SUPPLEMENTARY]; `Sato 等 - 2018 - Synergetic Effects of Triplet–Triplet Annihilation.pdf` [PRIMARY_ARTICLE] | 1751 | PRIMARY_ARTICLE | No |
| 2364 | `Renaud和Grozema - 2015 - Intermolecular Vibrational Modes Speed Up Singlet Fission in Perylenediimide Crystals.pdf` [PRIMARY_ARTICLE]; `jz5023575_si_001.pdf` [SUPPLEMENTARY] | 2201 | PRIMARY_ARTICLE | No |
| 2365 | `Kamencek 等 - 2020 - Evaluating Computational Shortcuts in Supercell-Based Phonon Calculations of Molecular Crystals The.pdf` [PRIMARY_ARTICLE]; `ct0c00119_si_001.pdf` [SUPPLEMENTARY] | 2203 | PRIMARY_ARTICLE | No |
| 2366 | `Wang和Houjou - 2026 - Coarse-grained lattice dynamics calculations combined with independent stiffness approximation a co.pdf` [PRIMARY_ARTICLE]; `d6cp00159a1_suppl.pdf` [SUPPLEMENTARY] | 2205 | PRIMARY_ARTICLE | No |
| 2367 | `Avila Ferrer和Santoro - 2012 - Comparison of vertical and adiabatic harmonic approaches for the calculation of the vibrational stru.pdf` [PRIMARY_ARTICLE]; `c2cp41169e_suppl.pdf` [SUPPLEMENTARY] | 2207 | PRIMARY_ARTICLE | No |
| 2368 | `Soprani 等 - 2025 - Accurate and Efficient Phonon Calculations in Molecular Crystals via Minimal Molecular Displacements.pdf` [PRIMARY_ARTICLE]; `ct5c00494_si_001.pdf` [SUPPLEMENTARY] | 2209 | PRIMARY_ARTICLE | No |
| 2370 | `Levine 等 - 2020 - CASSCF with Extremely Large Active Spaces Using the Adaptive Sampling Configuration Interaction Meth.pdf` [PRIMARY_ARTICLE]; `ct9b01255_si_001.pdf` [SUPPLEMENTARY] | 2212 | PRIMARY_ARTICLE | No |
| 2371 | `Agarawal 等 - 2024 - Automatic State Interaction with Large Localized Active Spaces for Multimetallic Systems.pdf` [PRIMARY_ARTICLE]; `ct4c00376_si_001.pdf` [SUPPLEMENTARY] | 2214 | PRIMARY_ARTICLE | No |
| 2372 | `Song和Li Manni - 2025 - A Genetic Algorithm Approach for Compact Wave Function Representations in Spin-Adapted Bases.pdf` [PRIMARY_ARTICLE]; `ct5c01264_si_001.pdf` [SUPPLEMENTARY] | 2216 | PRIMARY_ARTICLE | No |
| 2377 | `Freitag 等 - 2021 - Simplified State Interaction for Matrix Product State Wave Functions.pdf` [PRIMARY_ARTICLE]; `ct1c00674_si_001.pdf` [SUPPLEMENTARY] | 2222 | PRIMARY_ARTICLE | No |
| 2379 | `Abraham和Mayhall - 2020 - Selected Configuration Interaction in a Basis of Cluster State Tensor Products.pdf` [PRIMARY_ARTICLE]; `ct0c00141_si_001.pdf` [SUPPLEMENTARY] | 2225 | PRIMARY_ARTICLE | No |
| 2380 | `Park - 2021 - Second-Order Orbital Optimization with Large Active Spaces Using Adaptive Sampling Configuration Int.pdf` [PRIMARY_ARTICLE]; `ct0c01292_si_001.pdf` [SUPPLEMENTARY] | 2227 | PRIMARY_ARTICLE | No |
| 2383 | `Hermes 等 - 2025 - Localized Active Space State Interaction Singles.pdf` [PRIMARY_ARTICLE]; `ct5c00387_si_001.pdf` [SUPPLEMENTARY] | 2231 | PRIMARY_ARTICLE | No |
| 2384 | `Pandharkar 等 - 2022 - Localized Active Space-State Interaction a Multireference Method for Chemical Insight.pdf` [PRIMARY_ARTICLE]; `ct2c00536_si_001.pdf` [SUPPLEMENTARY] | 2233 | PRIMARY_ARTICLE | No |
| 2385 | `Reinholdt 等 - 2026 - Linear Response Selected Configuration Interaction.pdf` [PRIMARY_ARTICLE]; `ct5c01676_si_001.pdf` [SUPPLEMENTARY] | 2235 | PRIMARY_ARTICLE | No |
| 2387 | `Burton和Thom - 2020 - Reaching Full Correlation through Nonorthogonal Configuration Interaction A Second-Order Perturbati.pdf` [PRIMARY_ARTICLE]; `ct0c00468_si_001.pdf` [SUPPLEMENTARY] | 2238 | PRIMARY_ARTICLE | No |
| 2389 | `Liao 等 - 2024 - Quantum Information Orbitals (QIO) Unveiling Intrinsic Many-Body Complexity by Compressing Single-B.pdf` [PRIMARY_ARTICLE]; `jz4c01105_si_001.pdf` [SUPPLEMENTARY] | 2241 | PRIMARY_ARTICLE | No |

```text
MULTI_PDF_SANITY_SAMPLE = PASS
sample size = 20
selected supplementary failures = 0
```

## 8. Extended search validation

All requests were made through the real Uvicorn service using the clean test
copy and `limit=100`.

| Case | Expected object | HTTP | Found | Time |
| --- | --- | ---: | :---: | ---: |
| Distinctive full title/ESI text | paper `2086` | 200 | Yes | 136.951 ms |
| DOI `10.1021/acs.jpca.4c03213` | paper `1` | 200 | Yes | 36.986 ms |
| Venue `Physical Chemistry A` | paper `1` | 200 | Yes | 398.341 ms |
| Canonical author `Damiano Aliverti-Piuri` | author `01M067NANX00Y8V8F8NBQ9MJ0G` | 200 | Yes | 45.803 ms |
| Non-ASCII author `Dana Nachtigallová` | author `01M067NAP8RAK9524EK5CZ4N6G` | 200 | Yes | 34.482 ms |
| Punctuation-heavy title | paper `2463` | 200 | Yes | 33.323 ms |

```text
EXTENDED_SEARCH_VALIDATION = PASS
```

## 9. PDF positive/negative validation

```text
Positive: GET /api/papers/2468/pdf
  HTTP 200, application/pdf, 4,424,956 bytes, 18 pages, main-article first page

Negative: GET /api/papers/22/pdf
  HTTP 404, application/json, 48 bytes, controlled unavailable-PDF response
```

The unavailable route did not return another paper’s PDF and did not produce a
500 response.

## 10. Identity-review performance

The test service received one warm-up request followed by five consecutive
real Uvicorn requests:

```text
sample 1: 4.987 ms
sample 2: 4.095 ms
sample 3: 4.144 ms
sample 4: 3.958 ms
sample 5: 4.911 ms
median: 4.144 ms
minimum: 3.958 ms
maximum: 4.987 ms
mean: 4.419 ms
```

The single-SELECT structural regression passed in the 122-test suite. No
caching or FTS5 optimization was added for this measurement.

## 11. Pagination API

The first, second, final, and all-page boundary checks were performed with
`limit=100`.

```text
Papers:
  page 0 total = 2513; page 100 total = 2513; final offset = 2500; final count = 13
  page 0/page 100 different = true; boundary overlap = 0
  all pages = 26; rows = 2513; unique IDs = 2513; boundary overlaps = 0

Authors:
  page 0 total = 7398; page 100 total = 7398; final offset = 7300; final count = 98
  page 0/page 100 different = true; boundary overlap = 0
  all pages = 74; rows = 7398; unique IDs = 7398; boundary overlaps = 0
```

```text
PAGINATION_API = PASS
```

## 12. Mandatory user browser checklist

The final service is configured with:

```text
PAPERAZZI_DB=data/phase5-validation/post-fix/paperazzi-post-fix.sqlite3
URL=http://127.0.0.1:8765
```

The local agent has not marked these items. Please report each item as PASS or
FAIL after inspecting the page:

```text
A. Papers pagination — PENDING
   - total corpus count is visible;
   - Next changes to a different paper set;
   - Previous returns to the prior set;
   - page number and total pages are plausible.

B. Authors pagination — PENDING
   - page is not limited to the first 100 alphabetic identities;
   - Next reaches later alphabetic regions;
   - Previous returns correctly.

C. Paper 2468 — PENDING
   - document role matches the selected article;
   - Open local PDF opens the main paper, not ct6c00473_si_001.pdf;
   - opened PDF visually shows the article.

D. Paper 2467 — PENDING
   - source author order is correct;
   - Rishab Dutta is CORRESPONDING;
   - Marc Illa is CORRESPONDING;
   - no unrelated author is CORRESPONDING;
   - opened PDF confirms the correspondence information.

E. Unresolved-author semantics — PENDING
   - source name remains visible and order is preserved;
   - UNRESOLVED is visible;
   - FIRST remains visible when the unresolved source author is first.

F. Identity Review — PENDING
   - page opens normally;
   - high-priority corresponding/first-author cases remain ranked ahead when present;
   - no obvious old ~450 ms UI stall.
```

Therefore:

```text
USER_BROWSER_CONFIRMATION = PENDING
PHASE_5_POST_FIX_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
```

## 13. Defects and fixes

The pulled code correctly preferred paper 2468’s primary article and extracted
both 2467 email addresses, but its email-author matcher did not map a dotted
local part such as `marc.illasubina` to the source author displayed as `M
Illa`. The fix is limited to unique tokenized local-part matching and does not
turn `*` into a wildcard or weaken ambiguity checks. A real-data copy exposed
the defect before it was changed; a 122-test rerun and clean-copy rebuild then
passed with both corresponding authors.

No live database correction was applied. The validated 2468 role and 2467
evidence exist only in the ignored test copy used by this report.

## 14. Follow-up findings from the user's browser review

These findings were reported after the automated post-fix stages. They are
recorded as open issues; no additional implementation change was made in this
turn, and `USER_BROWSER_CONFIRMATION` remains `PENDING`.

### 14.1 Corresponding-author coverage is incomplete

The user's requirement is that every article's available correspondence
information should be recognized. The current test-copy database does not meet
that coverage requirement. A read-only count showed:

```text
papers = 2513
papers with active authorships = 2243
papers with any accepted corresponding author = 1
accepted corresponding authors = 2
active authorships with corresponding_status = UNKNOWN = 10446
accepted CORRESPONDING_AUTHOR evidence rows = 2
papers with document evidence = 1
papers with extraction runs = 1
open UNRESOLVED_CORRESPONDING_AUTHOR queue rows = 0
```

The one covered paper is 2467, `Fermionic mean-field dynamics for spin systems
beyond free fermions`, which was explicitly rebuilt during this validation.
This statistic does not prove that the other 2,512 papers have no
corresponding author in their source PDFs; it proves that the current database
has not yet performed or accepted a full-corpus correspondence extraction and
mapping pass.

The current pipeline requires a primary-document extraction run, a detected
correspondence candidate, an explicit correspondence signal, and a unique
paper-author mapping before it creates an accepted role. The detector currently
looks for correspondence terms or emails; the literal `*` is not itself a
wildcard or a complete mapping rule. The next coverage work must handle the
varied PDF styles (asterisks and superscripts, footnotes, multiple email blocks,
“corresponding author(s)” wording, and author/affiliation markers) and run the
accepted evidence workflow across the primary PDFs. Until then, most
`CORRESPONDING` counts are necessarily absent.

```text
FOLLOW_UP_CORRESPONDING_COVERAGE = OPEN
FULL_CORRESPONDENCE_REBUILD = NOT RUN
```

### 14.2 Internal paper IDs are not shown in the browser

When this report says “paper 2468”, `2468` is the internal database
`paper_id`, not a label currently displayed by the web page. The browser page
shows the title, DOI, year, and venue but not that numeric ID. The referenced
record is:

```text
paper_id = 2468
title = Automated Active Space Selection with CASCI Dipole Moments
doi = 10.1021/acs.jctc.6c00473
```

This is a reporting/UI traceability issue. Future user-facing reports should
lead with the title and DOI and optionally include the internal ID in
parentheses; the UI should expose a stable paper identifier if users need to
cross-reference logs and reports.

```text
FOLLOW_UP_PAPER_ID_TRACEABILITY = OPEN
```

### 14.3 Pagination is not persistent and has no direct page input

The current UI renders `.pager` after the paper/author list inside the panel.
It therefore appears only after scrolling through the list. The control has
Previous/Next buttons and a page counter, but no fixed/sticky bottom placement
and no input for jumping directly to a page number.

```text
FOLLOW_UP_PAGINATION_PLACEMENT = OPEN
FOLLOW_UP_PAGINATION_DIRECT_PAGE_INPUT = OPEN
```

The API supports `limit` and `offset`, and the automated pagination checks pass;
this finding concerns the browser interaction design, not API correctness.

### 14.4 Meaning of `UNRESOLVED` in Identity Review and paper detail

`UNRESOLVED` does not mean that the source author text could not be read. It
means that the source creator mention has no accepted
`AuthorIdentityMembership` to a canonical author for that particular paper.
The source name remains visible from `paper_creator_mentions`, while the
canonical `author_id` is null. `FIRST`/`ORDINARY` are authorship roles and are
independent from identity-resolution status.

For the reported examples, both are on paper 298,
`Symmetry-directed control of electronic coupling for singlet fission in
covalent bis-acene dimers`:

```text
Niels H. Damrauer — FIRST, UNRESOLVED
Jamie L. Snyder   — ORDINARY, UNRESOLVED
```

Their source names are present, but the paper-298 mentions are queued as
`AMBIGUOUS_AUTHOR_IDENTITY` with `NAME_BLOCK_REQUIRES_REVIEW`. Canonical
profiles with those names exist and are accepted on other paper mentions, but
that does not automatically merge this specific pair of source mentions. This
is intentional identity safety behavior, but the UI should explain it more
clearly instead of making `UNRESOLVED` look like a failed name parse.

```text
FOLLOW_UP_IDENTITY_REVIEW_LABELING = OPEN
```

### 14.5 Author profiles do not yet expose PDF-derived affiliation/contact data

The current `authors` model stores canonical name, normalized name, status,
merge/lock state, name variants, and external IDs. It has no persisted
affiliation or email fields, and the Author page only renders profile counts,
publications, and coauthors.

The PDF parser can produce affiliation and correspondence spans. For the
validated 2467 PDF, the test copy contains an accepted affiliation-candidate
span and an accepted correspondence span containing both email addresses, but
those spans remain document-level evidence; they are not projected into an
author contact/affiliation profile. Therefore the missing work unit and email
display is an unimplemented enrichment/projection feature, not evidence that
the PDF text was unavailable.

```text
FOLLOW_UP_AUTHOR_CONTACT_ENRICHMENT = OPEN
AUTHOR_PROFILE_AFFILIATION_FIELDS = NOT IMPLEMENTED
AUTHOR_PROFILE_EMAIL_FIELDS = NOT IMPLEMENTED
```

### 14.6 Overall follow-up state

```text
CORRESPONDING_AUTHOR_COVERAGE = INCOMPLETE
PAPER_ID_USER_TRACEABILITY = INCOMPLETE
PERSISTENT_PAGINATION_UI = INCOMPLETE
IDENTITY_REVIEW_EXPLANATION = INCOMPLETE
AUTHOR_CONTACT_ENRICHMENT = INCOMPLETE
USER_BROWSER_CONFIRMATION = PENDING
PHASE_5_POST_FIX_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
```
