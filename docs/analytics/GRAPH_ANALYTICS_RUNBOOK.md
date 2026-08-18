# Paperazzi Graph Analytics — Real-Corpus Runbook

**Status:** Graph Analytics v1 operational guide  
**Scope:** deterministic analysis of the local WoS background corpus into `data/analytics.sqlite3`

## 1. Data boundary

Graph Analytics is a derived layer:

```text
data/wos.sqlite3          source scholarly facts, read only for analytics
        ↓
data/analytics.sqlite3    recomputable analysis runs
```

Never write PageRank, coupling, co-citation, communities or RPYS results back into WoS source tables.

Every completed run records:

- WoS input snapshot hash;
- source corpus revision counts;
- algorithm name/version;
- parameters;
- CR completeness summary;
- run timestamps/status.

## 2. Current v1 capabilities

Implemented:

```text
Observed local citation graph
In/out degree
PageRank
Undirected betweenness / bridge centrality
Weak components
Bibliographic coupling
  - shared reference count
  - Jaccard when both CR lists are complete
  - Salton/cosine when both CR lists are complete
  - fractional shared-reference weight
Co-citation
  - raw count
  - normalized observed score
  - supporting citing papers
Paper neighborhood
Explainable related-paper score
Citation literature connector
Deterministic weighted-label communities
RPYS historical-root series and peaks
Analysis-run provenance
WoS revision / stale-run detection
```

Not yet part of v1:

```text
Leiden/Louvain dependency-backed community algorithms
co-word/thematic evolution
Zotero-collection-specific subset build UI
full author/institution/funder graph projections
semantic embeddings
Research Landscape contribution extraction
```

## 3. Pre-flight

Use the project environment exactly as required by root `AGENTS.md`:

```bash
export XDG_CACHE_HOME=/tmp/paperazzi-mamba-cache
export MAMBA_ROOT_PREFIX=/home/shuo/.local/share/mamba

micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

Run targeted tests:

```bash
micromamba run -n Paperazzi \
  python -m unittest discover -s tests -p 'test_graph_analytics*.py' -v
```

Then run the full synthetic suite:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
```

## 4. Build the first real analytics run

Default input/output:

```text
data/wos.sqlite3
data/analytics.sqlite3
```

Build:

```bash
micromamba run -n Paperazzi paperazzi-analytics build
```

Explicit paths:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  --wos-db data/wos.sqlite3 \
  --analytics-db data/analytics.sqlite3 \
  build
```

Useful sensitivity build:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  build \
  --min-shared-references 2 \
  --min-co-citation 2 \
  --community-min-weight 0.10
```

Do not tune these values merely to make a visually attractive graph. Record benchmark observations first.

## 5. Inspect run statistics

```bash
micromamba run -n Paperazzi paperazzi-analytics stats
```

Record:

```text
analysis_run_id
input_snapshot_hash
input_quality.complete_reference_lists
input_quality.incomplete_or_uncertain_reference_lists
nodes
CITES_OBSERVED edges
BIBLIOGRAPHIC_COUPLING edges
CO_CITATION edges
communities
```

The CR completeness counts are mandatory context for interpreting coupling and co-citation results.

## 6. Structural rankings

PageRank:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  centrality --metric pagerank_local --limit 50
```

Bridge papers:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  centrality --metric betweenness_undirected --limit 50
```

Local citation degree:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  centrality --metric in_degree_local --limit 50
```

Interpret these structurally. Do not describe PageRank or betweenness as paper quality.

## 7. Paper neighborhoods

For a WoS accession:

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  neighborhood 'WOS:XXXXXXXXXXXXXXX' --limit 30
```

The response separates:

- direct citations;
- papers citing the seed;
- shared-reference neighbors;
- co-cited neighbors;
- composite related papers.

For every bibliographic-coupling edge inspect:

```text
shared_reference_count
cosine
jaccard
quality_status
top_shared_references
```

If either source record has incomplete/uncertain CR, normalized coupling is intentionally suppressed. Positive shared references remain evidence; missing references are not treated as negative evidence.

