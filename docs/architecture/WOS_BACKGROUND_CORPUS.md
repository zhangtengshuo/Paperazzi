# WoS Background Corpus Architecture

**Status:** implementation baseline  
**Date:** 2026-08-18  
**Scope:** Paperazzi / Web of Science local corpus integration

## 1. Decision

Paperazzi adopts Web of Science (WoS) as an **independent scholarly background corpus**, not as a Zotero enrichment table.

The system is split into three source domains plus one integration/consumer layer:

```text
Zotero Library                 WoS Background Corpus
(read-only personal corpus)    (independent local scholarly corpus)
       |                                  |
       +---------------+  +---------------+
                       v  v
                    Paperazzi
               integration / identity /
               graph / query / web layer
                       ^
                       |
                  Local PDF
             provisional fallback
```

The WoS corpus has its own lifecycle and database. It may contain far more records than the user's Zotero library and must never depend on Zotero identifiers, collections, attachments, or Paperazzi `paper_id` values.

Default databases:

```text
data/paperazzi.sqlite3   Paperazzi-owned Zotero projection, identity, integration state
data/wos.sqlite3         independent WoS background corpus
```

## 2. Non-negotiable boundaries

1. `wos.sqlite3` contains no Zotero or Paperazzi foreign identity (`paper_id`, Zotero item key, collection id, attachment id).
2. WoS records are identified primarily by WoS accession number (`UT`, e.g. `WOS:001454467000035`). DOI is a strong cross-database identifier but not the WoS primary key.
3. Paperazzi links a Zotero-derived `Paper` to a WoS record only through an integration table in `paperazzi.sqlite3`.
4. WoS coverage is opportunistic and monotonic, **not a completeness requirement**. Missing WoS data must never block Zotero ingestion, Paperazzi validation, browsing, identity work, or PDF access.
5. Local PDF extraction remains available, but correspondence/affiliation/reference data extracted from PDF are provisional/fallback when equivalent structured WoS evidence exists.
6. Source provenance is always visible. WoS data never silently overwrite Zotero or PDF-derived evidence.

## 3. Source priority

For metadata that WoS explicitly structures, the production preference is:

```text
WoS structured Full Record
        |
        v
publisher structured metadata (future optional source)
        |
        v
local PDF deterministic extraction
        |
        v
local-AI PDF recovery
```

This priority does not delete or invalidate lower-priority evidence. It controls the preferred presentation/resolution source while preserving provenance and contradictions.

PDF forensic validation remains useful as QA for the fallback parser; it is no longer the required mechanism for populating correspondence across the full Zotero library.

## 4. WoS import format and ingestion model

Initial supported input is Clarivate Web of Science **Plain Text / Full Record and Cited References** export.

Important tags include:

```text
PT document type
AU abbreviated author names
AF full author names
TI title
SO source title
DT document type text
DE author keywords (when available)
ID Keywords Plus
AB abstract
C1 author-address mapping
C3 normalized organizations
RP corresponding/reprint address groups
EM e-mail addresses
RI ResearcherID
OI ORCID
FU funding agencies/grants
FX funding acknowledgement text
CR cited references
TC WoS Core Collection citation count
Z9 total citation count
DI DOI
WC WoS Categories
SC Research Areas
TO Citation Topics
PM PubMed ID
UT WoS accession number
DA export/update date
```

Import must be idempotent. Users should be able to repeatedly import broad, overlapping WoS searches without manually de-duplicating files or records.

```text
paperazzi-wos import savedrecs_001.txt
paperazzi-wos import sf-broad.txt
paperazzi-wos import pentacene.txt
```

`UT` drives record upsert. Each import batch is recorded with source filename/hash and counts. Re-importing a record may update current metadata and records time-varying citation metrics.

## 5. WoS corpus schema

The first implementation uses relational tables rather than a flat mega-table.

### 5.1 Core record

`wos_records`

- `ut` primary key
- DOI and normalized DOI
- title and normalized title
- source title
- document type
- abstract
- publication year/date
- volume/issue/pages/article number
- PMID
- current citation counts
- WoS category / research area / citation-topic raw fields
- raw Full Record text
- first/last import timestamps

### 5.2 Authors and identifiers

`wos_authors`

- record (`ut`)
- author order
- `AU` abbreviated form
- `AF` full form

`wos_author_identifiers`

- author row
- namespace (`ORCID`, `RESEARCHER_ID`)
- value
- raw value

AU/AF are position-aligned within a WoS record; the importer must preserve both forms.

### 5.3 Affiliations

`wos_addresses`

- record (`ut`)
- address order
- raw C1 address

`wos_author_addresses`

- author row
- address row

`wos_organizations`

- record (`ut`)
- normalized C3 organization strings

C1 bracket groups encode author-to-address relationships and must be retained rather than flattened into a record-level list only.

### 5.4 Correspondence

`wos_correspondence_groups`

- record (`ut`)
- group order
- raw RP group
- raw address

`wos_correspondence_members`

- correspondence group
- WoS author row
- raw abbreviated member name

**RP grammar is group-level.** Example:

```text
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, ...
```

means both `Xie, XY` and `Ma, HB` are members of that corresponding-address group and are corresponding authors.

Likewise:

```text
RP A; B; C (corresponding author), ADDRESS1.; D (corresponding author), ADDRESS2.
```

creates groups `{A,B,C}` and `{D}`. The parser must not interpret `(corresponding author)` as modifying only the immediately adjacent author name.

`EM` is stored independently as contact data. E-mail ordering must not be assumed to map positionally to RP author ordering.

### 5.5 Keywords, classifications, funding

`wos_keywords`

- record (`ut`)
- keyword
- type (`AUTHOR`, `KEYWORDS_PLUS`)

`wos_classifications`

