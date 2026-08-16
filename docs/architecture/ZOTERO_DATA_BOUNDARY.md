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

A separate architectural decision, [`LOCAL_PDF_EVIDENCE.md`](LOCAL_PDF_EVIDENCE.md), defines how available local PDFs may be parsed as **optional evidence**. PDF parsing does not weaken the tolerant Zotero-ingestion rule.

---

## 1. Zotero metadata channel

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

The reader may inspect the filesystem only to answer whether a local attachment file currently exists and to construct a local path that can later be served by the web application or handed to the separate local-evidence subsystem.

The Zotero metadata channel must never require a PDF parser.

---

## 2. Local PDF evidence is separate from Zotero ingestion

Paperazzi **may parse a locally available PDF**, but only through the independent `local_evidence` subsystem.

The distinction is:

```text
zotero_sqlite
    -> authoritative projection of what Zotero stores

local_evidence/pdf
    -> optional evidence extracted from a local document
```

PDF-derived information may include:

- displayed author/header information;
- affiliation/address blocks;
- e-mail/corresponding-author evidence;
- PDF embedded metadata;
- reference/bibliography sections;
- reference DOI/year identifiers;
- other document-local evidence useful for identity/graph analysis.

PDF-derived evidence must **not silently overwrite Zotero fields**. Provenance must remain distinguishable, for example:

```text
SOURCE_ZOTERO_SQLITE
SOURCE_LOCAL_PDF_NATIVE_TEXT
SOURCE_ZOTERO_FULLTEXT_CACHE
SOURCE_LOCAL_PDF_OCR       future
SOURCE_ONLINE
SOURCE_MANUAL
```

---

## 3. What remains explicitly out of scope for Zotero ingestion

The Zotero ingestion layer itself does **not**:

- parse PDF content;
- OCR PDFs;
- infer missing authors from filenames;
- repair Zotero metadata;
- fetch missing PDFs;
- treat missing DOI/creator/title-adjacent fields as fatal;
- treat a missing local attachment file as an error;
- require Zotero's attachment storage to be complete.

The project as a whole may parse PDFs via `local_evidence`, but failure in that subsystem must never make the Zotero scan fail.

A schema incompatibility or SQL/data-shape inconsistency that prevents safe database extraction is still an ingestion error. Missing scholarly metadata is not.

---

## 4. Authorship semantics

### 4.1 First author

When Zotero contains creators of type `author`, Paperazzi derives the Zotero-based first author from creator order (`orderIndex`).

If no suitable author creator exists, the Zotero-derived first author remains unknown.

A later local-PDF or online enrichment process may discover additional author information, but it remains separately sourced.

### 4.2 Corresponding author

Zotero SQLite metadata is not assumed to contain corresponding-author information.

Corresponding-author status may come from:

1. explicit Paperazzi manual assertion;
2. local PDF evidence such as correspondence lines/e-mail markers;
3. structured/public online metadata;
4. online AI research with evidence/provenance.

A PDF parser should first emit **correspondence evidence spans**, not directly declare a final corresponding author unless a later resolver can map that evidence to a Paperazzi author with sufficient confidence.

Until a claim is resolved:

```text
corresponding_author_status = UNKNOWN
```

This is normal.

---

## 5. Attachment and PDF availability semantics

Attachments have separate concepts.

### 5.1 Zotero attachment metadata exists

Derived exclusively from `zotero.sqlite`.

### 5.2 Local file is currently available

For file-capable attachments, Paperazzi may resolve the stored path and perform a filesystem existence check.

Operational states may include:

```text
NO_ATTACHMENT
ATTACHMENT_NO_LOCAL_FILE
LOCAL_FILE_AVAILABLE
UNRESOLVED_PATH
```

No attempt is required to determine why a local file is missing.

For the web UI:

```text
PDF: Available | Not local | None
```

When `LOCAL_FILE_AVAILABLE`, the backend can serve/open the PDF in the browser regardless of whether evidence extraction succeeded.

### 5.3 Evidence extraction state is independent

A local PDF may additionally have:

```text
AVAILABLE_NOT_EXTRACTED
EXTRACTED_NATIVE
EXTRACTED_PARTIAL
NO_TEXT_LAYER
PASSWORD_REQUIRED
OPEN_OR_PARSE_ERROR
OCR_PENDING / OCR_EXTRACTED       future
```

These states concern knowledge extraction only. They do not change PDF availability.

---

## 6. Reference/citation information

Reference lists are not expected from structured Zotero metadata and are therefore a major use case for local PDF evidence.

The project must distinguish:

```text
raw reference entry from a PDF
        !=
matched Paperazzi paper
```

The raw entry is preserved first. A separate matching layer may resolve it using DOI, normalized title, bibliographic fields, or AI-assisted disambiguation.

Only an accepted match creates a graph edge:

```text
Paper A --CITES--> Paper B
```

A missing PDF or an unparseable reference section simply means fewer citation edges; it never blocks the paper or author record.

---

## 7. Validation philosophy

Tests should validate **extractor correctness**, not Zotero completeness.

### Zotero metadata reader — must pass

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

### Local PDF evidence — must behave safely

- PDF files are opened read-only;
- a missing/unreadable/scan-only PDF is represented as a non-fatal evidence state;
- deterministic extraction preserves page/location provenance where available;
- reference segmentation is conservative and does not fabricate entries;
- raw reference evidence is retained when structured parsing is uncertain;
- PDF-derived evidence cannot silently become a Zotero field.

### Informational coverage metrics

- number of items without creators;
- DOI coverage;
- number of local PDFs missing;
- native-text PDF coverage;
- affiliation/correspondence candidate coverage;
- reference-section detection coverage;
- reference segmentation/DOI coverage;
- metadata quality differences between libraries.

These metrics guide feature improvement but are not ingestion acceptance gates.

---

## 8. Canonical model implication

`CanonicalZoteroItem` remains a faithful normalized projection of Zotero, not a cleaned bibliographic record.

It should preserve absence explicitly:

```text
fields may be missing
creators may be empty
collections may be empty
tags may be empty
attachments may be empty
```

PDF evidence must be stored outside this canonical Zotero projection and linked back to the paper/document through explicit provenance.

---

## 9. Consequence for project phases

### Phase 2

Phase 2 is successful once the Zotero reader safely and correctly maps the real library. Metadata incompleteness and missing local files are not blockers.

### Phase 2.5 — Local PDF Evidence validation

Before freezing the Phase 3 persistence schema, validate the new PDF evidence layer against a representative real-library sample:

- native text extraction;
- front-matter evidence;
- correspondence/e-mail evidence;
- reference-section discovery;
- conservative reference segmentation;
- DOI extraction from references;
- graceful handling of old scans and failures.

The validation results determine which evidence tables/fields must be included in Phase 3.

### Phase 3

Proceed to:

- `paperazzi.sqlite3` persistence;
- scan manifests;
- canonical semantic hashes;
- `NEW / MODIFIED / UNCHANGED / REMOVED / RESTORED` diff;
- attachment availability state;
- local document extraction state;
- first-class PDF evidence/reference tables;
- later reference-to-paper matching and citation graph generation.

### Online enrichment

External/online enrichment remains another evidence domain. It can add/corroborate:

- author identity;
- corresponding-author status;
- affiliations;
- education/history;
- ORCID/OpenAlex/Semantic Scholar identifiers;
- author news and new publications.

Those facts must remain distinguishable from both Zotero metadata and local PDF evidence.
