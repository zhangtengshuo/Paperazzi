# Graph Analytics and Literature Relation Mining — Development Outline

**Status:** development baseline  
**Date:** 2026-08-19  
**Scope:** deterministic and explainable mining of relationships already present in Paperazzi, Zotero, and the independent WoS corpus

## 1. Purpose

Paperazzi has reached the point where its main scholarly data forms are sufficiently stable to support a new phase: **derive useful structure from relationships already present in the corpus instead of continuing to treat each paper as an isolated record**.

This document defines the first of two complementary development tracks:

1. **Graph Analytics and Literature Relation Mining** — relationships that can be computed mainly from existing structured data and graph topology;
2. **Research Landscape and Field Maturity** — higher-level reconstruction of models, mechanisms, methods, research trajectories, milestones, maturity, and gaps. The second track is specified separately in `RESEARCH_LANDSCAPE_AND_FIELD_MATURITY.md`.

The immediate goal of this track is to make Paperazzi answer questions such as:

- Which papers are truly close to this paper, and *why*?
- Which papers are the intellectual base of a topic, and which are part of its current research front?
- Which papers bridge otherwise separate clusters?
- What are the shortest or strongest literature paths between two papers or two research themes?
- Which authors, groups, institutions, funders, or venues form persistent communities?
- Which old papers remain foundational even if they are not in the Zotero library or local WoS Full Record corpus?
- Which papers should the user read next because they occupy a structurally important position rather than merely sharing keywords?

The design should borrow useful interaction ideas from ResearchRabbit, Connected Papers, Litmaps, Inciteful, VOSviewer, bibliometrix, CiteSpace, and related science-mapping work without reproducing any one product.

---

## 2. Core design principle: facts, derived relations, and interpretations are different layers

Paperazzi must not store a computed similarity as though it were a bibliographic fact.

```text
SOURCE FACTS
    |
    |-- Paper A --CITES--> Paper B
    |-- Author X --AUTHORED--> Paper A
    |-- Paper A --HAS_KEYWORD--> K
    |-- Author X --AFFILIATED_WITH--> Institution I
    |
    v
DERIVED RELATIONS
    |
    |-- A --BIBLIOGRAPHIC_COUPLING[0.72]--> C
    |-- A --CO_CITED_WITH[41]--> B
    |-- X --COAUTHOR_STRENGTH[0.48]--> Y
    |-- A --BRIDGE_SCORE[...]--> cluster pair
    |
    v
AI / HUMAN INTERPRETATION
    |
    `-- “A and C belong to the same methodological research front.”