- record (`ut`)
- namespace (`WC`, `SC`, `TO`, `WE`)
- value

`wos_funding`

- record (`ut`)
- raw `FU`
- raw `FX`

Normalized funder/grant extraction can be added without discarding the original WoS strings.

### 5.6 Citation graph

`wos_cited_references`

- source `ut`
- citation order
- raw CR text
- parsed DOI
- cited author/year/source/volume/page where available
- `target_ut` nullable

A cited reference remains first-class even when the target Full Record is absent from the local WoS corpus.

When a later import introduces a record whose normalized DOI matches an existing cited reference, the resolver fills `target_ut`. Thus the graph grows incrementally:

```text
external CR node -> later imported WoS record -> resolved local citation edge
```

False citation edges are worse than unresolved edges; DOI exact matching is authoritative for the initial resolver and weaker matching may be introduced separately with provenance/review state.

### 5.7 Import batches and metrics history

`wos_import_batches`

- batch id
- source filename
- SHA-256
- optional label/search note
- imported timestamp
- record/new/update counts

`wos_record_metrics`

- record (`ut`)
- observed timestamp
- batch id
- TC/Z9 counts

Repeated imports can therefore capture citation-count growth instead of merely overwriting it.

## 6. Paperazzi integration schema

The only required Paperazzi-owned bridge is `paper_wos_links` in `paperazzi.sqlite3`:

```text
paper_id
wos_ut
match_method
match_score
status
matched_at
notes
```

`wos_ut` is a logical external identifier, not a cross-SQLite foreign key.

Initial match priority:

1. normalized DOI exact -> automatic accepted link;
2. normalized title exact with year/journal sanity checks -> automatic accepted link;
3. title + year + journal/author composite -> candidate or accepted only under conservative rules;
4. fuzzy title -> review candidate;
5. no match -> normal `WOS_NOT_IN_LOCAL_CORPUS` state.

The integration layer must distinguish:

```text
WOS_MATCHED
WOS_NOT_IN_LOCAL_CORPUS
WOS_MATCH_AMBIGUOUS
WOS_NOT_CHECKED
```

`WOS_NOT_IN_LOCAL_CORPUS` does **not** mean the article is absent from Web of Science. It only means the currently imported local WoS corpus does not contain a resolved match.

## 7. Paper detail and provenance behavior

For a matched paper, Paperazzi consumes WoS information without copying the whole WoS record into `papers`.

The paper detail API/UI should expose, when present:

- WoS linkage state and UT;
- full WoS author names;
- corresponding authors from RP groups;
- affiliations and organizations;
- ORCID / ResearcherID;
- abstract;
- author keywords / Keywords Plus;
- WoS categories, research areas, citation topics;
- funding agencies/grants and acknowledgement text;
- current citation metrics and observation date;
- cited references, including whether each target is in the local WoS corpus and/or in Zotero;
- related/citation graph information as later query features.

When WoS is absent, Paperazzi continues normally and labels any PDF-derived correspondence/reference/affiliation presentation as local-PDF fallback/provisional evidence.

## 8. Standalone WoS corpus surface

Because the WoS corpus is independent of Zotero, Paperazzi should expose a standalone WoS search/detail API and web surface. A WoS record need not be in Zotero to be browsable.

Search dimensions should eventually include:

- title / DOI / UT
- author / ORCID / ResearcherID
- keyword / topic
- journal
- organization
- funder

The UI clearly marks whether a WoS record is linked to a Zotero/Paperazzi paper.

## 9. Corpus filling strategy without API automation

API access and browser automation are explicitly **not required** for this phase.

Recommended workflow:

### Stage A — broad topical corpus

Perform broad WoS topic searches characteristic of the Zotero collection and export large overlapping batches as Plain Text / Full Record and Cited References. Over-coverage is desirable; the WoS corpus is background knowledge, not a mirror of Zotero.

### Stage B — unmatched-cluster expansion

After matching Zotero papers against the local WoS corpus, analyze unmatched Zotero records by title vocabulary, Zotero tags/collections, journals, years and frequent authors. Search WoS by clusters, not one title at a time.

### Stage C — targeted completion only where useful

Only after broad/cluster expansion should individual missing titles be considered. Important collections, high-value method papers and identity-critical papers can be prioritized. Remaining unmatched papers are legitimate and do not block any task.

### Stage D — citation-frontier expansion

Rank cited DOIs that are frequently referenced by the local WoS corpus but whose Full Records are not yet imported. These are high-value candidates for the next manual WoS export.

Corpus growth therefore has three independent drivers:

```text
topic expansion + Zotero coverage expansion + citation-frontier expansion
```

## 10. Implementation sequence

1. add this architecture contract;
2. implement independent WoS parser/schema/store/import CLI;
3. implement RP group grammar and tests;
4. implement CR parsing and DOI-based local citation resolution;
5. add `paper_wos_links` to Paperazzi persistence;
6. implement conservative Zotero/Paper -> WoS matcher;
7. add non-blocking WoS state and WoS detail to query/API layer;
8. render WoS/provenance information in paper detail;
9. add standalone WoS corpus API/UI and coverage reporting;
10. use coverage/unmatched/citation-frontier reports to guide manual WoS exports.

## 11. Acceptance principles

The implementation is correct only if all of the following hold:

- deleting or not creating `data/wos.sqlite3` does not break existing Paperazzi/Zotero workflows;
- importing overlapping WoS files is idempotent by UT;
- RP group semantics preserve all corresponding authors in a group;
- cited references are retained even when target records are absent;
- later WoS imports can resolve earlier CR DOI edges;
- missing WoS matches are visible but never task blockers;
- WoS information remains source-attributed and does not silently overwrite Zotero/PDF evidence;
- the WoS corpus remains independently useful even for records not in Zotero.
