# Paperazzi Phase 5.5 Identity and Correspondence Validation Report

PHASE5_5_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
PYTHON_313_CONTRACT = PASS
SYNTHETIC_REGRESSION = PASS
NAME_VARIANT_RECONCILIATION = FAIL
SIMILAR_NAME_CANDIDATES = PASS
IDENTITY_REVIEW_ACTIONS = PASS
IDENTITY_REVIEW_REAL_SAMPLE = PENDING_USER_REVIEW
CANONICAL_DIFFERENT_PAIR_PERSISTENCE = PASS
PAGINATION_UX = FAIL
PAPER_ID_TRACEABILITY = PASS
IDENTITY_UNRESOLVED_EXPLANATION = PASS
SOURCED_AUTHOR_EVIDENCE_API = PASS
CORRESPONDENCE_BENCHMARK = FAIL
CORRESPONDENCE_BENCHMARK_FP = 2
CORRESPONDENCE_BENCHMARK_RECALL = 0.2314814815
FULL_CORRESPONDENCE_POPULATION = BLOCKED_BY_BENCHMARK
ZOTERO_SOURCE_MODIFIED = NO
LIVE_PAPERAZZI_DB_MODIFIED_DURING_VALIDATION = NO
EXISTING_ANACONDA_ENV_MODIFIED = NO

The local automated stages are complete. The report deliberately remains
AWAITING_USER_BROWSER_CONFIRMATION; the browser checklist has not been
claimed as passed by the local agent. The service will be started against the
isolated test copy after this report is written and left available for the
user's inspection.

## 1. Pulled revision and runtime

The repository was fast-forwarded with:

~~~text
git pull --ff-only origin main
before: 35118ae
after:  6417119e452ce3e3c088400ea7218bd10d654dc9
commit: Test multi-candidate and persistent different-person identity review
~~~

Runtime checks:

~~~text
micromamba: 2.8.1
environment: Paperazzi
Python: 3.13.15
environment contract: PASS
pip check: No broken requirements found.
Alembic head/current: 0007_similar_author_review_queue (head)
~~~

The full suite command was:

~~~text
micromamba run -n Paperazzi python -W default -m unittest discover -s tests -v
~~~

Result: Ran 136 tests in 45.757s, OK; failures 0, errors 0, skips 0.
The repository had no tracked or modified production files from this
validation. The pre-existing unrelated untracked directories
pdf-evidence-output/ and phase2-output/ were preserved.

## 2. Database safety and isolated validation copy

The live source database was opened read-only and copied with
sqlite3.Connection.backup():

~~~text
source: data/phase4-validation/paperazzi.sqlite3
source size: 39124992 bytes
source SHA-256: 9c7d294132e2122714cccc956c4d2c986a21b180410493cb8a803b3e1671cddd

copy: data/phase5-validation/phase5_5/paperazzi-phase5_5.sqlite3
copy size after validation: 39890944 bytes
copy SHA-256: 20c4cd987441d96285d24069691b5c2c20a9e21201d01ab26dca0ff824d011c7
copy migration: 0007_similar_author_review_queue (head)
PRAGMA foreign_key_check: []
~~~

All writes in this run, including the migration, name-variant sync, review
queue refresh, and synthetic validation actions, were scoped to the copy.
The live Paperazzi database, Zotero source, and existing Anaconda/micromamba
environment were not modified.

Copy baseline/final corpus facts used by the checks:

~~~text
papers: 2513
active canonical authors: 7398
source author mentions: 12207
accepted author memberships: 10448
open ambiguous identity reviews before similar refresh: 1759
~~~

## 3. Name variants and similar-name review queue

Name-variant commands:

~~~text
sync dry-run:
  accepted_memberships = 10448
  current_source_variants = 7398

sync apply:
  accepted_mentions_seen = 10448
  variants_added = 0

second sync apply:
  accepted_mentions_seen = 10448
  variants_added = 0
~~~

The sync is idempotent. There are 1,145 canonical authors with more than one
accepted mention, but 0 authors with more than one distinct SOURCE raw spelling
in this corpus. Therefore the required real-data sample of at least 20 authors
with multiple variants is not available in the pulled input. This is recorded
as NAME_VARIANT_RECONCILIATION = FAIL; no variants or human identity decisions
were invented to satisfy the sample gate.

Similar-name refresh at minimum score 0.50 produced:

~~~text
blocked_pairs_examined: 4895
same_paper_pairs_blocked: 36
manual_different_pairs_blocked: 0
pairs_similarity_scored: 4859
candidate_sources: 2182
reviews_created_or_updated: 500
algorithm_seconds (dry-run): 2.267
~~~

The applied copy contains 500 open SIMILAR_AUTHOR_IDENTITY rows and the
original 1759 open AMBIGUOUS_AUTHOR_IDENTITY rows. Accepted memberships
remained 10448, and no automatic merge occurred. Real candidate pairs remain
pending human review; this validation did not make decisions about real people.

## 4. Identity Review operations

The targeted operation suite passed 14/14 tests in 6.886s. It covered:

- unresolved mention comparison and manual link;
- mention-level not-same-person rejection;
- create-separate-identity;
- manual merge while preserving source spellings;
- reverse-direction merge (full -> hyphen) in a temporary synthetic 0007
  database;
- same-paper merge guard;
- canonical pair Different people persistence and suppression of future
  similar-name suggestions;
- lock/unlock and repeatable unlink/relink history.

The reverse-direction check returned an active target with two active
authorships and a persisted merge decision. The canonical pair decision test
also passed. The real-data candidate queue was inspected, but no real pair was
resolved; hence IDENTITY_REVIEW_REAL_SAMPLE = PENDING_USER_REVIEW.

