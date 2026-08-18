# Research Landscape, Knowledge Evolution, and Field Maturity — Development Outline

**Status:** development baseline  
**Date:** 2026-08-19  
**Scope:** reconstruction of research-field evolution, contribution lineages, milestones, maturity, and evidence gaps from Paperazzi’s graph plus evidence-bearing AI/domain analysis

## 1. Purpose

This document defines the higher-level research-intelligence track that sits above Paperazzi’s bibliographic graph analytics.

The problem is not merely:

```text
Which papers are related?
```

It is:

```text
How did a research direction become what it is today?
Who introduced or changed the important models?
Which experimental observations forced theoretical changes?
Which methods became standard, and which remain exploratory?
Where are the major unresolved capabilities or evidence gaps?
How mature is one research capability compared with another field?
```

The intended end product is a **Research Landscape**: a reproducible, evidence-backed model of a research domain that can support timelines, method/model genealogies, milestone attribution, capability profiles, evidence-gap maps, and field-to-field comparison.

This layer depends on `GRAPH_ANALYTICS_AND_LITERATURE_RELATION_MINING.md`, but it must not be reduced to citation counts or an LLM-generated narrative.

---

## 2. Four scales of scholarly understanding

Paperazzi should explicitly support four different analytical scales:

```text
LEVEL 1 — PAPER
What did this paper do?

LEVEL 2 — NEIGHBORHOOD
What papers/authors/methods are structurally related to it?

LEVEL 3 — LINEAGE
Where did this model/method/mechanism come from, and what extended or challenged it?

LEVEL 4 — FIELD
How did the entire research direction evolve, how mature are its capabilities, and what is missing?
```

Existing literature-discovery tools are strongest at Levels 1–2. Paperazzi’s differentiating target should be Levels 3–4 while retaining traceability back to the underlying papers.

---

## 3. Core principle: a field history must be built from multiple evidence layers

A trustworthy Research Landscape should combine:

```text
citation structure
    +
co-citation / bibliographic coupling / community structure
    +
temporal topic evolution
    +
structured paper contributions
    +
citation-context / prior-work relations
    +
expert-reviewable evidence
```

No single layer is sufficient.

Examples:

- citation count alone does not tell whether a paper introduced a model or merely popularized it;
- a review may summarize a milestone but is not automatically the primary source of that milestone;
- co-citation can reveal an intellectual pairing but does not specify the scientific relation;
- AI can identify a claimed novelty, but the claim must be tied to evidence in the paper and checked against prior literature;
- a method may be highly published but still weakly benchmarked or poorly validated.

---

## 4. Research Landscape as a named analytical object

A landscape should be explicitly defined, versioned, and reproducible.

Suggested object:

```text
research_landscape
- landscape_id
- title
- description
- scope_definition
- inclusion_policy
- seed_papers
- seed_reviews
- corpus_snapshot
- created_at
- updated_at
- ontology_version
- analysis_version
```

Example:

```text
Landscape: Singlet Fission — Theory, Dynamics, and Experiment
Scope: molecular and condensed-phase SF, mechanism/state/coupling/rate/dynamics/spin/material development
```

A landscape is not equivalent to:

- one Zotero collection;
- one keyword search;
- all papers containing a phrase;
- the full WoS corpus.

Those are inputs to a landscape definition.

---

## 5. Corpus construction and boundary control

Field analysis is highly sensitive to corpus definition. The system must preserve how the corpus was constructed.

Recommended multi-source process:

### 5.1 Curated seeds

Use:

- user-selected landmark papers;
- high-quality review/perspective papers;
- core Zotero collections;
- known major authors/method papers.

### 5.2 Broad WoS background set

Use broad topic/author/manual WoS exports to avoid restricting the landscape to the user’s existing Zotero holdings.

### 5.3 Citation expansion

Use:

- backward references;
- forward citations when available;
- co-citation neighborhood;
- bibliographic-coupling neighborhood;
- citation-frontier expansion.

A cascading citation-expansion approach is valuable because keyword-only corpus construction can miss conceptually important papers using different terminology.

### 5.4 Membership status

Do not make every discovered paper automatically a core landscape member.

Suggested state:

```text
CORE
SUPPORTING
CONTEXTUAL
CANDIDATE
EXCLUDED
```

Each membership decision should preserve its basis:

```text
USER_CURATED
REVIEW_ANCHOR
TOPIC_QUERY
CITATION_EXPANSION
CO_CITATION
BIBLIOGRAPHIC_COUPLING
AI_CANDIDATE
MANUAL_DECISION
```

---

## 6. Domain ontology: from bibliographic records to scientific contributions

Citation graphs cannot answer “who developed which model?” without representing what papers actually contribute.

The Research Landscape layer therefore needs a contribution ontology.

### 6.1 General contribution entities

At minimum:

```text
ResearchQuestion
Phenomenon
System
Material
ElectronicState
Mechanism
Model
Method
Observable
Property
Environment
Dataset
Benchmark
Experiment
Result
Limitation
OpenQuestion
```

Domain-specific landscapes may extend this vocabulary.

### 6.2 Paper contribution predicates

Recommended baseline:

```text
STUDIES
USES_SYSTEM
USES_MATERIAL
USES_STATE
OBSERVES
MEASURES
COMPUTES
USES_METHOD
USES_MODEL
PROPOSES_MODEL
PROPOSES_MECHANISM
INTRODUCES
EXTENDS
GENERALIZES
REFINES
BENCHMARKS
VALIDATES
COMPARES_WITH
SUPPORTS
CHALLENGES
CONTRADICTS
REINTERPRETS
APPLIES_TO
IDENTIFIES_LIMITATION
IDENTIFIES_OPEN_QUESTION
```

These are scientific relations, not generic semantic embeddings.

### 6.3 Example

```text
Paper P
  --USES_SYSTEM--> pentacene dimer
  --USES_STATE--> S1S0
  --USES_STATE--> TT
  --USES_STATE--> CT
  --USES_METHOD--> electronic-structure method M
  --COMPUTES--> electronic coupling
  --USES_MODEL--> rate model R
  --SUPPORTS--> superexchange mechanism
  --IDENTIFIES_LIMITATION--> dimer model vs crystal
```

The precise content must come from the paper/review evidence, not from the schema example.

---

## 7. Evidence contract for contribution extraction

AI is appropriate for contribution extraction, but only under a bounded evidence contract.

Every extracted assertion should support:

```text
contribution_assertion_id
paper_id / wos_ut
subject
predicate
object
section/page locator
source_excerpt_hash or evidence pointer
assertion_status
confidence
extractor_prompt_version
model/version
review_status
```

Suggested status:

```text
EXPLICIT_PRIMARY
EXPLICIT_REVIEW_SUMMARY
SUPPORTED_INFERENCE
CANDIDATE_NEEDS_REVIEW
CONFLICTING
REJECTED
```

Primary-paper evidence outranks review-summary attribution when deciding who first introduced a method/model.

A review is useful for discovering candidate milestones and vocabulary, but it should not silently become proof of priority.

---

## 8. Recommended extraction workflow: review-first, primary-paper verification

Reading thousands of primary papers blindly is inefficient.

A better pipeline is:

```text
high-quality reviews / perspectives
        ↓
bootstrap domain ontology
        ↓
extract candidate models, methods, milestones, open questions
        ↓
resolve cited primary papers
        ↓
inspect primary-paper evidence
        ↓
freeze verified contribution assertions
        ↓
expand to neighboring papers where graph structure suggests missing branches
```

This makes reviews navigation aids rather than unverified ground truth.

For mature or controversial milestones, require multiple evidence sources or expert review.

---

## 9. Historical roots: RPYS

Reference Publication Year Spectroscopy should provide the first historical layer.

RPYS detects publication-year peaks among all references cited by the field and is useful for finding foundational works that may not be obvious from topic searches or current citation rankings.

Outputs:

```text
reference publication year
peak strength
responsible references
current citation support in the landscape
resolved Paper/WoS identity
landmark candidate status
```

RPYS should answer:

> On which older scientific works does this field repeatedly stand?

It should not by itself label a paper as the originator of a specific model; that requires contribution evidence.

Possible extension:

- RPYS-CO around a marker paper/model to recover a more specific intellectual ancestry.

---

## 10. Evolutionary backbone: main-path and multi-path analysis

A raw citation graph becomes unreadable at field scale. Main-path analysis can extract a smaller backbone of knowledge flow.