```

Required provenance classes:

```text
FACT
DERIVED
INTERPRETATION
```

A derived edge must carry the analysis run, algorithm, parameters, input snapshot, and score components that created it.

An AI narrative must point to facts/derived results and must never be required for the underlying graph to exist.

---

## 3. Existing data that should be exploited first

### 3.1 Paperazzi / Zotero

- active Zotero papers;
- Zotero collections and tags;
- author order and resolved author identities;
- local PDF provenance/fallback evidence;
- Paperazzi ↔ WoS links;
- user-curated membership in collections, which is a strong signal of personal research interest.

### 3.2 Independent WoS corpus

High-value graph inputs include:

- `UT`, DOI, title, year, venue;
- `AU` / `AF` authors;
- author-address links (`C1`) and organizations (`C3`);
- ORCID / ResearcherID;
- author keywords and Keywords Plus;
- WoS categories, research areas, citation topics;
- funding organizations/grants;
- cited references (`CR`) and resolved `target_ut` edges;
- citation-count observations;
- CR completeness/observation state introduced by the WoS merge model.

The WoS corpus is broader than Zotero and should act as the background graph around the user’s curated library.

### 3.3 Future public-web person evidence

The public-web person layer should later add explicit mentorship, group membership, event participation, and other evidence-backed social relations. Those edges should be usable by graph analytics but must remain provenance-distinct from publication-derived co-authorship.

---

## 4. Citation completeness is part of the analytics contract

The recent WoS export behavior shows that `CR` may be omitted or partial in some observations. This matters mathematically.

Paperazzi must distinguish:

```text
“an observed citation exists”
```

from:

```text
“no citation exists”
```

when the source reference list is incomplete.

### 4.1 Safe statements with partial CR

If a CR row was observed, the corresponding citation edge is valid evidence even when the source record’s reference list is incomplete.

### 4.2 Unsafe negative statements with partial CR

If a record has `MISSING_FROM_EXPORT`, `PARTIAL`, or uncertain CR status, absence of a specific citation cannot be treated as evidence that the paper did not cite it.

### 4.3 Metrics affected by incomplete CR

The following require completeness-aware filtering or uncertainty flags:

- bibliographic coupling;
- reference-overlap normalization;
- out-degree and reference diversity;
- shortest paths if missing outgoing citations are material;
- co-citation counts when the citing source may have an incomplete CR payload;
- main-path or historical analyses built from a truncated local graph.

Initial policy:

- direct observed citation edges may always be retained;
- normalized reference-overlap measures should prefer records with confirmed complete CR;
- analyses using incomplete records must expose `coverage_status` / `input_quality`;
- no ranking should silently mix complete and incomplete reference lists as though they were equivalent.

---

## 5. Core graph model

The analytics layer should support at least these node classes:

```text
Paper
Author
Institution
Funder
Keyword
Topic
Venue
ZoteroCollection
PublicEvent       future
```

Primary fact edges:

```text
Paper --CITES--> Paper / ExternalReference
Author --AUTHORED--> Paper
Author --FIRST_AUTHOR_OF--> Paper
Author --CORRESPONDING_AUTHOR_OF--> Paper
Author --AFFILIATED_WITH--> Institution
Paper --HAS_KEYWORD--> Keyword
Paper --HAS_TOPIC--> Topic
Paper --FUNDED_BY--> Funder
Paper --PUBLISHED_IN--> Venue
Paper --IN_ZOTERO_COLLECTION--> ZoteroCollection
```

The graph should retain source identity and evidence status for every fact edge.

---

## 6. Analysis family A — direct citation network

### 6.1 Basic graph statistics

Compute for relevant corpus slices:

- in-degree / out-degree;
- local and global citation counts where meaningful;
- PageRank or related prestige scores;
- betweenness centrality;
- closeness only where graph topology makes it interpretable;
- weak/strong component membership;
- temporal citation accumulation;
- citation age distribution.

Centrality must never be presented as a generic “quality score”. Labels should be structural:

```text
highly cited in this corpus
high bridge centrality
high PageRank within this landscape
```

### 6.2 Prior and derivative works

Borrow the useful interaction concept from Connected Papers:

- **Prior works:** older papers structurally central to the neighborhood;
- **Derivative works:** later papers/reviews that consolidate or extend the neighborhood.

The algorithm should be explicit; this is not simply “oldest” and “newest”.

### 6.3 Citation path service

Support queries such as:

```text
How is Paper A connected to Paper B?
How is singlet fission connected to nonadiabatic dynamics?
What papers bridge NOCI and charge-transfer coupling literature?
```

Initial methods:

- shortest path on direct citation graph;
- k-shortest paths;
- bidirectional citation expansion;
- path scoring that penalizes extremely generic high-degree hubs;
- optional path constraints by year, topic, author, venue, or Zotero membership.

This reproduces the useful *literature connector* concept while keeping the full path explainable.

---

## 7. Analysis family B — bibliographic coupling

Two papers are bibliographically coupled when they cite overlapping prior literature.

For paper reference sets `R_i` and `R_j`, store more than one similarity metric rather than prematurely selecting one universal score.

Candidate measures:

```text
intersection_count = |R_i ∩ R_j|
Jaccard            = |Ri ∩ Rj| / |Ri ∪ Rj|
Salton/cosine      = |Ri ∩ Rj| / sqrt(|Ri| |Rj|)
```

Also support fractional weighting so that papers with huge bibliographies do not dominate merely because they cite many references.

### Why this matters

Bibliographic coupling is especially useful for detecting a **research front**: recent papers may be highly related because they use the same intellectual base even before they have had time to cite one another.

### Required output

A derived edge should expose:

```json
{
  "relation": "BIBLIOGRAPHIC_COUPLING",
  "shared_reference_count": 23,
  "jaccard": 0.31,
  "cosine": 0.57,
  "reference_quality": "COMPLETE_BOTH",
  "top_shared_references": ["..."],
  "analysis_run_id": "..."
}
```

The UI must be able to answer **why are these papers related?** by showing the shared references.

---

## 8. Analysis family C — co-citation

Two papers are co-cited when later papers cite them together.

Co-citation is especially useful for identifying the **intellectual base** of a field:

```text
Research front         bibliographic coupling
Intellectual base      co-citation
```

Recommended outputs:

- raw co-citation count;
- normalized co-citation score;
- citing-paper list;
- first observed co-citation year;
- co-citation time series;
- corpus-specific vs broader-WoS support.

A time series is valuable because two papers can move from independent works to a community-recognized conceptual pair years later.

---

## 9. Analysis family D — co-authorship and research-group structure

Construct author collaboration graphs with explicit weighting choices.

Possible edge components:

```text
shared papers
fractional shared-paper weight
recency-weighted collaboration
first/corresponding-author role combinations
shared institutions over time
shared topics
```

Do not equate:

```text
coauthor = advisor
coauthor = same research group
coauthor = close collaborator
```

Those stronger relations require separate evidence.

Useful derived views:

- persistent collaboration communities;
- short-lived collaborations;
- cross-institution bridges;
- emerging independent groups around former trainees once public-web genealogy exists;
- author migration between topic communities.

---

## 10. Analysis family E — conceptual structure and topic evolution

Use multiple concept sources separately:

```text
Author Keywords
Keywords Plus
WoS Category
WoS Research Area
WoS Citation Topic
Zotero tags
future AI/domain concepts
```

Do not silently collapse them into one canonical topic vocabulary.

### 10.1 Co-word network

Compute keyword/topic co-occurrence with:

- term frequency;
- document frequency;
- pair co-occurrence;
- normalized association strength;
- temporal frequency;
- cluster membership.

### 10.2 Thematic map

Borrow the bibliometrix strategic-map idea:

- centrality = relation of a theme to the overall domain;
- density = internal development/cohesion of the theme.

The four-quadrant presentation can label themes as:

```text
motor
basic/transversal
niche/specialized
emerging-or-declining
```

The final label must include temporal evidence before distinguishing “emerging” from “declining”.

### 10.3 Thematic evolution

Across time windows, track clusters that:

- persist;
- split;
- merge;
- appear;
- disappear;
- change vocabulary while retaining paper/citation continuity.

Prefer relational continuity, not pure keyword-string overlap.

---

## 11. Analysis family F — community detection and map layout

The graph UI should not depend on a single community algorithm.

Initial candidates:

- Leiden/Louvain-style modularity communities;
- connected-component analysis;
- density-based clustering for semantic/path outputs;
- hierarchical clustering for small local neighborhoods.

Every community result should be versioned by algorithm and parameters.

The 2-D map is a **visualization of a relation model**, not the relation model itself.

Possible layout sources:

- force-directed graph for interactive neighborhoods;
- UMAP/t-SNE only for embeddings or similarity spaces and clearly labeled as projections;
- timeline layout for temporal paths;
- bipartite layout for author–paper or paper–funder views.

---

## 12. Explainable related-paper scoring

Paperazzi should eventually have a unified related-paper service, but v1 must remain decomposable.

Candidate components:

```text
DIRECT_CITATION
BIBLIOGRAPHIC_COUPLING
CO_CITATION
SHARED_AUTHORS
SHARED_INSTITUTIONS
SHARED_KEYWORDS
SHARED_TOPICS
SHARED_FUNDERS
TEMPORAL_PROXIMITY
ZOTERO_COLLECTION_PROXIMITY
future ABSTRACT_SEMANTIC_SIMILARITY
```

Return the vector of components, not just one number.

Example:

```json
{
  "paper": "A",
  "related_paper": "B",
  "score": 0.81,
  "reasons": {
    "bibliographic_coupling": 0.72,
    "co_citation": 0.66,
    "shared_topic": 0.88,
    "shared_author": 0.0
  },
  "explanation": "Strong shared-reference base and frequent later co-citation; no shared authors."
}
```

AI may verbalize this vector, but the score must be reproducible without AI.

---

## 13. Historical-root detection with RPYS

Reference Publication Year Spectroscopy (RPYS) should be implemented because WoS CR data is unusually well suited to it.

Procedure:

1. take all cited references in a landscape/corpus;
2. aggregate by cited-reference publication year;
3. identify peaks relative to local temporal baselines;
4. identify references responsible for each peak;
5. resolve them to local WoS/Paperazzi records where possible;
6. preserve unresolved historical references as first-class external reference nodes.

RPYS complements citation counts because foundational works can be old, sparsely indexed, or absent from the local Full Record corpus.

Potential extension: RPYS-CO using a marker paper or landmark to isolate a more specific intellectual lineage.

---

## 14. User-facing exploration modes

### 14.1 Paper neighborhood

From one seed paper show:

```text
Direct citations
Shared-reference neighbors
Co-cited neighbors
Important prior works
Important derivative works
Shared authors/topics
```

### 14.2 Multi-seed map

The user selects several seed papers or a Zotero collection. Build a local graph around their union and rank papers by relevance to the seed set.

### 14.3 Literature connector

Two papers/topics/authors become endpoints. Return multiple explainable literature paths.

### 14.4 Cluster overview

Show major communities, labels, representative papers, authors, venues, and time span.

### 14.5 Author network

Show collaboration communities and allow overlaying future public-web mentorship/event evidence without conflating evidence types.

### 14.6 Time slider

All major graph views should be able to filter by publication year or analysis window so the user can watch a structure emerge rather than only see the final accumulated network.

---

## 15. Persistence model for derived analytics

Do not write derived scores into source tables.

Recommended logical tables:

```text
analysis_runs
- analysis_run_id
- analysis_type
- input_snapshot_hash
- corpus_definition_json
- algorithm
- parameters_json
- code_version
- started_at
- completed_at
- status

