# Local AI Task Contract — Graph Analytics Real-Corpus Validation

Read and obey, in this order:

1. root `AGENTS.md`;
2. `docs/architecture/GRAPH_ANALYTICS_AND_LITERATURE_RELATION_MINING.md`;
3. `docs/analytics/GRAPH_ANALYTICS_RUNBOOK.md`.

## Mission

Validate Graph Analytics v1 against the user's real local WoS corpus and produce an expert-reviewable Singlet Fission benchmark report.

This task is validation and analysis. It is **not** permission to alter Zotero, source PDFs, or WoS source exports.

## Absolute rules

- Work directly on `main`; never create a branch or PR.
- Use only micromamba environment `Paperazzi` for authoritative execution.
- Treat `data/wos.sqlite3` as source scholarly data for this task; Graph Analytics reads it but does not write derived scores into it.
- Derived runs belong in `data/analytics.sqlite3`.
- Do not use an LLM to invent graph edges, communities, similarity scores, citations, or historical roots.
- Do not tune weights/thresholds until the initial benchmark results have been recorded.
- Do not call centrality a quality score.
- Do not interpret absent citations/references from incomplete WoS CR as negative evidence.
- Preserve suspicious outputs; do not silently remove them merely to improve presentation.

## Execution

### 1. Preflight and tests

```bash
export XDG_CACHE_HOME=/tmp/paperazzi-mamba-cache
export MAMBA_ROOT_PREFIX=/home/shuo/.local/share/mamba

git branch --show-current
git status --short
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
micromamba run -n Paperazzi python -m unittest discover -s tests -p 'test_graph_analytics*.py' -v
micromamba run -n Paperazzi python -m unittest discover -s tests -v
```

Do not discard unrelated local changes.

### 2. Build

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  --wos-db data/wos.sqlite3 \
  --analytics-db data/analytics.sqlite3 \
  build
```

If exact betweenness or coupling construction is unreasonably slow on the real corpus, measure and report the stage/corpus size before changing algorithms. Performance work must preserve semantics.

### 3. Record corpus quality

From the build/stats output record at least:

```text
record count
observed reference count
resolved citation edges
complete CR record count
incomplete/uncertain CR record count
analysis_run_id
snapshot hash
```

### 4. Structural checks

Inspect top 30 each:

```bash
paperazzi-analytics centrality --metric pagerank_local --limit 30
paperazzi-analytics centrality --metric betweenness_undirected --limit 30
paperazzi-analytics centrality --metric in_degree_local --limit 30
```

For every surprising high-rank item distinguish:

```text
real structural role
review/perspective hub
broad-method hub
corpus boundary effect
CR incompleteness artifact
suspicious implementation result
```

### 5. Singlet Fission seed set

Choose approximately 10 clearly identified SF papers already present in the local WoS corpus, covering several subareas when possible:

```text
experimental/photophysics
state/mechanism theory
CT/superexchange
coupling/electronic structure
rate theory
dynamics
spin/triplet-pair work
crystal/material work
review/perspective
```

Record the UT and why each seed was chosen. Do not select seeds to make the output look good.

For each seed run:

```bash
paperazzi-analytics neighborhood 'WOS:...'
paperazzi-analytics related 'WOS:...'
```

Review top neighbors and classify them:

```text
EXPECTED
PLAUSIBLE_NEW_CONNECTION
STRUCTURALLY_TRUE_BUT_NOT_SCIENTIFICALLY_USEFUL
SUSPICIOUS
SOURCE_COVERAGE_ARTIFACT
```

For coupling inspect actual shared references, not only scores.
For co-citation inspect actual citing papers.

### 6. Connector tests

Run multiple endpoint pairs including at least:

```text
electronic-structure/coupling ↔ dynamics
rate theory ↔ spin dynamics
experiment ↔ theoretical model
```

Every returned hop must correspond to a persisted `CITES_OBSERVED` fact. Judge whether the path is scientifically informative in addition to being topologically valid.

### 7. Communities

Run:

```bash
paperazzi-analytics communities
```

Assess:

- number and size distribution;
- whether obvious SF neighborhoods separate;
- whether labels reflect member papers;
- giant generic clusters;
- isolated records;
- whether incomplete CR systematically pushes papers out of meaningful clusters.

Community labels are derived descriptions, not scientific facts.

### 8. RPYS

Run:

```bash
paperazzi-analytics rpys --peaks-only
```

Inspect each major peak and the references responsible for it. Identify:

```text
recognized historical root
methodological/general chemistry root
field-specific landmark
corpus artifact
unresolved but potentially important old reference
```

The RPYS local baseline includes zero-count neighboring calendar years.

### 9. API smoke test

Start/use the local app or FastAPI TestClient and verify:

```text
GET /api/analytics/stats
GET /api/analytics/centrality
GET /api/analytics/wos/{ut}/related
GET /api/analytics/wos/{ut}/neighborhood
GET /api/analytics/connector
GET /api/analytics/communities
GET /api/analytics/rpys
```

Verify `/api/analytics/stats` reports stale/rebuild state after WoS changes.

## Required final report

Write a timestamped report under an ignored/local analytics run directory unless the user explicitly asks to commit the report. Include:

### Execution
- branch and dirty-state summary;
- environment check;
- targeted/full test results;
- build runtime if available;
- analysis run id/hash.

### Corpus quality
- papers;
- references;
- resolved citation edges;
- CR completeness distribution.

### Graph structure
- top PageRank;
- top bridge centrality;
- top local cited papers;
- component/community statistics.

### SF expert benchmark
For each seed, summarize coupling/co-citation/related results and classifications.

### Connector benchmark
List tested endpoints and path judgments.

### RPYS
List principal peaks and interpretation.

### Defects and artifacts
For each suspicious result state:

```text
example
whether source-data or algorithmic
root cause if identified
recommended code change
regression test needed
```

### GA-v2 recommendation
Prioritize only issues supported by the real benchmark. Likely categories include performance scaling, subset/collection landscapes, Leiden/Louvain comparison, concept networks, author/institution projections, or UI map rendering, but do not assume these are required before observing the data.

## Success condition

Success is not “the graph looks plausible.” Success requires:

1. deterministic tests pass;
2. every citation path traces to observed citation facts;
3. incomplete CR is visible and does not create false normalized coupling;
4. related-paper explanations expose components/evidence;
5. several SF results survive expert inspection;
6. suspicious results remain documented rather than hidden;
7. the report gives concrete evidence for the next Graph Analytics iteration.
