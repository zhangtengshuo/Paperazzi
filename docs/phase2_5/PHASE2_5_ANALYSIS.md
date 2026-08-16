# Phase 2.5 analysis — PDF evidence v1

Source run:

```text
docs/phase2_5/runs/20260817-005040-pdf-evidence-v1/
```

## 1. Result summary

The 200-document stratified validation establishes that low-level PDF access is not the main problem:

```text
selected PDFs                    200
NATIVE_TEXT_GOOD                 198
NATIVE_TEXT_SPARSE                 1
NO_PAGES                           1
parse errors                       0
```

Front-matter heuristics found:

```text
affiliation candidates           165
correspondence candidates         81
e-mail candidates                 61
```

Reference extraction was much less complete:

```text
exact reference heading           45
usable deterministic segmentation 30
segmented reference entries      785
DOI identifiers in those entries  10
```

Therefore the dominant problem is **layout/semantic heterogeneity**, not PyMuPDF's ability to open and read files.

---

## 2. Fixed-code issues discovered

### 2.1 Historical years misread as reference ordinals

A historical author-year bibliography produced apparent ordinals such as:

```text
1943
1962
1954
```

while the deterministic parser reported high confidence.

This is a production-parser defect rather than a reason to invoke AI. The baseline parser has therefore been hardened to:

- keep deterministic ordinals within a conservative range;
- reject year-like ordinal values;
- require locally near-sequential numbering;
- add a regression test based on this failure mode.

### 2.2 Front-matter keyword false positives

The first run also showed heuristic candidates triggered by:

- prose containing `center` as a verb;
- publisher/download banners;
- `Articles you may be interested in` material.

Known systematic noise should be removed in fixed code. Remaining ambiguous cases belong to AI quality review.

---

# 3. Why exact-heading reference extraction is insufficient

Only 45/200 PDFs were detected by exact bibliography headings despite 198/200 having good native text.

This means a large fraction of the library uses formats such as:

- references without a literal heading;
- headings merged into another text block;
- multi-column ordering that hides the heading in plain sorted text;
- historical bibliography styles;
- author-year bibliography;
- numbered references using layout/superscripts rather than textual markers.

It is not desirable to encode every possible publisher layout as a growing set of global regex rules.

---

# 4. Adopted architecture: mandatory AI review + bounded retries

For each locally available PDF:

```text
Attempt 1
fixed deterministic parser
        ↓
mandatory local-AI review
        ↓
PASS / ACCEPT_PARTIAL / RETRY
                         ↓
                   Attempt 2
                   targeted strategy
                         ↓
                   AI review
                         ↓
                   optional Attempt 3
                         ↓
                   final status
```

Every Attempt-1 result is reviewed by the local AI, including those labeled `HIGH` by the parser.

The maximum is three attempts total. Most documents should stop after Attempt 1.

Detailed behavior:

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

Architecture and persistence requirements:

```text
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
```

Structured AI review contract:

```text
schemas/pdf_evidence_review.schema.json
```

---

# 5. Reference matching consequence

Only 10 DOI strings were found among 785 deterministically segmented entries (~1.3%).

Even if adaptive extraction substantially improves segmentation, old references frequently lack DOI text.

Therefore Paperazzi citation matching must treat DOI as a very strong but sparse identifier.

Required matching ladder:

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED
AUTHOR_YEAR_JOURNAL
JOURNAL_VOLUME_PAGE_YEAR
BIBLIOGRAPHIC_COMPOSITE
AI_RESOLVED
UNRESOLVED
```

Raw reference text must always survive failed parsing/matching.

---

# 6. Acceptance philosophy

The PDF subsystem is not judged by whether every paper yields authors, affiliations, and a fully segmented bibliography.

Valid final states include:

```text
PASS
ACCEPT_PARTIAL
UNRESOLVED
NEEDS_OCR
```

A difficult PDF never blocks Zotero ingestion or the rest of the PDF batch.

The design target is:

> high aggregate information yield, bounded per-document effort, and auditable provenance.

---

# 7. Next implementation consequence

Phase 3 persistence must include extraction-attempt history rather than only a single final PDF result.

At minimum reserve:

```text
paper_documents
document_extraction_attempts
document_evidence_spans
paper_references
paper_reference_matches
```

Evidence rows should identify their originating `attempt_id` and acceptance status so rejected/superseded extraction attempts remain auditable without entering the citation graph.