Traditional main-path analysis uses traversal weights on citation edges to identify important paths through a citation network. Modern variants improve this by incorporating semantic/citation-context information and by identifying multiple parallel trajectories rather than forcing an entire field into one line.

Paperazzi should therefore avoid a single canonical “main path”.

Recommended outputs:

```text
GLOBAL_BACKBONE
KEY_ROUTE_PATHS
PARALLEL_TRAJECTORIES
ALTERNATIVE_BRANCHES
RECENT_FRONTIER_PATHS
```

Each path should have:

- structural score;
- topical coherence;
- time span;
- representative papers;
- contribution labels;
- confidence/coverage warning.

The user must be able to see important papers excluded from the path and why.

---

## 11. Milestone detection should combine structure and contribution evidence

A “milestone” is not simply a highly cited paper.

Candidate milestone signals:

```text
citation backbone position
RPYS peak contribution
citation burst
high betweenness / bridge role
high co-citation centrality
large change in subsequent vocabulary/method usage
explicit “introduced/proposed” contribution evidence
independent adoption by multiple groups
later review recognition
```

Recommended representation:

```text
milestone_id
landscape_id
paper_id
milestone_type
structural_evidence
contribution_evidence
adoption_evidence
review_recognition
confidence
human_status
```

Milestone types may include:

```text
FOUNDATIONAL
MODEL_INTRODUCTION
METHOD_INTRODUCTION
EXPERIMENTAL_DISCOVERY
MECHANISM_SHIFT
BENCHMARK
CONTROVERSY
RESOLUTION
SCALING_BREAKTHROUGH
APPLICATION_BREAKTHROUGH
```

Do not automatically assign historical priority from an LLM output alone.

---

## 12. Burst and emerging-front analysis

The landscape should identify when concepts, methods, or papers suddenly gain attention.

Potential signals:

- citation burst;
- publication burst;
- keyword/topic burst;
- new-author/community influx;
- rapid increase in cross-cluster citation;
- abrupt emergence of a method entity in contribution extraction.

Display as temporal bands rather than only counts:

```text
Charge transfer       ━━━━━━━━━
Triplet pair              ━━━━━━━━━━━
Vibronic effects               ━━━━━━━
Spin dynamics                      ━━━━━━━
```

“Emerging” and “declining” must be distinguished using direction/time trends, not a single static thematic-map quadrant.

---

## 13. Thematic evolution

The landscape should model themes as time-dependent communities.

For consecutive windows, determine whether a theme:

```text
PERSISTS
SPLITS
MERGES
EMERGES
DECLINES
DISAPPEARS
REBRANDS
```

Use more than keyword overlap. Useful continuity signals include:

- shared core papers;
- citation continuity;
- shared authors;
- contribution entities;
- weighted keyword/topic overlap.

Thematic evolution can be rendered as an alluvial/Sankey diagram with drill-down to the papers responsible for each transition.

---

## 14. Model and method genealogy

This should become one of Paperazzi’s signature views.

Example abstract structure:

```text
Model A
  |
  +-- INTRODUCED_BY --> Paper 1 / Person A
  |
  +-- EXTENDED_BY ----> Paper 2 / Person B
  |
  +-- BENCHMARKED_BY --> Paper 3
  |
  +-- CHALLENGED_BY --> Paper 4
  |
  +-- APPLIED_TO -----> System X / Y / Z
  |
  `-- REPLACED_OR_GENERALIZED_BY --> Model B
```

The same structure applies to computational methods, experimental techniques, mechanistic hypotheses, and rate/dynamics models.

A method genealogy should not be built from paper citation alone. Contribution/citation-context evidence must state the relation.

---

## 15. Citation-context relation mining

Later phases should distinguish why one paper cites another.

Useful relation classes:

```text
BACKGROUND
USES_METHOD
USES_MODEL
USES_DATA
EXTENDS
BENCHMARKS
COMPARES_WITH
SUPPORTS
CHALLENGES
CONTRADICTS
```

This is inspired by citation-context systems such as scite but should use chemistry/domain-specific predicates where useful.

A `USES_METHOD` citation should have more influence on method genealogy than a generic background citation.

---

## 16. Multi-layer scientific roadmap

Technology roadmapping provides a useful visualization principle: multiple interacting layers aligned on a time axis.

Paperazzi should adapt this into a **Scientific Roadmap**.

Generic layout:

```text
TIME ─────────────────────────────────────────────────────────→

