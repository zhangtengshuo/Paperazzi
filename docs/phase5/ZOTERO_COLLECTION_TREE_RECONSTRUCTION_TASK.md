# Task: Reconstruct the Zotero left navigation tree in Paperazzi Web

Status: implementation handoff. This document describes the work for the remote
AI. It is not a request to modify the Zotero database.

## Objective

Make the Paperazzi Web application reproduce the useful semantics of Zotero's
left navigation pane:

1. show the complete collection hierarchy, including empty collections and
   collections whose current items are not active bibliographic papers;
2. show the number of active Paperazzi papers in every collection;
3. expand/collapse nested collections and select a collection to browse its
   papers;
4. preserve that one paper may belong to multiple collections;
5. preserve Zotero's item order within a collection where the source provides
   it;
6. show a paper's collection paths in the paper detail view.

Tags are already persisted and should be exposed as a separate, compatible
filter/display dimension if practical. They must not be confused with the
collection tree.

The result must remain a read-only presentation of Zotero-sourced organization
data. Do not write back to Zotero, and do not infer collections from WoS, PDFs,
authors, titles, or citation graphs.

## Materials prepared for implementation

The implementation/acceptance snapshot is:

`docs/phase5/runs/20260819-zotero-collection-tree/zotero_collection_tree_snapshot.json`

It contains:

- the full 121-node collection catalog from the validated Zotero snapshot;
- all 3,120 source `collectionItems` rows as source counts;
- the 3,011 active bibliographic collection memberships mapped to Paperazzi
  `paper_id` and Zotero item identity;
- all 2,513 active Paperazzi papers, including their collection keys;
- the 185 active papers without a collection;
- the current active tag summary;
- roots, child keys, depth, source membership counts, and active paper counts;
- known limitations of the observed Zotero schema.

The snapshot is a frozen fixture for remote implementation and tests. It is not
the runtime source of truth. Runtime data must continue to come from the
read-only Zotero scan and the Paperazzi-owned database.

## Current baseline

The current active Paperazzi database is:

`data/phase5-validation/phase5_5/paperazzi-phase5_5.sqlite3`

The current projection contains:

| Quantity | Count |
|---|---:|
| Active Paperazzi papers | 2,513 |
| Papers with at least one active collection membership | 2,328 |
| Active collection memberships | 3,011 |
| Collection keys appearing on active papers | 102 |
| Full Zotero collection catalog | 121 |
| Active papers without a collection | 185 |
| Active tag memberships | 3,060 |
| Active papers with tags | 1,458 |
| Distinct active tags including tag type | 726 |

## What already exists

The following code already reads and persists per-item organization data:

- `src/paperazzi/zotero_sqlite/adapters/userdata_125.py` reads nested
  collection membership, parent collection key and item order;
- `src/paperazzi/zotero_sqlite/reader.py` maps those rows into
  `CanonicalCollection`;
- `src/paperazzi/ingest/models.py` includes collections and tags in the
  organization payload/hash;
- `src/paperazzi/database/models.py` persists
  `zotero_item_collections` and `zotero_item_tags`;
- `src/paperazzi/database/persistence.py` replaces the current per-item
  organization projection transactionally when the organization hash changes.

The current collection row is an item-membership projection. It is not a global
collection catalog. It does not preserve a collection node that has no current
active bibliographic membership, and it does not provide a single authoritative
row for collection name/parent/library identity.

The current Web layer has no collection API, no collection query parameter, no
collection tree UI, and no collection/tag section in paper detail. The paper
list currently supports only text, year, venue and PDF filters.

## Required implementation

### 1. Add a first-class collection catalog

Add a Paperazzi-owned catalog projection, for example
`zotero_collections`. The exact table name is an implementation choice, but it
must preserve at least:

```text
library_id
collection_id                 diagnostic Zotero numeric ID
collection_key                stable Zotero collection identity within library
name
parent_collection_id          nullable diagnostic ID
parent_collection_key         nullable stable parent identity
present_in_last_scan
first_seen_run_id
last_seen_run_id
created_at
updated_at
```

Use `(library_id, collection_key)` as the stable uniqueness identity. Do not
use a Zotero numeric ID alone, and do not silently merge collections with the
same key from different libraries.

Keep `zotero_item_collections` as the many-to-many membership projection. It
should continue to preserve `order_index` for the position of an item inside a
collection. A collection catalog row and a membership row have different
lifecycles and must not be collapsed into one table.

The catalog must be populated from the Zotero `collections` table even when a
collection has no active bibliographic item. A removed collection should retain
historical state and become absent from the current tree, not be hard-deleted
from the audit history.

### 2. Extend the read/persist path

