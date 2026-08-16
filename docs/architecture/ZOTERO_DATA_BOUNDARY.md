# Zotero data boundary

**Status:** Architecture decision, effective from Phase 2 onward.

Paperazzi treats Zotero as a **read-only metadata source**, not as a dataset that must be repaired, completed, or validated for scholarly completeness.

## Core rule

> Extract whatever is present in `zotero.sqlite`; preserve missing values as missing; never block ingestion because bibliographic metadata is incomplete.

Paperazzi does not attempt to make the Zotero library complete or correct.

Examples that are valid input states:

- journal article with no creators;
- item with no DOI;
- attachment metadata whose local file does not exist;
- item with partial journal/year/issue/page metadata;
- group-library records with different metadata quality;
- deleted or stale historical Zotero records retained for audit.

These are data states, not ingestion failures.

---

## 1. What Paperazzi reads from Zotero

The Zotero ingestion layer reads database metadata only:

- libraries;
- bibliographic item identity and type;
- item fields stored in Zotero;
- creator records and creator order/type;
- collections;
- tags;
- attachment metadata;
- deletion state;
- Zotero bookkeeping fields needed for change detection/audit.

The reader may inspect the filesystem only to answer whether a local attachment file currently exists and to construct a local path that can later be served by the web application.

---

## 2. What Paperazzi explicitly does not do

The Zotero ingestion layer does **not**:

- read or parse PDF content;
- extract first-page author/correspondence information from PDFs;
- OCR PDFs;
- infer missing authors from filenames or attachment contents;
- repair Zotero metadata;
- fetch missing PDFs;
- treat missing DOI/creator/title-adjacent fields as fatal;
- treat a missing local attachment file as an error;
- require Zotero's attachment storage to be complete.

A schema incompatibility or SQL/data-shape inconsistency that prevents safe extraction is still an ingestion error. Missing scholarly metadata is not.

---

## 3. Authorship semantics

### First author

When Zotero contains creators of type `author`, Paperazzi derives the first author from Zotero creator order (`orderIndex`).

If no suitable author creator exists, first author remains unknown.

### Corresponding author

Zotero SQLite metadata is not assumed to contain corresponding-author information.

Paperazzi must **not parse local PDFs** to obtain it.

Corresponding-author status may therefore come only from:

1. an explicit Paperazzi manual assertion;
2. structured/public online metadata returned by the enrichment workflow;
3. online AI research with evidence/provenance.

Until such information exists:

```text
corresponding_author_status = UNKNOWN
```

This is normal and does not block author ingestion.

---

## 4. Attachment semantics

Attachments have two separate concepts:

### 4.1 Zotero attachment metadata exists

This is derived exclusively from `zotero.sqlite`.

### 4.2 Local file is currently available

For file-capable attachments, Paperazzi may resolve the stored path and perform a filesystem existence check.

The resulting state should be simple:

```text
NO_ATTACHMENT
ATTACHMENT_NO_LOCAL_FILE
LOCAL_FILE_AVAILABLE
UNRESOLVED_PATH
```

This status is informational only.

No attempt is made to determine *why* a file is missing (not synced, manually deleted, stale metadata, storage corruption, etc.) unless that becomes useful for another feature later.

For the web UI, a paper row can therefore expose:

```text
PDF: Available | Not local | None
```

When `LOCAL_FILE_AVAILABLE`, the Paperazzi backend can serve/open that file in the browser. The PDF is not parsed by Paperazzi.

---

## 5. Validation philosophy

Tests should validate **extractor correctness**, not Zotero completeness.

### Must pass

- source DB is opened read-only;
- compatible schema adapter is selected;
- canonical items can be produced without corrupt joins;
- `(libraryID, itemKey)` identity remains unique;
- creator order is preserved when creators exist;
- fields/collections/tags/attachments map correctly when present;
- deleted Zotero child records are not accidentally resurrected;
- malformed/unknown schema fails safely;
- missing values remain representable as `None`/empty collections;
- missing local files do not raise ingestion errors.

### Informational only

- number of items without creators;
- DOI coverage;
- number of local PDFs missing;
- attachment sync-state distribution;
- number of items without optional metadata;
- metadata quality differences between libraries.

These metrics may be logged, but they are not acceptance gates and should not trigger repair work.

---

## 6. Canonical model implication

`CanonicalZoteroItem` is a faithful normalized projection of Zotero, not a cleaned bibliographic record.

It should preserve absence explicitly:

```text
fields may be missing
creators may be empty
collections may be empty
tags may be empty
attachments may be empty
```

The downstream Paperazzi database can enrich this record with external evidence, but must preserve provenance so that Zotero-derived facts remain distinguishable from online enrichment.

---

## 7. Consequence for project phases

### Phase 2

Phase 2 is considered successful once the reader safely and correctly maps the real library. Metadata incompleteness and missing local files are not blockers.

The deleted-child-attachment filter remains a real reader correctness fix because otherwise Paperazzi would reconstruct data that Zotero has marked deleted.

### Phase 3

Proceed to:

- `paperazzi.sqlite3` persistence;
- scan manifests;
- canonical semantic hashes;
- `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` diff;
- persistence of attachment availability state.

Do not spend additional Phase 2 effort diagnosing missing authors, DOI gaps, or absent PDF files.

### Later enrichment

External/online enrichment is a separate domain. It can add:

- author identity;
- corresponding-author status;
- affiliations;
- education/history;
- ORCID/OpenAlex/Semantic Scholar identifiers;
- author news and new publications.

Those facts must never be confused with data directly extracted from Zotero.