Experimental observation
    ───────────────────────────────────────────────────────────

Phenomenon / mechanism
    ───────────────────────────────────────────────────────────

Theory / model
    ───────────────────────────────────────────────────────────

Electronic-structure / characterization methods
    ───────────────────────────────────────────────────────────

Dynamics / kinetic methods
    ───────────────────────────────────────────────────────────

Materials / systems / scale
    ───────────────────────────────────────────────────────────

Validation / benchmark
    ───────────────────────────────────────────────────────────

Application
    ───────────────────────────────────────────────────────────
```

Each milestone card should connect vertically to related developments in other lanes.

This representation is better than a single chronological list because scientific progress often depends on interactions between experiment, theory, computational capability, and materials.

---

## 17. Evidence–Gap Matrix

Evidence and gap maps from medicine/policy provide a useful transferable idea: use a two-dimensional framework where each cell represents how much and what kind of evidence exists for a combination of research dimensions.

For a chemistry landscape, candidate axes might be:

```text
ROWS: capability / research task
COLUMNS: system scale / environment / material class
```

Example structure:

```text
                         monomer  dimer  oligomer  crystal  disordered  device
Electronic states          ●       ●●      ●●       ●●●
Coupling                            ●●●     ●●       ●●
Rate theory                         ●●●     ●●       ●●
Nonadiabatic dynamics               ●●      ●        ●
Spin dynamics                       ●●               ●
Environment                         ●       ●●       ●●
Experiment validation       ●       ●●      ●●       ●●●
Predictive design                    ●       ●        ●
```

A cell must be drillable into:

- paper count;
- independent-group count;
- methods used;
- benchmark/validation evidence;
- time distribution;
- key papers;
- contradictory evidence;
- confidence and corpus completeness.

An empty cell is only a candidate gap. The system must distinguish:

```text
NO_EVIDENCE_FOUND
LOW_EVIDENCE
EVIDENCE_OUTSIDE_LOCAL_CORPUS_POSSIBLE
NOT_APPLICABLE
EXPLICITLY_IDENTIFIED_OPEN_PROBLEM
```

This prevents “not in our database” from being mislabeled as “nobody has studied it”.

---

## 18. Field Capability Maturity Profile

The user’s proposed “axis length = maturity” idea is useful, but a research field should not be reduced to one global maturity number.

Paperazzi should define a multidimensional **Field Capability Maturity Profile (FCMP)**.

### 18.1 Capability axes

For excited-state theory/dynamics landscapes, candidate axes include:

```text
1. Electronic-state definition and representation
2. State characterization / diabatic representation
3. Potential-energy-surface topology
4. Electronic/nonadiabatic/spin coupling calculation
5. Vibronic and nuclear-motion treatment
6. Rate theory
7. Nonadiabatic dynamics
8. Spin dynamics
9. Environmental / condensed-phase treatment
10. Morphology / mesoscale treatment
11. Experiment–theory validation
12. Method benchmark / reproducibility
13. Transferability across molecular/material classes
14. Multiscale integration
15. Predictive design capability
```

A landscape may customize this list, but axis definitions must be versioned.

### 18.2 Maturity should be evidence-based and multidimensional

For each capability axis, evaluate components such as:

```text
BREADTH
  How many relevant systems/material classes/scales are covered?

DEPTH
  Are only proof-of-concept methods present, or are high-level/systematic methods available?

INDEPENDENT_REPLICATION
  Have multiple independent groups reproduced/used the capability?

BENCHMARKING
  Are competing methods systematically compared against trustworthy references?

EXPERIMENTAL_VALIDATION
  Are predictions compared to relevant observables/time scales?

TRANSFERABILITY
  Does the approach work beyond a narrow model system?

INTEGRATION
  Is the capability integrated with adjacent steps in the workflow?

STANDARDIZATION / REPRODUCIBILITY
  Are common benchmarks, protocols, or reusable software/data established?