Add a separate collection-catalog read path to the validated Zotero adapter and
reader. The source query must read the complete `collections` table, not only
`collectionItems`. Include `libraryID`, `collectionID`, `key`,
`collectionName`, `parentCollectionID` and the parent key/name when available.

Persist the catalog transactionally in the same scan lifecycle as item
organization data. The operation must be idempotent. A collection-only change
must remain an organization change and must not change bibliographic hashes.

The observed Zotero schema has no explicit sibling-order column for collection
nodes. Do not fabricate one from `collectionItems.orderIndex`. For this corpus,
use and document the deterministic UI fallback:

```text
name.casefold(), then collection_key
```

Keep item `orderIndex` separately for paper ordering inside a selected
collection.

### 3. Add read-only Web APIs

The following contract is recommended; preserve existing endpoints and naming
conventions if an equivalent design is cleaner:

```text
GET /api/collections/tree?library_id=<id>&include_empty=true
GET /api/collections/{collection_key}?library_id=<id>
GET /api/papers?collection_key=<key>&library_id=<id>&limit=<n>&offset=<n>
```

The tree response should provide, for every node:

```text
library_id
collection_key
name
parent_collection_key
depth
children
active_paper_count
has_active_papers
```

The collection detail response should provide the node path, child nodes,
counts, and a paginated paper list. A paper returned by the general paper API
should expose its collection memberships or collection paths. Do not make the
client reconstruct the tree by issuing one request per node.

The query layer must avoid N+1 queries. Counts and paper membership should be
computed with bounded SQL queries or precomputed projections. Support empty
collections without returning an error or hiding the node.

### 4. Add Web UI navigation

Add a persistent collection navigation area, preferably a left sidebar on wide
screens and a collapsible panel on narrow screens. It must support:

- an explicit “All papers” root;
- collection roots and nested children;
- expand/collapse without losing the selected collection;
- visible active-paper counts;
- empty collection nodes;
- selected-node highlighting and breadcrumb/path display;
- pagination for the selected collection;
- papers belonging to multiple collections without duplication in the paper
  list;
- collection badges/paths in the paper detail page.

Keep the existing Papers, Authors, Identity Review, audit and WoS views working.
Do not replace the Paperazzi identity-author model with Zotero creator data.

Tags may be added as a second filter/sidebar section, but tags must not be
rendered as collection children.

### 5. Handle source edge cases

The implementation must explicitly test and handle:

- a root collection with no active papers, such as `0A_Fundation`;
- a nested path such as `0A_Fundation` → `0A_2024青基`;
- a deeper path such as `Programming` → `Julia` → `Makie`;
- a collection containing only deleted/non-bibliographic source items;
- a paper in multiple collections;
- an active paper in no collection;
- the same collection key in different libraries;
- a missing parent row in a malformed or partial historical snapshot;
- collection rename, reparenting, removal and restoration across scans;
- collection names and paper titles containing non-ASCII text.

If a parent is missing, keep the child visible under an explicit
“orphaned/missing parent” bucket and retain the raw parent key for diagnosis.
Do not drop the child or attach it to an arbitrary root.

## Acceptance criteria

The implementation is complete only when all of the following pass:

1. A fresh migration and scan can persist the full collection catalog and
   current memberships without changing paper/author/PDF behavior.
2. The fixture validates 121 collection nodes, 3,011 active memberships,
   2,328 papers with a collection and 185 papers without one.
3. The tree endpoint returns empty nodes and correct parent/child paths.
4. Selecting a node returns the correct paginated papers and does not duplicate
   papers with multiple memberships.
5. Paper detail exposes all collection paths and does not lose tags.
6. A repeated scan is idempotent; collection-only changes update organization
   state but not bibliographic state.
7. Removed collections disappear from the current tree while historical scan
   evidence remains queryable.
8. API/UI tests cover the edge cases above and the existing Web test suite still
   passes.
9. No Zotero database, Zotero storage, PDF or WoS database is modified by the
   implementation or tests.

## Suggested files to inspect first

```text
src/paperazzi/zotero_sqlite/adapters/userdata_125.py
src/paperazzi/zotero_sqlite/reader.py
src/paperazzi/ingest/models.py
src/paperazzi/database/models.py
src/paperazzi/database/persistence.py
src/paperazzi/web/queries.py
src/paperazzi/web/api.py
src/paperazzi/web/ui.py
tests/test_zotero_reader.py
tests/test_phase5_web.py
migrations/versions/0001_zotero_persistence.py
docs/phase5/runs/20260819-zotero-collection-tree/zotero_collection_tree_snapshot.json
```

Do not treat the fixture as permission to hard-code the current collection
names. The production implementation must read future Zotero scans and must
remain correct when collections are added, renamed, moved or deleted.
