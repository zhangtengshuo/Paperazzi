# Local PDF Evidence architecture

**Status:** Architecture decision. Local PDF parsing is a first-class optional subsystem of Paperazzi.

## 1. Position in the system

Paperazzi has two independent local input channels:

```text
                    ┌─────────────────────────────┐
                    │ Zotero metadata channel     │
                    │ zotero.sqlite READ ONLY     │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                         CanonicalZoteroItem
                                   │
                                   ▼
                         Paperazzi paper layer
                                   ▲
                                   │
                    ┌──────────────┴──────────────┐
                    │ Local PDF evidence channel  │
                    │ storage/.../*.pdf READ ONLY │
                    └─────────────────────────────┘
```

The channels are deliberately separate:

- Zotero metadata ingestion must succeed even when no PDF exists.
- PDF parsing must never modify Zotero metadata or silently replace a Zotero field.
- PDF-derived facts are local evidence with explicit provenance.
- A parse failure, scan-only PDF, missing attachment, or incomplete reference list only reduces evidence coverage; it never blocks Zotero ingestion.

This preserves the tolerant Zotero boundary while making available PDFs scientifically useful.

---

## 2. Why PDF evidence is first-class

Real-library reconnaissance showed that direct PyMuPDF extraction is fast and that most stored PDFs have native text layers. Local PDFs contain information that `zotero.sqlite` normally does not contain in structured form:

- complete displayed author line;
- author affiliation/address blocks;
- author-to-affiliation marker evidence;
- corresponding-author/e-mail evidence;
- PDF embedded metadata;
- reference/bibliography sections;
- identifiers embedded in references, especially DOI;
- other paper-local evidence useful for later identity and graph analysis.

The most important new capability is the **reference graph**. References create paper-to-paper relations, which can later induce author-to-author influence/citation relations and support deeper research-network analysis.

---

## 3. Layered extraction model

PDF processing is intentionally split into deterministic evidence extraction and semantic interpretation.

### Layer A — deterministic document extraction

Primary backend: **PyMuPDF**.

Extract read-only:

```text
PDF path / attachment identity
page count
PDF metadata
native text per page
text blocks + page/bbox
front-matter text (normally first 2 pages)
reference-section heading and raw section
strong identifiers: DOI, e-mail, year patterns
text-layer quality/status
```

No AI is needed here.

### Layer B — deterministic candidate extraction

From Layer A:

```text
affiliation-candidate blocks
correspondence/e-mail candidate blocks
reference entries when segmentation is trustworthy
reference DOI identifiers
```

These are candidates/evidence spans, not authoritative scholarly facts.

### Layer C — semantic resolution

Local AI and/or deterministic resolvers consume the evidence:

```text
PDF author line ↔ Zotero creators
author ↔ affiliation mapping
corresponding-author claim
reference entry ↔ canonical paper matching
```

Every resolved claim keeps a link to its original PDF evidence.

### Layer D — external enrichment

Online sources can corroborate or extend local evidence:

```text
ORCID
Crossref
OpenAlex
Semantic Scholar
publisher pages
institutional profiles
online AI research
```

Local PDF evidence and online evidence remain distinguishable.

---

## 4. Text-source priority and graceful degradation

Recommended source order for a locally available document:

```text
1. direct PDF native text via PyMuPDF
2. Zotero .zotero-ft-cache / .zotero-ft-unprocessed (optional fallback)
3. OCR / MinerU path for scan-only PDFs (later optional stage)
4. no local text evidence
```

Direct PDF parsing is preferred because it is independent of Zotero indexing state and provides layout coordinates and embedded metadata.

OCR is not a prerequisite for v1. Scan-only PDFs should initially be represented as:

```text
text_status = NO_TEXT_LAYER / THIN_TEXT_LAYER
needs_ocr = true
```

and otherwise remain usable as ordinary PDF attachments in the web UI.

---

## 5. Front-matter evidence

The first two pages are the default front-matter evidence window.

Deterministic extraction should preserve blocks containing likely institution or correspondence signals. Examples include:

```text
Department / Institute / University / Laboratory / Center / CNRS / RIKEN / ...
corresponding author / correspondence / electronic address / e-mail / ...
name@example.edu
```

Common publisher noise such as subscriber-access/download banners should be filtered where safely recognizable.

Important rule:

> The deterministic layer should prefer preserving a slightly noisy evidence block over inventing an author-affiliation mapping.

The local AI may later map superscript markers and author names using the Zotero creator list as context.

---

## 6. Reference extraction

### 6.1 Reference-section discovery

The deterministic parser looks for exact late-document headings such as:

```text
References
Reference
Bibliography
Literature Cited
Works Cited
Notes and References
References and Notes
```

A heading found in the latter portion of the paper is preferred over early table-of-contents mentions.

If no trustworthy heading is found, the parser returns no structured reference section rather than guessing that arbitrary trailing text is a bibliography.

### 6.2 Preserve raw reference evidence

Whenever a reference section is detected, preserve the raw section even if entry segmentation is uncertain.

This is essential for author-year bibliographies and unusual historical layouts.

### 6.3 Deterministic entry segmentation

High-confidence v1 segmentation targets numbered styles:

```text
[1] ...
[2] ...
[3] ...

1. ...
2. ...
3. ...
```