```

### 18.3 Suggested maturity rubric

Do not directly equate publication count with maturity.

A useful initial 0–5 rubric:

```text
0  No meaningful evidence found in the defined landscape
1  Conceptual proposal / isolated proof of principle
2  Multiple demonstrations but narrow systems or strong unresolved method dependence
3  Multi-group application with comparative evidence and growing reproducibility
4  Systematic benchmarking/validation and broad transfer across representative systems
5  Mature predictive capability with standardized/reproducible workflows and demonstrated integration
```

Each score must include:

```text
score
confidence
supporting papers
contradictory papers
coverage indicators
reasoning/evidence summary
human review state
```

### 18.4 Do not copy Technology Readiness Level blindly

TRL is useful inspiration for staged maturity, but it was designed for technology readiness/deployment and is one-dimensional for many research questions. Paperazzi’s capability profile should remain multi-axis and expose evidence rather than pretend to produce a universal readiness level.

---

## 19. Preferred visualizations for maturity and gaps

### 19.1 Primary: capability heatmap

A heatmap is better than a radar chart for detailed comparison because every cell can expose evidence and uncertainty.

```text
Capability                  Singlet fission    Nucleobase dynamics    Domain C
State representation            ████                 █████
PES/topology                     ███                  █████
Coupling                         ████                 ████
Rate theory                      ████                 ██
Nonadiabatic dynamics            ██                   █████
Environment                      ██                   ████
Validation                       ███                  ████
Benchmark/reproducibility        ██                   ███
Multiscale integration           ██                   ███
```

The bars above are illustrative only; production scores require analysis.

### 19.2 Secondary: radar / spider summary

Radar charts are useful as a compact overview but can visually exaggerate area. Use only as a summary linked to the evidence-rich heatmap.

### 19.3 Evidence density overlay

A maturity score with only three papers should look different from the same score supported by fifty independent papers.

Show:

- score;
- evidence count;
- independent-group count;
- confidence.

---

## 20. Field comparison

Paperazzi should allow comparison of landscapes using the same capability schema.

Important rule:

> A field comparison is only valid where the axis definitions and evidence rules are compatible.

Comparison views:

```text
capability heatmap
radar summary
per-axis evidence table
time-to-maturity plot
benchmark density
experiment/theory agreement density
method diversity
system-scale coverage
```

The system should support the question:

> Why does field A appear more mature on nonadiabatic dynamics but less mature on rate-model standardization than field B?

The answer must drill down to papers/methods/benchmarks, not stop at the chart.

---

## 21. Singlet fission as the first Research Landscape benchmark

Singlet fission (SF) is the best first benchmark because:

- the local Zotero/WoS corpus is already substantial;
- the user can expert-check conclusions;
- SF spans experiment, mechanism, electronic structure, coupling, rate theory, dynamics, spin, materials, and device relevance;
- several well-developed theoretical branches coexist with unresolved conceptual/mechanistic questions;
- it is complex enough to test multi-trajectory analysis rather than a trivial linear history.

### 21.1 Initial SF ontology candidates

#### Phenomena / states

```text
S1 / local excitation
CT states
correlated triplet pair
separated triplets
quintet / spin manifolds
```

#### Mechanism classes

```text
direct coupling
sequential CT
virtual-CT / superexchange
vibronic mediation
coherent/incoherent variants
```

#### Theory/method capability classes

```text
electronic-state construction
interstate coupling
rate theory
Redfield / open-system models
surface-hopping / trajectory dynamics
quantum dynamics
spin dynamics
morphology / crystal / environment
```

These are starting ontology candidates only and should be refined from reviews and primary papers.

### 21.2 SF roadmap lanes

Recommended initial roadmap:

```text
EXPERIMENT
TRIPLET-PAIR CHARACTERIZATION
MECHANISM
ELECTRONIC STRUCTURE / STATE MODEL
COUPLING
RATE THEORY
DYNAMICS
SPIN DYNAMICS
MATERIAL SCALE / MORPHOLOGY
VALIDATION / BENCHMARK
DEVICE / PREDICTIVE DESIGN
```

### 21.3 Candidate anchor reviews / perspectives

Use reviews as ontology and milestone-discovery anchors, then verify primary papers. Useful anchors include:

- David Casanova (2018), *Theoretical Modeling of Singlet Fission*, covering electronic states, rates, interstate couplings, excited-state dynamics, and materials;
- Geyer & Zhu (2019), *Triplet Pair States in Singlet Fission*, emphasizing triplet-pair intermediates and rate-definition debates;
- crystalline-SF perspectives discussing CT/quintet character, phonon/electron coupling, decoherence, triplet-pair dissociation, and transport;
- user-curated reviews and primary papers already present in Zotero/WoS.

### 21.4 SF validation questions

A correct landscape should eventually answer with evidence:

- Which papers introduced major direct/CT/superexchange mechanism models?
- How did electronic coupling calculations evolve?
- When did explicit rate-theory formulations become influential?
- Which dynamics methods were first applied, and to what system scales?
- How does the treatment of the correlated triplet-pair state change over time?
- Which approaches reached crystals or condensed phases rather than dimers?
- How much independent benchmarking exists for couplings, rates, and dynamics?
- Where do experiments discriminate between competing theoretical models?
- Which open issues repeatedly survive across reviews and decades?

---

## 22. Nucleobase excited-state dynamics as a comparator

A second benchmark should be a scientifically adjacent but structurally different field: nucleobase excited-state dynamics.

Why it is useful:

- it has a long history of ultrafast experiment and computational dynamics;
- isolated bases, solution, clusters, and larger nucleic-acid systems create a clear scale hierarchy;
- conical intersections, internal conversion, intersystem crossing, solvent effects, and nonadiabatic dynamics provide distinct capability axes;
- reviews explicitly compare theoretical dynamics methods and experimental time scales.

Relevant review literature documents extensive use of on-the-fly nonadiabatic dynamics, historically including Tully-style surface hopping with multiconfigurational electronic structure for isolated nucleobases, while also emphasizing strong dependence on the chosen electronic-structure/dynamics method and continuing challenges in larger/condensed systems.

The comparator should test whether Paperazzi can distinguish:

```text
high publication volume
from
high methodological maturity
from
high experimental validation
from
high cross-scale integration
```

No SF-vs-nucleobase maturity scores should be frozen before the common capability ontology and evidence rubric are validated.

---

## 23. Research-field “missingness” must be defined carefully

There are at least four kinds of gaps:

```text
CORPUS_GAP
Paperazzi has not acquired the relevant literature.