## 5. API and UI evidence

ASGI checks against the isolated copy returned:

~~~text
GET /health: 200, OK
GET /api/papers?limit=1&offset=0: 200, total=2513, paper_id present
GET /api/papers/2468: 200
  title = Automated Active Space Selection with CASCI Dipole Moments
  paper_id = 2468
GET /api/authors?limit=1&offset=0: 200, total=7398, author_id present
GET /api/authors/{id}/evidence: 200, rows=0 on this copy
GET /api/reviews/identity: 200, canonical-author queue rows use preferred names
GET /api/reviews/identity/{multi-candidate-id}: 200, candidate_count=2
~~~

The real copy has no populated authorship_evidence rows, so its evidence route
correctly returned an empty list. The dedicated sourced-evidence tests passed
2/2 and verified that ACCEPTED and CANDIDATE evidence are exposed with
provenance while candidate evidence is not promoted into current canonical
profile fields.

The returned home-page source contains IDENTITY UNRESOLVED, Paperazzi ID,
jumpPage, and position:sticky. The paper detail API exposes the title and
numeric Paperazzi ID, and the unresolved explanation is present in the UI
source. These support PAPER_ID_TRACEABILITY and
IDENTITY_UNRESOLVED_EXPLANATION.

PAGINATION_UX = FAIL is intentional at this stage: local source/ASGI checks
show the sticky pager and direct-page input, but a real browser session has
not yet been visually confirmed. The final service is left for user browser
inspection; no browser pass is claimed here.

## 6. Correspondence benchmark

The benchmark was built with:

~~~text
micromamba run -n Paperazzi python scripts/build_correspondence_benchmark.py \
  --db-path data/phase5-validation/phase5_5/paperazzi-phase5_5.sqlite3 \
  --sample-size 80 \
  --output data/phase5-validation/phase5_5/correspondence-benchmark-v1.json
~~~

Builder result:

~~~text
cases: 80
with_candidate: 53
with_email: 47
predicted_nonempty: 17
~~~

Every case was manually inspected from the actual selected primary PDF's
front matter. Ground truth was written into the benchmark JSON; 70 cases had
an explicit corresponding-author marker/star/email, and 10 had no explicit
correspondence information in the inspected primary PDF front matter and were
left with an empty ground-truth list rather than inferred.

Scoring result:

~~~text
reviewed_cases: 80
tp: 25
fp: 2
fn: 83
precision: 0.9259259259
recall: 0.2314814815
hard_gate_fp_zero: false
recall_gate_0_90: false
pass: false
~~~

Representative failures:

- Paper 389, On the role of symmetry in XDW-CASPT2: the PDF explicitly
  identifies Roland Lindh as the correspondence author, but the parser
  selected Stefano Battaglia from the ordinary Electronic mail line. Roland
  Lindh's source mention is still an unresolved identity candidate and has no
  active authorship, which also exposes the identity/correspondence coupling.
- Paper 1683, Enzyme-catalyzed electrochemical aptasensor...: the PDF maps
  *, **, and *** to Yue Zhang, Mei Lin, and Chenglin Zhou, but the parser
  additionally predicted Xiaobin Zhou.
- Paper 2169, A Bayesian cluster analysis method...: the PDF names Dylan M.
  Owen and Patrick Rubin-Delanchy as corresponding; only Dylan M. Owen was
  predicted.
- Paper 1608, Harnessing multiple generated excitons...: the PDF names
  Fernando Fernández-Lázaro and Dirk M. Guldi; only Dirk M. Guldi was
  predicted.

The broader failure pattern is consistent with the prior user findings:
ordinary Electronic mail is not equivalent to a correspondence declaration;
starred author-header information is not consistently retained in the
correspondence candidate span; email-to-author mapping can become ambiguous
when the source identity is unresolved; and grouped multi-author email blocks
can over-map an unrelated author. The benchmark failure is preserved as a
blocking result. Full correspondence population is therefore not run.

The pulled code already contains the focused correspondence and identity
regression coverage used above. No production fix or real-data population was
applied during this validation; the failing benchmark and JSON ground truth
remain available in the ignored data/phase5-validation/phase5_5/ test-output
directory for the next repair cycle.

## 7. Committed 100-PDF analysis sample

At the user's request, 100 active Paperazzi primary PDFs were selected from
the reachable local primary-PDF corpus using `random.Random(20260817)`. They
were copied into the tracked project directory:

~~~text
tests/fixtures/phase5_5_correspondence_pdf_sample_100/
~~~

The accompanying manifest records each Paperazzi ID, title, DOI, source file
name, byte size, and SHA-256:

~~~text
tests/fixtures/phase5_5_correspondence_pdf_sample_100/MANIFEST.json
~~~

Sample verification passed:

~~~text
PDF files: 100
total bytes: 253019226 (241.3 MiB)
total pages: 1389
largest file: 10512092 bytes
SHA-256 mismatches: 0
unreadable PDFs: 0
~~~

The sample contains primary PDFs selected from the local corpus, not the
SQLite database or Zotero source. It is included so a remote AI can inspect
representative front matter and correspondence formatting. The report and
this sample are the only intended files for the GitHub commit; unrelated
untracked directories remain unstaged.

## 8. Final handoff

The automated result is not a Phase 5.5 pass because the name-variant real
sample is unavailable and the correspondence hard gate fails (FP=2, recall
0.2315). The isolated test service should be inspected in a browser before
any further UI conclusion. Real correspondence population remains
BLOCKED_BY_BENCHMARK.