Only a plausible mostly increasing sequence is accepted. Otherwise the section remains `raw-unsegmented` or `raw-author-year-or-unsegmented`.

This conservative policy prevents false citation edges.

### 6.4 Reference identifiers

For every segmented entry, extract strong identifiers such as:

```text
DOI
publication year
```

Later resolvers may add title/journal/volume/page fields.

---

## 7. Citation matching and graph semantics

References are not equivalent to matched papers. Store them separately.

```text
citing paper
    │
    ▼
paper_reference (raw evidence)
    │
    ▼
paper_reference_match
    │
    ▼
cited Paperazzi paper
```

Recommended match classes:

```text
DOI_EXACT               auto-accept, very high confidence
TITLE_EXACT_NORMALIZED  high confidence with sanity checks
BIBLIOGRAPHIC_COMPOSITE title + year + journal/volume/page
AI_RESOLVED              candidate/claim with evidence
UNRESOLVED               keep raw reference only
```

A `CITES` graph edge is created only after a reference match is accepted.

The raw reference is never discarded when matching fails.

### In-library citation graph

If both citing and cited papers are in Paperazzi/Zotero:

```text
Paper A --CITES--> Paper B
```

This immediately supports:

- citation paths inside the user's library;
- papers that connect otherwise separate author clusters;
- frequently referenced foundational papers;
- author-to-author citation/influence projections;
- topic lineage and method genealogy;
- later comparison against external citation graphs.

---

## 8. Proposed persistence model

Phase 3 should reserve first-class tables rather than storing everything as opaque JSON.

### `paper_documents`

```text
document_id
paper_id
zotero_attachment_key
local_path
availability_status
content_type
file_size
file_mtime
zotero_storage_hash          nullable
extraction_status
extraction_backend
extraction_backend_version
extracted_at
```

The filesystem path is operational state, not scholarly identity.

### `document_evidence_spans`

```text
evidence_span_id
document_id
kind                         front-matter / affiliation-candidate / correspondence-candidate / ...
page_index
bbox_json                    nullable
raw_text
extractor_version
created_at
```

### `paper_references`

```text
reference_id
citing_paper_id
document_id
ordinal                      nullable
raw_text
parsed_doi                   nullable / separate multi-value table if needed
parsed_year                  nullable
parse_method
parse_confidence
reference_section_start_page
reference_section_end_page
```

### `paper_reference_matches`

```text
reference_match_id
reference_id
cited_paper_id
match_type
match_score
status                       ACCEPTED / CANDIDATE / REJECTED
resolver
created_at
```

### Claims using PDF evidence

Existing/future `claims` should be able to point to `document_evidence_spans` as evidence for:

```text
author affiliation
corresponding-author status
email/public contact evidence
other paper-specific author facts
```

---

## 9. Caching and incremental extraction

PDF extraction should not be repeated unnecessarily.

Recommended document-change key:

```text
preferred: Zotero storageHash when present
fallback:  file size + mtime
```

If the document-change key is unchanged and extractor version is unchanged, reuse prior PDF evidence.

Re-extract when:

```text
attachment becomes locally available
file content/state changes
extractor version changes materially
user explicitly requests rebuild
```

A Zotero bibliographic metadata change alone does not require re-parsing an unchanged PDF.

---

## 10. Failure semantics

All PDF states are valid operational states:

```text
AVAILABLE_NOT_EXTRACTED
EXTRACTED_NATIVE
EXTRACTED_PARTIAL
NO_TEXT_LAYER
PASSWORD_REQUIRED
OPEN_OR_PARSE_ERROR
FILE_UNAVAILABLE
OCR_PENDING / OCR_EXTRACTED       future
```

No state above blocks the Zotero scan or author database update.

The web UI still exposes `Open PDF` whenever the local file itself is available, regardless of extraction status.

---

## 11. Validation strategy

PDF validation is about **extractor behavior and useful coverage**, not completeness of the library.

Unit tests must cover:

- DOI extraction and normalization;
- exact reference-heading detection;
- numbered reference segmentation with monotonicity checks;
- preservation of unsegmented author-year sections;
- first-page affiliation/correspondence candidate extraction;
- publisher-boilerplate suppression;
- missing PDF as non-fatal state;
- synthetic native-text PDF end-to-end extraction.

Real-library validation should use a deterministic stratified sample across publication eras plus known layout anchors, and report:

- text-layer status;
- parse failures;
- affiliation/correspondence/email candidate coverage;
- reference-heading coverage;
- deterministic segmentation coverage;
- extracted DOI coverage inside references;
- representative evidence snippets for manual inspection.

These percentages guide parser improvement but are not Zotero-ingestion gates.

---

## 12. Current implementation boundary

Implemented now:

```text
src/paperazzi/local_evidence/pdf.py
scripts/validate_pdf_evidence.py
tests/test_pdf_evidence.py
```

Current deterministic v1 intentionally does **not** yet:

- resolve author names from the first page;
- assign affiliations to specific authors;
- convert corresponding evidence into final authorship flags;
- force-split arbitrary author-year references;
- OCR scan-only PDFs;
- match extracted references against the Paperazzi corpus.

Those steps should be added only after the real-library validation report shows what layouts actually dominate the user's corpus.