EVIDENCE_GAP
Very little published work exists for a defined matrix cell.

METHOD_GAP
Work exists, but an important methodological capability is missing or weak.

VALIDATION_GAP
Methods exist, but benchmark/experimental validation is insufficient.

INTEGRATION_GAP
Individual components exist but have not been connected into an end-to-end workflow.
```

The UI should never collapse these into one “gap” label.

---

## 24. Contradictions and controversies are first-class data

A mature field history should not flatten disagreements.

Store contradiction structures such as:

```text
Claim A --SUPPORTED_BY--> Paper 1, Paper 2
Claim A --CHALLENGED_BY--> Paper 3
Claim B --ALTERNATIVE_TO--> Claim A
Review R --SUMMARIZES_CONTROVERSY--> {A, B}
```

Useful examples include disputes over:

- mechanism;
- state character;
- rate definition;
- method accuracy;
- experimental assignment;
- whether a model generalizes across materials.

The timeline should be able to show the lifetime of a controversy and whether later work resolved, reframed, or simply bypassed it.

---

## 25. People and schools inside a Research Landscape

Once the public-web person-evidence layer matures, Paperazzi can overlay academic genealogy and events on the scientific contribution graph.

This enables questions such as:

- Which research school introduced a particular model family?
- Did a method spread through advisor–student lineages or through independent adoption?
- Which former trainees established independent branches?
- Which conference/workshop communities preceded bursts of a new approach?

Important: these are derived sociological interpretations. Underlying mentorship/event facts must remain distinct from scientific contribution facts.

---

## 26. Funding, institutions, and capability evolution

WoS funding and affiliation data can support additional layers:

```text
Funder -> papers -> capability/topic
Institution -> authors -> contributions
Country/region -> capability adoption over time
```

Potential analyses:

- which funders supported the emergence of a method branch;
- which institutions act as bridges between experimental and theoretical communities;
- geographic diffusion of a method;
- whether a research front is dominated by one group or independently reproduced.

These should be descriptive evidence, not causal claims unless additional evidence supports causality.

---

## 27. UI specification

A Research Landscape should expose several synchronized views.

### 27.1 Landscape overview

```text
Corpus size
Time span
Major clusters
Key authors/groups
Historical roots
Current research fronts
Major unresolved questions
Capability summary
```

### 27.2 Multi-lane scientific timeline

Primary overview of development across experiment/theory/method/system/application lanes.

Features:

- zoom by decade/year;
- milestone cards;
- branch lines;
- controversy bands;
- citation burst overlays;
- click milestone -> primary evidence.

### 27.3 Model/method genealogy

Interactive directed graph showing introduction, extension, benchmark, challenge, and application relations.

### 27.4 Theme-evolution alluvial map

Show themes splitting/merging across time windows.

### 27.5 Evidence–Gap Matrix

Interactive matrix with cell drill-down.

### 27.6 Capability heatmap

Compare maturity across axes and/or across two landscapes.

### 27.7 Radar summary

Secondary compact visualization only.

### 27.8 “Why?” panel

Every milestone, maturity score, gap, and inferred trajectory needs a side panel exposing:

```text
supporting papers
contradictory evidence
analysis method
AI extraction evidence
coverage warning
human review status
```

---

## 28. Data model for the Research Landscape layer

Logical tables/entities:

```text
research_landscapes
landscape_corpus_snapshots
landscape_memberships
landscape_ontology_versions

