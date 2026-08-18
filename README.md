# Paperazzi

Paperazzi is a local-first scholarly knowledge system built around a personal Zotero library and an independently growable Web of Science (WoS) background corpus.

Zotero's local `zotero.sqlite`, `storage/`, and PDF files are read-only source data. Paperazzi never writes to Zotero. WoS exports are imported into a separate Paperazzi-owned database and may cover literature far beyond the Zotero collection.

## Current status

```text
Phase 1   Zotero SQLite reconnaissance                         PASS
Phase 2   production read-only Zotero schema adapter/reader    PASS
Phase 2.5 local PDF evidence + AI-supervised adaptive parsing  PASS
           deterministic PDF baseline                          FROZEN_V3
Phase 3   relational persistence + incremental scan state      PASS
Phase 3.1 persistence hardening                                PASS
Phase 4   author identity + authorship/reference resolution    PASS
Phase 5   backend + minimal web UI                             IN_PROGRESS
Phase 6   independent WoS background corpus + integration      IN_PROGRESS
```

The WoS architecture contract is:

`docs/architecture/WOS_BACKGROUND_CORPUS.md`

## Core data architecture

```text
Zotero Library                 WoS Background Corpus
(read-only personal corpus)    data/wos.sqlite3
       |                              |
       +------------+  +--------------+
                    v  v
                 Paperazzi
          data/paperazzi.sqlite3
          integration / identity /
          graph / query / web layer
                    ^
                    |
               Local PDF
          provisional fallback
```

Important boundaries:

- `wos.sqlite3` is independent of Zotero and contains no Zotero/Paperazzi identifiers.
- Paperazzi links a local `Paper` to WoS only through the Paperazzi-side `paper_wos_links` bridge using WoS `UT`.
- WoS coverage is **not** a completeness requirement. Missing WoS information never blocks Zotero ingestion, browsing, PDF access, identity work, or other Paperazzi tasks.
- `WOS_NOT_IN_LOCAL_CORPUS` means only that the currently imported local WoS corpus has no accepted match; it does not claim that the article is absent from Web of Science.
- For facts explicitly structured in a linked WoS Full Record, WoS is the preferred production source. Local PDF extraction remains fallback/provisional evidence and parser QA remains separately auditable.

## Mandatory local Python environment

Local Paperazzi development, real-database validation, Zotero/PDF integration tests, WoS import/matching, and local-AI execution **must use a dedicated micromamba environment named `Paperazzi`**.

The user's existing Anaconda `base` or other general-purpose Python environments are not Paperazzi dependency targets and must not be upgraded, downgraded, or otherwise modified for this project.

Canonical local environment:

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
dependency baseline = constraints/phase5-test.txt
```

Create/repair the environment from the repository root:

```bash
micromamba create -y -f environment/Paperazzi.yml
micromamba run -n Paperazzi python -m pip install -c constraints/phase5-test.txt -e ".[pdf,web]"
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

The environment check must report `"pass": true` before authoritative local testing begins.

## WoS corpus workflow

### 1. Export from Web of Science

For the current manual workflow, perform broad/overlapping WoS topic searches and export:

```text
Format: Plain Text File
Record Content: Full Record and Cited References
```

Broad over-coverage is intentional. The WoS corpus is background knowledge, not a mirror of Zotero.

### 2. Import any number of overlapping export files

```bash
micromamba run -n Paperazzi paperazzi-wos import savedrecs.txt
micromamba run -n Paperazzi paperazzi-wos import sf-broad.txt --label "SF broad search"
micromamba run -n Paperazzi paperazzi-wos import pentacene.txt --label "pentacene expansion"
```

Default WoS database:

```text
data/wos.sqlite3
```

Override with either:

```text
PAPERAZZI_WOS_DB=/path/to/wos.sqlite3
```

or CLI `--db`.

Imports are idempotent by WoS accession number (`UT`). Re-importing overlapping records updates current metadata, preserves import provenance, records citation-metric observations, and does not duplicate the scholarly record.

Useful corpus commands:

```bash
micromamba run -n Paperazzi paperazzi-wos stats
micromamba run -n Paperazzi paperazzi-wos search "singlet fission"
micromamba run -n Paperazzi paperazzi-wos frontier --limit 100
```

The `frontier` command ranks DOI-bearing references frequently cited by the local WoS corpus whose own Full Records have not yet been imported. It is a guide for future broad/manual WoS exports, not a completion queue.

### 3. Match Zotero/Paperazzi papers against the local WoS corpus

