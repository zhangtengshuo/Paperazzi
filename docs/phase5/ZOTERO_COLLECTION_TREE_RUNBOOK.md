# Zotero Collection Tree — Local Runbook

**Status:** Web navigation implementation guide  
**Date:** 2026-08-19  
**Source of truth:** live local Zotero `zotero.sqlite`, opened read-only

## 1. Purpose

Paperazzi now persists the complete Zotero collection catalog independently from item-to-collection membership and exposes it as a Zotero-style navigation sidebar in the local Web UI.

The production data flow is:

```text
Zotero collections table         Zotero collectionItems table
(full catalog, including empty)   (item membership + item order)
             |                              |
             +--------------+---------------+
                            v
                 Paperazzi Zotero scan
                            |
             +--------------+---------------+
             v                              v
     zotero_collections            zotero_item_collections
     catalog lifecycle             membership lifecycle
             |                              |
             +--------------+---------------+
                            v
                    Web collection tree
```

The frozen artifact under:

```text
docs/phase5/runs/20260819-zotero-collection-tree/
```

is a validation fixture only. It must never be used as the production runtime source.

## 2. Required migrations

From the repository root:

```bash
micromamba run -n Paperazzi alembic upgrade head
```

The current collection-navigation migrations are:

```text
0011_zotero_collection_catalog
0012_zotero_collection_scan_summary
```

They add:

```text
zotero_collections
zotero_scan_runs.collection_count
zotero_scan_runs.collection_catalog_hash
```

Stable collection identity is:

```text
(library_id, collection_key)
```

Collection names are mutable labels and are never identity keys.

## 3. Run a catalog-aware Zotero scan

The catalog-aware production scan entrypoint is:

```bash
micromamba run -n Paperazzi python scripts/scan_zotero_with_collections.py
```

Explicit paths:

```bash
micromamba run -n Paperazzi python scripts/scan_zotero_with_collections.py \
  --zotero-db /path/to/Zotero/zotero.sqlite \
  --zotero-data-dir /path/to/Zotero \
  --paperazzi-db data/paperazzi.sqlite3
```

The Zotero database is opened through the existing read-only probe path (`mode=ro` plus `query_only`). The script never writes to Zotero.

Expected output includes:

```text
status
scan_run_id
items_read
collections_read
item change counts
COLLECTION_NEW
COLLECTION_UPDATED
COLLECTION_UNCHANGED
COLLECTION_REMOVED
COLLECTION_RESTORED
```

A collection-only rename/reparent can change `collection_catalog_hash` while the bibliographic corpus hash remains unchanged. This is intentional.

## 4. Validate against the frozen 2026-08-19 snapshot

If the live Zotero library has not changed since the supplied snapshot, the Web tree summary should reproduce:

```text
collection_nodes               121
active_collection_memberships  3011
active_papers                  2513
papers_with_collection         2328
unfiled_papers                 185
```

Check:

```bash
curl -s 'http://127.0.0.1:8765/api/collections/tree?library_id=1&include_empty=true'
```

The frozen snapshot is allowed to validate these counts and example paths. A later live Zotero scan may legitimately differ.

## 5. Run tests

Targeted collection tests:

```bash
micromamba run -n Paperazzi \
  python -m unittest discover -s tests -p 'test_zotero_collection*.py' -v
```

Migration gate:

```bash
micromamba run -n Paperazzi \
  python -m unittest tests.test_phase3_migrations -v
```

Then run the full synthetic suite:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
```

## 6. Start Web

```bash
micromamba run -n Paperazzi paperazzi-web
```

Open the normal Paperazzi local Web page.

The Papers view should now have a responsive Zotero-style left sidebar containing:

```text
All papers
Unfiled
<root collection>
  <child collection>
    <grandchild collection>
...
```

Empty collection nodes are intentionally retained.

The expanded/collapsed state and last selected collection are persisted in browser `localStorage`.

## 7. Collection selection semantics

Clicking a collection shows **direct members of that collection by default**, matching the organizational meaning of a Zotero collection node.

The API also supports subtree queries:

```text
GET /api/collections/{collection_key}/papers?include_descendants=true
```

This is not the default Web selection behavior.

Tree nodes expose both:

```text
active_paper_count          direct members
subtree_active_paper_count  unique active papers anywhere below the node
```

A paper placed in both a parent/child or multiple descendant collections is counted only once in a subtree result.

## 8. Ordering semantics

The observed Zotero schema provides:

```text
collectionItems.orderIndex
```

for item order inside one collection. Paperazzi preserves and uses that value for collection paper lists.

The observed schema does **not** provide a reliable collection-node sibling-order column. Therefore siblings are displayed deterministically by:

```text
(name.casefold(), collection_key)
```

The UI must not invent a Zotero drag-order claim.

## 9. Empty collections and missing parents

The complete catalog is read directly from Zotero `collections`; it is not reconstructed from `collectionItems`.

Therefore:

- empty collections remain visible;
- a collection with only non-bibliographic Zotero items remains a catalog node even if its active-paper count is zero;
- removed collections remain historical rows in Paperazzi with `present_in_last_scan=0`;
- a later restoration reuses the stable `(library_id, collection_key)` identity.

If a collection references a parent that is absent from the current catalog, it is **not silently promoted to a root**. It appears in the diagnostic `orphaned` section returned by the tree API.

Parent cycles or disconnected malformed components are also surfaced in that diagnostic section, and recursive child edges are truncated so API JSON remains serializable.

## 10. Web/API contract

Implemented endpoints:

```text
GET /api/collections/tree
GET /api/collections/{collection_key}
GET /api/collections/{collection_key}/papers
GET /api/collections/unfiled/papers
GET /api/papers/{paper_id}/organization
GET /api/collections/ui.js
```

Normal paper detail also exposes:

```json
{
  "zotero_organization": {
    "collections": [],
    "collection_paths": [],
    "tags": []
  }
}
```

Tags remain a separate organization dimension from collection membership.

## 11. Performance contract

`GET /api/collections/tree` must not issue one query per collection node.

The current implementation performs three bounded source reads:

1. current collection catalog;
2. active paper memberships;
3. active paper total.

Direct/subtree counts, paths and hierarchy are then computed in memory.

This property must remain true when the collection tree grows beyond the current 121-node snapshot.

## 12. What to inspect after the first real scan

After running the new scan against the actual Zotero database, report at least:

```text
collection_count from scan ledger
collection_catalog_hash
/api/collections/tree summary
number of root nodes
number of orphaned nodes
All papers count
Unfiled count
several deep collection paths
one empty collection
one paper with multiple collection memberships
one collection paper list with orderIndex preserved
```

If the first real scan reproduces the frozen snapshot counts, that is strong evidence that the full catalog and membership projections are aligned. If it differs, compare against the current live Zotero state before treating the difference as a defect.