analysis_nodes
- analysis_run_id
- node_type
- node_key
- attributes_json

analysis_edges
- analysis_run_id
- source_type/source_key
- predicate
- target_type/target_key
- weight
- components_json
- quality_status

analysis_clusters
- analysis_run_id
- cluster_id
- label
- metrics_json

analysis_cluster_members
- analysis_run_id
- cluster_id
- node_key
- membership_weight
```

Because these outputs are recomputable and potentially large, a separate future `data/analytics.sqlite3` is reasonable. The implementation may initially keep small materialized analytics in Paperazzi-owned storage, but source databases must remain cleanly separated from derived outputs.

---

## 16. API concepts

Candidate endpoints:

```text
GET /api/analytics/papers/{id}/related
GET /api/analytics/papers/{id}/neighborhood
GET /api/analytics/connector?from=...&to=...
GET /api/analytics/clusters/{landscape_id}
GET /api/analytics/authors/{id}/network
GET /api/analytics/rpys/{landscape_id}
GET /api/analytics/themes/{landscape_id}
POST /api/analytics/runs
```

Every API response should expose analysis provenance and quality/completeness warnings.

---

## 17. Development sequence

### Phase GA-0 — Corpus and graph snapshot contract

- define graph node/edge identifiers;
- define input snapshot/hash;
- define CR completeness handling;
- define analysis-run provenance;
- implement sparse graph export from WoS/Paperazzi without new interpretation.

### Phase GA-1 — Citation core

Implement:

- direct citation graph;
- degree/PageRank/betweenness;
- citation path queries;
- prior/derivative work ranking;
- graph component statistics.

### Phase GA-2 — Coupling and co-citation

Implement:

- bibliographic coupling;
- co-citation;
- normalization/fractional counting;
- “why related” evidence;
- local paper-neighborhood API.

### Phase GA-3 — Communities and concepts

Implement:

- community detection;
- co-word network;
- thematic map;
- temporal cluster statistics;
- initial 2-D interactive map.

### Phase GA-4 — Author/institution/funder projections

Implement:

- collaboration graph;
- institution network;
- funder–paper and funder–topic views;
- temporal affiliation/collaboration overlays where evidence permits.

### Phase GA-5 — RPYS and evolution utilities

Implement:

- RPYS;
- RPYS peak explanations;
- theme evolution across time slices;
- outputs consumed by the Research Landscape layer.

### Phase GA-6 — Composite explainable recommendation

Build the related-paper service from deterministic components. Semantic embeddings may be added later as one component, not as the sole relation model.

---

## 18. Acceptance criteria

The graph-analytics stage is acceptable only if:

1. all derived relations are reproducible from a versioned input snapshot;
2. source facts and derived edges are visibly distinct;
3. incomplete WoS CR does not silently produce false negative assertions or unfair normalized similarity;
4. a user can open a related-paper edge and see why it exists;
5. bibliographic coupling and co-citation are separately available and not collapsed into one opaque similarity score;
6. citation-path results are traceable to actual citation edges;
7. community labels do not become canonical scientific facts;
8. old/unresolved references remain usable in RPYS and historical-root analysis;
9. the same algorithms work on a Zotero collection, an arbitrary WoS corpus slice, and a future named Research Landscape;
10. no AI call is required to compute the baseline graph.

---

## 19. Initial benchmark

Use singlet-fission literature as the first expert-checkable benchmark because Paperazzi already has a substantial user-curated/WoS corpus and domain expertise is available for manual validation.

Benchmark questions:

- Do known theoretical/experimental subcommunities separate naturally?
- Does bibliographic coupling identify recent research fronts more effectively than direct citation alone?
- Does co-citation recover recognized intellectual bases?
- Are old seminal works recovered by RPYS even when not in Zotero?
- Can the connector find sensible paths between electronic-structure/coupling papers and dynamics/spin papers?
- Which papers are structurally important bridges but not top citation-count papers?
- How strongly do the user’s Zotero collections align with data-derived communities?

The benchmark should produce a frozen validation report before tuning scoring weights.

---

## 20. Methodological inspirations

This design is informed by the following established approaches:

- ResearchRabbit: iterative citation-network exploration and paper/author/concept maps;
- Connected Papers: similarity based on co-citation and bibliographic coupling rather than a simple citation tree;
- Litmaps: seed-based citation-network discovery and iterative expansion;
- Inciteful: graph-based paper discovery and literature-connector paths;
- VOSviewer / bibliometrix / CiteSpace: bibliographic coupling, co-citation, co-authorship, co-word networks, thematic maps, temporal science mapping;
- Reference Publication Year Spectroscopy (RPYS): historical-root and seminal-reference detection;
- bibliometric-network research emphasizing full vs fractional counting and careful normalization.

Key references for implementation design include:

- Connected Papers, “About”: co-citation + bibliographic coupling similarity and force-directed visualization.
- Perianes-Rodriguez, Waltman & van Eck (2016), *Constructing bibliometric networks: A comparison between full and fractional counting*.
- Waltman et al. (2019), work comparing relatedness measures for clustering publications.
- Marx, Bornmann, Barth & Leydesdorff (2014), *Detecting the historical roots of research fields by reference publication year spectroscopy (RPYS)*.
- Haunschild & Bornmann (2022), *Reference publication year spectroscopy (RPYS) in practice*.

The implementation should treat these as methodological references, not as a requirement to reproduce their software output exactly.