## 8. Explainable related-paper service

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  related 'WOS:XXXXXXXXXXXXXXX' --limit 30
```

v1 exposes score components rather than one opaque similarity:

```text
DIRECT_CITATION             0.20
BIBLIOGRAPHIC_COUPLING      0.35
CO_CITATION                 0.25
SHARED_AUTHORS              0.10
SHARED_CONCEPTS             0.10
```

This is an initial benchmark model, not a frozen scientific truth. Do not tune it until the Singlet Fission validation report is recorded.

## 9. Literature connector

```bash
micromamba run -n Paperazzi paperazzi-analytics \
  connector 'WOS:SOURCE' 'WOS:TARGET' \
  --max-paths 3 \
  --max-hops 8
```

The connector traverses the undirected projection of observed citation facts so it can move both forward and backward through citation history.

Every returned path edge states:

```text
FORWARD_CITATION
or
REVERSE_TRAVERSAL
```

and names the actual citing/cited nodes. Partial CR may hide paths; it never creates a path.

## 10. Communities

```bash
micromamba run -n Paperazzi paperazzi-analytics communities
```

v1 uses:

```text
DETERMINISTIC_WEIGHTED_LABEL_PROPAGATION_V1
```

on a combined similarity graph derived from complete-CR coupling plus co-citation.

Community labels come from frequent structured concepts and are explicitly derived labels. They are not canonical topic assertions.

## 11. RPYS

Full time series:

```bash
micromamba run -n Paperazzi paperazzi-analytics rpys
```

Peaks only:

```bash
micromamba run -n Paperazzi paperazzi-analytics rpys --peaks-only
```

Inspect the references responsible for peaks. Unresolved cited references remain useful and should not be dropped just because no local WoS Full Record exists.

## 12. Web/API

Analytics routes are mounted with the existing WoS router.

Build:

```http
POST /api/analytics/runs
```

Body example:

```json
{
  "min_shared_references": 2,
  "min_co_citation": 2,
  "community_min_weight": 0.10
}
```

Query endpoints:

```text
GET /api/analytics/stats
GET /api/analytics/centrality
GET /api/analytics/wos/{ut}/related
GET /api/analytics/wos/{ut}/neighborhood
GET /api/analytics/papers/{paper_id}/related
GET /api/analytics/papers/{paper_id}/neighborhood
GET /api/analytics/connector?from_ut=...&to_ut=...
GET /api/analytics/paper-connector?from_paper_id=...&to_paper_id=...
GET /api/analytics/communities
GET /api/analytics/rpys
```

Paper-ID routes require an accepted `paper_wos_links` bridge. WoS-only background papers remain queryable directly by UT.

`GET /api/analytics/stats` reports whether the latest materialized run appears stale relative to the current canonical WoS graph counts. A stale run is preserved for provenance and should be rebuilt rather than silently overwritten.

## 13. Singlet Fission benchmark

The first real validation should use the existing Singlet Fission corpus.

Inspect at least:

1. top 30 PageRank papers;
2. top 30 bridge-centrality papers;
3. 10 expert-known seed papers from distinct SF subareas;
4. their top coupling neighbors;
5. their top co-citation neighbors;
6. connector paths between electronic-structure/coupling work and dynamics/spin work;
7. major derived communities;
8. top RPYS peaks and responsible references.

For each output classify:

```text
EXPECTED
PLAUSIBLE_NEW_CONNECTION
STRUCTURALLY_TRUE_BUT_NOT_SCIENTIFICALLY_USEFUL
SUSPICIOUS
SOURCE_COVERAGE_ARTIFACT
```

Do not tune weights until this first benchmark is frozen.

## 14. Required real-run report

Return:

```text
Environment/tests
Analysis run id/hash
WoS CR completeness summary
Graph node/edge counts
Top PageRank papers
Top bridge papers
Representative coupling relations with shared references
Representative co-citation relations with citing papers
Representative connector paths
Community summary
RPYS peaks
Suspicious outputs / source-coverage artifacts
Recommended GA-v2 changes
```

The purpose of the first run is validation of analytical meaning, not producing the prettiest graph.
