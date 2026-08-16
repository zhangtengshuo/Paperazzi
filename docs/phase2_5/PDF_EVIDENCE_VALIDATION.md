# Phase 2.5 — Local PDF Evidence validation

## Objective

Validate the first deterministic local-PDF evidence layer against the real Zotero library before Phase 3 freezes the persistence schema.

The architecture under test is:

```text
CanonicalZoteroItem
        │
        ├── no local PDF ────────────────> continue normally
        │
        └── local PDF available
                │ READ ONLY
                ▼
             PyMuPDF
                │
                ├── PDF metadata
                ├── native page text
                ├── text blocks + bbox
                ├── front-matter evidence
                ├── affiliation candidates
                ├── correspondence/e-mail candidates
                └── reference section / entries / DOI
```

Nothing in this phase writes to Zotero or modifies PDFs. A missing, scanned, encrypted, or malformed PDF is a valid non-fatal evidence state.

See [`docs/architecture/LOCAL_PDF_EVIDENCE.md`](../architecture/LOCAL_PDF_EVIDENCE.md) for the design.

---

## Why this validation happens before Phase 3

Phase 3 will create the first persistent `paperazzi.sqlite3` schema. PDF reconnaissance has shown that references and front-matter evidence are valuable enough to deserve first-class tables rather than opaque JSON blobs.

This validation determines the real-world shapes that those tables need to preserve.

---

# Procedure for the local AI

Run from the Paperazzi repository root.

## Step 1 — run all unit tests

```bash
python -m unittest discover -s tests -v
```

The PDF-specific tests include:

- DOI extraction/normalization;
- numbered bibliography segmentation;
- late exact `References`/`Bibliography` heading selection;
- preservation of author-year bibliographies without unsafe forced splitting;
- missing PDF as a non-fatal state;
- an end-to-end synthetic native-text PDF generated with PyMuPDF, including affiliation, correspondence/e-mail, metadata, and references.

If a PDF test fails, preserve the complete terminal output. Do not weaken the parser merely to make a test pass.

## Step 2 — real-library stratified validation

Use the real library already tested in Phases 1–2:

```bash
python scripts/validate_pdf_evidence.py \
  --db /mnt/d/zotero/zotero.sqlite \
  --data-dir /mnt/d/zotero \
  --limit 200 \
  --label pdf-evidence-v1
```

The validator:

1. creates a Paperazzi-owned consistent SQLite snapshot;
2. obtains active papers and their locally available PDF attachments through `ZoteroSQLiteReader`;
3. includes known layout anchors from the reconnaissance report when present;
4. fills the remaining sample deterministically across publication-era buckets;
5. opens each selected PDF read-only with PyMuPDF;
6. records extraction coverage and short evidence samples.

The selection is deterministic for a fixed library state. This makes parser changes comparable across repeated runs.

Output:

```text
pdf-evidence-output/<timestamp>-pdf-evidence-v1/
├── PDF_EVIDENCE_REPORT.md
├── pdf_evidence_report.json
└── zotero_snapshot.sqlite
```

The snapshot remains local and must not be committed.

---

# What to inspect

## A. Text extraction

Inspect the `text_status` distribution:

```text
NATIVE_TEXT_GOOD
NATIVE_TEXT_PARTIAL
NATIVE_TEXT_SPARSE
THIN_TEXT_LAYER
NO_TEXT_LAYER
PASSWORD_REQUIRED
OPEN_OR_PARSE_ERROR
```

No coverage percentage is a pass/fail gate. The purpose is to learn what fallback paths are worth implementing.

For `OPEN_OR_PARSE_ERROR`, inspect representative files to determine whether the failure is PyMuPDF-specific or the PDF itself is malformed/encrypted.

## B. Front matter

For at least ten papers with affiliation candidates, compare the short report samples with the PDF first page.

Check whether candidates usually contain actual affiliations rather than publisher banners or ordinary body text.

For at least five papers with correspondence candidates, verify whether the evidence contains a real e-mail/correspondence marker.

Do **not** attempt to solve author-to-affiliation mapping in this phase. We are validating evidence capture, not semantic resolution.

## C. References

Inspect three separate levels:

### 1. Heading detection

Does the reported heading actually start the bibliography?

Pay attention to false positives caused by:

- table of contents;
- sentences such as "see References";
- section headers in supplementary material;
- repeated page headers.

The v1 parser deliberately accepts only exact heading lines in the latter 70% of the document.

### 2. Numbered segmentation

For `confidence=HIGH`, manually inspect at least ten papers and verify that:

- entries start at actual bibliography entry boundaries;
- ordinals are plausible/increasing;
- one bibliography entry is not accidentally split into several entries;
- multiple entries are not collapsed into one because of line wrapping.

### 3. Unsegmented references

`raw-author-year-or-unsegmented` and `raw-unsegmented` are valid outcomes.

Do not force them into structured entries merely to increase the entry-count metric. The raw reference section is the fallback evidence and can later be interpreted by a local AI or a better citation parser.

## D. DOI extraction inside references

Spot-check DOI-bearing entries. Exact DOI extraction is strategically important because it will become the highest-confidence automatic route for building in-library citation edges.

---

# Important expected limitations of v1

The current parser intentionally does not yet:

- infer a complete PDF author list;
- map author superscripts to affiliations;
- declare the final corresponding author;
- OCR old scans;
- force-split arbitrary author-year bibliography layouts;
- parse every reference into title/journal/volume/page;
- match references to Paperazzi papers.

Those are next-layer tasks. First determine how good the underlying local evidence is.

---

# Result package

Copy only:

```text
PDF_EVIDENCE_REPORT.md
pdf_evidence_report.json
```

into:

```text
docs/phase2_5/runs/<timestamp>-pdf-evidence-v1/
```

and commit them.

Do not commit:

```text
zotero.sqlite
zotero_snapshot.sqlite
PDF files
.zotero-ft-cache contents
full extracted PDF text
```

The JSON report intentionally contains only short evidence snippets, not the complete PDF text or complete raw bibliography.

---

# Acceptance decision

Phase 2.5 is not judged by a target percentage such as "90% of references must parse".

The layer is accepted when:

- unit tests pass;
- local PDFs are read without mutation;
- failures are isolated per document and non-fatal;
- front-matter candidate extraction is useful enough to feed a semantic resolver;
- exact reference headings have acceptably low false-positive behavior;
- `HIGH` numbered segmentation is trustworthy on manual spot checks;
- uncertain bibliographies are preserved rather than fabricated;
- extracted DOI values are reliable on spot checks;
- the report reveals enough real layouts to finalize Phase 3 evidence/reference tables.

After reviewing this report, the next implementation should be chosen from the evidence rather than assumed in advance. Likely candidates are:

1. reference-to-Paperazzi matching, starting with DOI exact matches;
2. author/affiliation/correspondence semantic resolution using local AI;
3. Zotero full-text cache fallback;
4. OCR/MinerU fallback for old scans;
5. persistence schema for document evidence and references.
