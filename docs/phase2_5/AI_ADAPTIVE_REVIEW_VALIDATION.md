# Phase 2.5b — Validate AI-supervised adaptive PDF extraction

## Objective

Validate the hybrid workflow defined by:

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

This phase does **not** ask whether PyMuPDF can open PDFs; Phase 2.5 already established that.

The questions are now:

1. Can the local AI reliably detect bad or incomplete Attempt-1 output?
2. Can it recover useful evidence with a targeted Attempt 2?
3. Is Attempt 3 actually rare?
4. Does AI review reduce false positives without discarding valid partial evidence?
5. Can references without an exact heading be recovered safely?
6. Can the process stop after at most three attempts for every document?

---

# 1. Prerequisites

Pull the latest repository first.

Run all unit tests:

```bash
python -m unittest discover -s tests -v
```

The tests must include the regression that publication years such as `1943/1962/1954` are not accepted as reference ordinals.

If unit tests fail, report the failure before running the adaptive review batch.

---

# 2. Local-AI operating specification

The local AI must read and follow:

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

Structured final review output should follow:

```text
schemas/pdf_evidence_review.schema.json
```

Architecture rationale:

```text
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
```

No internet access is required or desired for this validation.

Zotero DB and PDFs are read-only.

---

# 3. Validation corpus

Use the already tested 200-document Phase 2.5 sample as the source pool:

```text
docs/phase2_5/runs/20260817-005040-pdf-evidence-v1/pdf_evidence_report.json
```

Select approximately **40 documents** with deliberate coverage, not simply the first 40.

Target groups:

```text
A. 10 apparently good deterministic results
   - includes HIGH segmented references when possible
   - purpose: verify AI can PASS good output and detect hidden false positives

B. 10 NATIVE_TEXT_GOOD documents with references=null
   - include known examples such as QuTiP-BoFiN / APS-style papers when available
   - purpose: test no-heading/tail-reference recovery

C. 10 MEDIUM/LOW or raw-unsegmented reference results
   - especially author-year/historical layouts
   - purpose: test conservative alternative segmentation

D. 10 front-matter/noise or historical-layout cases
   - candidate affiliations/correspondence with obvious possible publisher/body noise
   - purpose: test AI semantic review of front matter
```

If one document belongs to more than one group, replace it so the final set remains diverse.

Keep broad year coverage, including pre-1980 material.

---

# 4. Per-document procedure

For every selected document:

## Attempt 1

Run the committed deterministic extractor.

Then the local AI must review the result using the prompt.

Record:

```text
PASS
ACCEPT_PARTIAL
RETRY
UNRESOLVED
NEEDS_OCR
```

If `RETRY`, state the concrete problem code/hypothesis before attempting another extraction.

## Attempt 2

Use one bounded strategy from the prompt, such as:

```text
TAIL_REFERENCE_RECOVERY
BLOCK_COLUMN_RECONSTRUCTION
ALTERNATIVE_REFERENCE_SEGMENTATION
FRONT_MATTER_RECOVERY
ZOTERO_FT_CACHE_FALLBACK
OCR_IF_CONFIGURED
```

Review the new result.

## Attempt 3

Use only if Attempt 2 remains concretely recoverable with a materially different strategy.

Never exceed Attempt 3.

Temporary document-specific Python is allowed under a runtime/temp directory. Do not edit committed parser source during the batch.

---

# 5. Required checks

For each final result, the local AI should explicitly check:

## Reference correctness

- reference section is genuinely bibliography/citations;
- reference entries are not body text;
- ordinals are not publication years;
- numbering is structurally plausible when numbering exists;
- author-year layouts are not force-split without adequate evidence;
- raw bibliography is preserved when structured segmentation remains uncertain.

## Front-matter correctness

- affiliation candidates are institutional/address evidence, not body prose;
- publisher/download banners are rejected;
- `Articles you may be interested in` is rejected;
- generic prose using words such as `center` is not treated as affiliation;
- corresponding-author evidence is near the author/front-matter context or otherwise clearly attributable.

## Provenance

Every accepted result identifies:

```text
attempt number
strategy
page(s)
raw evidence text
text source
quality/final status
```

---

# 6. Required aggregate report

Create a report containing at least:

```text
selected_documents
attempt1_PASS
attempt1_ACCEPT_PARTIAL
attempt1_RETRY
attempt1_UNRESOLVED
attempt1_NEEDS_OCR

attempt2_executed
attempt2_resolved
attempt3_executed
attempt3_resolved
final_UNRESOLVED
final_NEEDS_OCR

reference_sections_before_ai_review
reference_sections_after_ai_review
segmented_reference_documents_before
segmented_reference_documents_after
reference_entries_before
reference_entries_after

AI_rejected_false_positive_reference_outputs
AI_rejected_false_positive_affiliation_candidates
AI_rejected_false_positive_correspondence_candidates
```

Also summarize retry strategies used:

```text
strategy -> count -> success count
```

---

# 7. Manual anchor checks

At minimum inspect these known cases if they are available in the local library:

### Rota / historical bibliography case

Confirm that publication years are not reference ordinals after the deterministic fix and AI review.

### QuTiP-BoFiN

The earlier reconnaissance indicated a substantial reference list while the first fixed-heading parser returned `references=null`. Test whether the local AI can recover the bibliography using tail/layout inspection.

### Soriano & Palacios 2014

Likewise test reference recovery plus front-matter e-mail/affiliation evidence.

### Publisher-noise case

Inspect at least one PDF containing download/subscriber/article-recommendation boilerplate and verify it is not accepted as author affiliation/correspondence evidence.

---

# 8. Output and commit policy

Do not commit PDFs, Zotero DBs, snapshots, complete extracted article text, or large raw bibliographies.

Commit only compact diagnostic artifacts, for example:

```text
docs/phase2_5/runs/<timestamp>-ai-adaptive-review/
├── AI_REVIEW_REPORT.md
└── ai_review_report.json
```

The JSON may contain short evidence snippets and attempt metadata, but not entire PDF text.

---

# 9. Acceptance interpretation

This is not a pass/fail completeness test.

A good outcome is one where:

- the AI catches known false-positive patterns;
- most straightforward documents stop after Attempt 1;
- Attempt 2 materially recovers a useful portion of missed reference sections;
- Attempt 3 is uncommon;
- unresolved documents terminate cleanly;
- no document exceeds three attempts;
- provenance is preserved;
- no false citation edge is created merely to increase coverage.

After this run, Phase 3 can freeze the persistence model for extraction attempts and accepted PDF evidence.