landscape_concepts
landscape_concept_aliases

paper_contributions
contribution_assertions
contribution_evidence

contribution_relations
citation_context_relations

landscape_milestones
landscape_trajectories
trajectory_members

landscape_themes
theme_time_slices
theme_transitions

capability_schemas
capability_axes
capability_assessments
capability_evidence

gap_map_schemas
gap_map_cells
gap_map_evidence
```

This is derived/domain-specific information and should not pollute WoS source tables.

A separate future `analytics.sqlite3` is attractive because landscapes can be rebuilt and versioned independently of source ingestion. If initially stored in the Paperazzi database, provenance boundaries must remain equally explicit.

---

## 29. AI execution architecture

AI work in this layer should be task-specific, evidence-bounded, and repeatable.

Recommended agents/tasks:

```text
REVIEW_ONTOLOGY_BOOTSTRAP
PRIMARY_PAPER_CONTRIBUTION_EXTRACTION
CITATION_CONTEXT_CLASSIFICATION
MILESTONE_EVIDENCE_REVIEW
CONTROVERSY_EXTRACTION
OPEN_QUESTION_EXTRACTION
CAPABILITY_EVIDENCE_SUMMARY
LANDSCAPE_NARRATIVE_SYNTHESIS
```

Each should have:

- input scope;
- required evidence pointers;
- output schema;
- prompt version/hash;
- allowed predicates;
- confidence/status;
- validation rules.

The final narrative agent should consume frozen graph/contribution/maturity results; it must not invent missing milestones to make the story smoother.

---

## 30. Human/expert review model

Not every contribution assertion needs manual review, but high-impact conclusions should.

Require manual/expert review for:

- `FIRST_INTRODUCED_BY` / historical priority claims;
- milestone designation above a threshold;
- contradiction-resolution claims;
- field maturity scores used for cross-field comparison;
- strong “research gap” claims;
- claims that a person or group “developed” a model when contribution evidence is ambiguous.

Routine `USES_METHOD`, `STUDIES_SYSTEM`, and similar explicit assertions can be AI-extracted with automated validation and sampled QA.

---

## 31. Development sequence

### Phase RL-0 — Landscape contract

- define landscape identity and corpus snapshot;
- define membership states;
- define FACT / DERIVED / INTERPRETATION separation;
- connect Graph Analytics outputs.

### Phase RL-1 — SF ontology bootstrap

- select 5–15 high-quality SF reviews/perspectives;
- extract candidate ontology;
- normalize model/method/mechanism/state aliases;
- freeze ontology v1 after expert review.

### Phase RL-2 — Contribution extraction v1

Start with a manageable set of landmark/core primary papers.

Extract:

- research question;
- system/material;
- states;
- mechanism;
- model;
- electronic-structure method;
- dynamics/rate method;
- observables;
- key result;
- validation;
- limitation/open question;
- relation to prior work.

### Phase RL-3 — Historical structure

Compute/integrate:

- RPYS;
- citation backbone;
- multiple main paths;
- citation/topic bursts;
- milestone candidates.

Then expert-check candidate milestones against primary evidence.

### Phase RL-4 — Scientific roadmap

Build first multi-lane SF timeline with verified milestone cards and model/method branches.

### Phase RL-5 — Evidence–Gap Matrix

Define SF capability × scale/system matrix and populate it from structured contributions.

### Phase RL-6 — Capability maturity v1

Define common excited-state dynamics capability schema and scoring rubric.

Produce evidence-backed SF capability profile.

### Phase RL-7 — Nucleobase comparator

Build a smaller nucleobase landscape using the same common capability schema.

Compare SF vs nucleobase dynamics and revise the maturity rubric if expert interpretation shows systematic bias.

### Phase RL-8 — Generalize beyond photochemistry

Only after the two benchmarks succeed should landscape schema/configuration become a reusable user-facing feature for arbitrary fields.

---

## 32. Acceptance criteria

A Research Landscape implementation is acceptable only if:

1. a landscape can be reproduced from a frozen corpus snapshot and ontology version;
2. citation-network structure and AI-extracted scientific contributions remain distinguishable;
3. every model/method genealogy edge has evidence;
4. a timeline milestone can be opened to the primary papers supporting it;
5. reviews guide discovery but do not silently establish historical priority;
6. multiple research trajectories can coexist;
7. incomplete WoS CR coverage is exposed as an uncertainty source;
8. gap claims distinguish corpus gaps from genuine evidence/method/validation/integration gaps;
9. maturity scores expose supporting and contradictory evidence plus confidence;
10. field comparison uses a shared, versioned capability schema;
11. AI narrative output can be regenerated from structured results and is not the sole storage of the analysis;
12. SF expert review finds the reconstructed history scientifically recognizable and useful rather than merely bibliometrically plausible.

---

## 33. Initial deliverables for the Singlet Fission benchmark

The first complete benchmark should produce:

```text
SF landscape corpus definition
SF ontology v1
citation/co-citation/coupling map
RPYS historical-root plot
major citation/main-path trajectories
model/mechanism genealogy
method genealogy
multi-lane development timeline
thematic-evolution view
major controversies/open questions
evidence-gap matrix
capability maturity profile
key people/groups per trajectory
machine-readable evidence package
human validation report
```

A successful benchmark should allow a domain expert to move from a high-level statement such as:

> “nonadiabatic dynamics appears less developed than electronic-state/coupling theory in this portion of SF research”

to the exact matrix cells, papers, methods, benchmark status, system scales, and timeline evidence supporting or contradicting that statement.

---

## 34. Methodological inspirations

The design deliberately combines methods from several traditions.

### Literature discovery / structural similarity

- ResearchRabbit, Connected Papers, Litmaps, Inciteful;
- bibliographic coupling and co-citation;
- citation-path exploration.

### Science mapping

- VOSviewer-style bibliometric networks;
- bibliometrix thematic maps and thematic evolution;
- CiteSpace-style temporal/burst/turning-point analysis;
- RPYS for historical roots.

### Knowledge evolution

- main-path analysis and modern multi-path/semantic variants;
- citation-context analysis;
- technology roadmapping adapted to scientific layers.

### Contribution representation

- Open Research Knowledge Graph (ORKG) work on machine-actionable research contributions and comparisons;
- scientific contribution graph / prerequisite-relation work as a future-looking model for automated roadmapping.

### Gap and maturity analysis

- Evidence and Gap Maps using explicit two-dimensional frameworks;
- systematic mapping studies for identifying saturated vs underdeveloped subareas;
- maturity/readiness models only as conceptual inspiration, with explicit recognition that a research field requires a multidimensional capability profile rather than one TRL-like scalar.

---

## 35. Reference starting points

Useful methodological references include:

- Hummon & Doreian (1989), original main-path analysis tradition;
- recent semantic/multi-trajectory main-path work in *Journal of Informetrics*;
- Marx, Bornmann, Barth & Leydesdorff, RPYS historical-root analysis;
- Haunschild & Bornmann, RPYS practical methodology;
- Aria/Cuccurullo and bibliometrix work on science mapping and thematic evolution;
- Phaal, Farrukh & Probert (2004), multi-layer technology roadmapping;
- ORKG publications on representing and comparing research contributions;
- recent methodological reviews of Evidence and Gap Maps;
- recent work on scientific contribution graphs for literature-based roadmapping.

Domain benchmark references should initially include major SF reviews/perspectives and nucleobase-dynamics reviews, but all field-history conclusions must ultimately trace to the primary evidence represented in Paperazzi.