Run a dry match first:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --unmatched-output data/wos-unmatched.jsonl
```

Persist conservative matches and explicit coverage state with:

```bash
micromamba run -n Paperazzi python scripts/match_wos_corpus.py \
  --paperazzi-db data/paperazzi.sqlite3 \
  --wos-db data/wos.sqlite3 \
  --apply \
  --unmatched-output data/wos-unmatched.jsonl
```

The automatic matcher currently accepts only strong deterministic matches:

```text
DOI_EXACT
TITLE_EXACT
TITLE_YEAR_JOURNAL
```

Ambiguous cases remain unresolved. Missing cases remain normal and non-blocking.

### 4. Grow the corpus efficiently

Recommended order:

```text
broad topic searches
    -> match against Zotero
    -> cluster unmatched Zotero papers by topic/journal/author/tag
    -> broad cluster searches
    -> targeted high-value completion only when useful
    -> citation-frontier expansion
```

Do not search every missing Zotero title individually unless that paper is important enough to justify targeted completion.

## WoS data currently retained

The independent corpus stores and exposes, where present:

- `UT`, DOI, title, journal/source, publication metadata;
- abbreviated and full author names (`AU`, `AF`);
- ORCID and ResearcherID (`OI`, `RI`);
- author-address mappings and organizations (`C1`, `C3`);
- correspondence groups (`RP`) and e-mail contacts (`EM`);
- abstract;
- author keywords and Keywords Plus;
- WoS Categories, Research Areas, Citation Topics, indexes;
- funding agencies/grants and full funding acknowledgement (`FU`, `FX`);
- cited references (`CR`) including DOI-based local citation-edge resolution;
- WoS/total citation counts (`TC`, `Z9`) with observation history.

WoS `RP` is parsed using **group semantics**. For example:

```text
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, ...
```

means both Xie and Ma are corresponding authors. `EM` is contact information and is not itself used to define the corresponding-author role.

## Web application

Start Paperazzi:

```bash
micromamba run -n Paperazzi paperazzi-web
```

Default address:

`http://127.0.0.1:8765`

Default databases:

```text
data/paperazzi.sqlite3
data/wos.sqlite3
```

Overrides:

```text
PAPERAZZI_DB=/path/to/paperazzi.sqlite3
PAPERAZZI_WOS_DB=/path/to/wos.sqlite3
```

The browser now includes:

- Zotero/Paperazzi paper and author surfaces;
- explicit per-paper WoS state (`WOS_MATCHED`, `WOS_NOT_IN_LOCAL_CORPUS`, `WOS_MATCH_AMBIGUOUS`, `WOS_NOT_CHECKED`);
- WoS correspondence authors, affiliations/organizations, identifiers, abstract, keywords/topics, funding, citation metrics and references;
- an independent **WoS Corpus** search/detail surface;
- WoS corpus coverage statistics;
- citation-frontier view for planning additional manual exports;
- local PDF access and PDF-derived evidence as fallback/provenance, not as a WoS replacement.

WoS API endpoints include:

```text
GET  /api/wos/stats
GET  /api/wos/search
GET  /api/wos/records/{ut}
GET  /api/wos/records/{ut}/references
GET  /api/wos/frontier
GET  /api/wos/coverage
GET  /api/papers/{paper_id}/wos
POST /api/wos/match?apply=false|true
```

## Validation

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
├── constraints/
├── docs/
│   └── architecture/
│       └── WOS_BACKGROUND_CORPUS.md
├── prompts/local_ai/
├── schemas/
├── src/paperazzi/
│   ├── zotero_sqlite/
│   ├── ingest/
│   ├── local_evidence/
│   ├── wos/
│   ├── database/
│   ├── identity/
│   └── web/
├── migrations/
├── scripts/
├── tests/
└── data/
```

## Core semantic boundaries

```text
paper_creator_mention != canonical author
paper_reference       != cited paper
Paperazzi Paper       != WoS record
WoS cited reference   != resolved WoS target record
```

Every Zotero paper author remains recorded even when canonical identity is unresolved. Structured WoS evidence can supplement production presentation and identity/correspondence evidence without silently overwriting the source Zotero spelling or PDF provenance. Only accepted/resolved relations produce semantic graph edges.

## Safety rule

Zotero source data are read-only. Persistent state may write only to Paperazzi-owned paths. Local environment setup may modify only the dedicated micromamba environment `Paperazzi`, never the user's existing Anaconda/base environment.
