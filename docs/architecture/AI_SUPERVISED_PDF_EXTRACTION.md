# AI-supervised adaptive PDF extraction

**Status:** Architecture decision following the first 200-document Phase 2.5 validation.

This document defines how Paperazzi combines deterministic Python extraction with a local AI reviewer for heterogeneous scholarly PDFs.

The governing prompt is:

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

The prompt is part of the operational specification and must be versioned together with parser behavior.

---

## 1. Why this layer exists

The first stratified 200-PDF validation showed a strong asymmetry:

```text
PDF/native-text access              very reliable
semantic/layout interpretation      much less uniform
```

Observed results:

```text
200 selected PDFs
198 NATIVE_TEXT_GOOD
0 parse errors
165 with heuristic affiliation candidates
81 with heuristic correspondence candidates
61 with e-mail candidates
45 with exact reference heading found
30 with usable deterministic reference segmentation
785 segmented reference entries
10 DOI strings inside segmented entries
```

The fixed parser therefore solves the low-level document-access problem, but it cannot safely enumerate every publisher and historical layout.

A purely rule-based strategy would require an ever-growing set of brittle publisher-specific exceptions. A purely AI-based strategy would lose determinism and make provenance difficult to audit.

Paperazzi therefore uses a hybrid design:

```text
fixed parser
    ↓
mandatory local-AI quality review
    ↓
PASS / ACCEPT_PARTIAL / RETRY
                      ↓
              adaptive Attempt 2
                      ↓
              review again
                      ↓
              optional Attempt 3
                      ↓
       final bounded extraction state
```

---

# 2. Responsibilities

## 2.1 Fixed production code

The committed Python extractor owns tasks that should be repeatable and testable:

- opening PDFs read-only;
- PDF metadata;
- native text extraction;
- blocks/coordinates;
- text-layer classification;
- first-pass front-matter candidates;
- first-pass exact reference-heading search;
- conservative numbered-reference segmentation;
- DOI/e-mail/year regex extraction;
- known systematic-noise suppression;
- serialization of evidence and provenance.

Known systematic failures discovered in real data should be fixed here and protected by regression tests.

Example: publication years such as `1943`, `1962`, and `1954` must never be accepted as bare reference ordinals.

## 2.2 Local AI

The local AI owns tasks where document-specific semantic/layout judgment is valuable:

- review every Attempt-1 extraction for plausibility;
- recognize false-positive affiliation/correspondence blocks;
- notice a missing bibliography despite good native text;
- identify references without a literal `References` heading;
- choose a bounded alternative parsing strategy;
- reconstruct two-column or unusual block ordering;
- recognize author-year/hanging-indent/superscript reference formats;
- relate front-matter symbols/e-mails to displayed authors when evidence is adequate;
- decide when partial evidence is safer than another retry.

The local AI must never silently mutate the deterministic result.

## 2.3 Deterministic database writer

Only normal Paperazzi code writes accepted results to `paperazzi.sqlite3`.

The local AI returns structured candidate results and attempt decisions; it does not execute SQL against Paperazzi or Zotero.

---

# 3. Maximum-three-attempt state machine

Each local document has at most three extraction attempts.

## Attempt 1

```text
actor      = DETERMINISTIC
strategy   = production extractor version
reviewer   = LOCAL_AI
```

Every available PDF receives this attempt and every result receives a local-AI review.

The reviewer returns one of:

```text
PASS
ACCEPT_PARTIAL
RETRY
UNRESOLVED
NEEDS_OCR
```

`HIGH` parser confidence does not bypass AI review.

## Attempt 2

Executed only after `RETRY`.

```text
actor = LOCAL_AI_CONTROLLED
```

The AI chooses a specific bounded recovery strategy, for example:

```text
TAIL_REFERENCE_RECOVERY
BLOCK_COLUMN_RECONSTRUCTION
ALTERNATIVE_REFERENCE_SEGMENTATION
FRONT_MATTER_RECOVERY
ZOTERO_FT_CACHE_FALLBACK
OCR_IF_CONFIGURED
```

Attempt 2 must have an explicit failure hypothesis and strategy description.

## Attempt 3

Exceptional final attempt.

It must use a materially different strategy and remain local/read-only. The AI may create a temporary document-specific Python script under Paperazzi runtime/cache directories.

After Attempt 3, no further retries are allowed.

Final state:

```text
PASS
ACCEPT_PARTIAL
UNRESOLVED
NEEDS_OCR
```

No infinite repair loop is permitted.

---

# 4. Important semantic distinction: attempts vs accepted evidence

All attempts are historical facts.

Suppose:

```text
Attempt 1: parser says HIGH, but years are misread as ordinals
Attempt 2: AI reconstructs author-year bibliography correctly
```

Paperazzi should retain both attempt records, while only Attempt 2 contributes accepted reference evidence.

Therefore:

```text
attempt output != accepted evidence
```

and:

```text
accepted evidence must identify accepted_attempt_id
```

This makes the pipeline auditable and allows later parser versions to be compared against historical decisions.

---

# 5. Persistence additions for Phase 3

The existing `paper_documents` concept should gain review/final-selection fields:

```text
paper_documents
- document_id
- paper_id
- zotero_attachment_key
- local_path
- document_change_key
- availability_status
- extraction_status
- accepted_attempt_id           nullable
- attempt_count
- prompt_version
- prompt_hash
- extractor_version
- last_reviewed_at
```

Add a first-class attempt table.

## `document_extraction_attempts`

```text
attempt_id
 document_id
attempt_number                 1..3
actor                          DETERMINISTIC / LOCAL_AI_CONTROLLED / OCR
strategy
strategy_parameters_json       bounded parameters / recovery description
extractor_version
prompt_version
prompt_hash
text_source                    PDF_NATIVE / ZOTERO_FT_CACHE / OCR
started_at
completed_at
decision                       PASS / ACCEPT_PARTIAL / RETRY / UNRESOLVED / NEEDS_OCR
problem_codes_json
quality_notes
output_hash
runtime_artifact_path          nullable, Paperazzi-owned cache only
```

Constraints:

```text
UNIQUE(document_id, attempt_number)
attempt_number BETWEEN 1 AND 3
```

## Evidence provenance

`document_evidence_spans` and `paper_references` should include:

```text
attempt_id
acceptance_status
```

so evidence from a rejected attempt can remain auditable without entering downstream claims/graphs.

Recommended states:

```text
ACCEPTED
SUPERSEDED
REJECTED
CANDIDATE
```

---

# 6. Prompt versioning is part of reproducibility

Adaptive extraction behavior depends on both code and prompt.

Therefore every AI-reviewed extraction stores:

```text
prompt_path
prompt_version or git commit
prompt_hash
```

A changed prompt may justify re-review without re-reading an unchanged PDF from scratch.

This creates two independent version axes:

```text
extractor_version
review_prompt_version
```

Later Paperazzi can selectively rebuild only documents affected by a meaningful parser/prompt upgrade.

---

# 7. Batch execution model

For thousands of PDFs:

```text
for each NEW/changed document:
    deterministic Attempt 1
    build compact review context
    local AI reviews Attempt 1
    if PASS/ACCEPT_PARTIAL:
        finalize
    elif RETRY:
        execute bounded Attempt 2
        local AI reviews
        if still RETRY and recoverable:
            execute Attempt 3
        finalize
    continue to next document regardless of result
```

The AI should not load an entire 100-page PDF into context by default.

The review context should be progressive:

```text
Attempt 1 review:
- Zotero metadata context
- deterministic result
- front-matter evidence snippets
- reference evidence snippets
- compact structural diagnostics

Attempt 2/3 only:
- selected raw pages/blocks/words needed for the identified problem
```

This bounds context and computation while preserving flexibility.

---

# 8. Reference extraction implications from Phase 2.5

The first validation found only 10 DOI strings in 785 segmented references.

Therefore the citation graph must not be designed around DOI availability.

Reference matching should prioritize:

```text
1 DOI exact, when present
2 normalized title, when recoverable
3 author + year + journal/book
4 journal + volume + page/article number + year
5 local-AI bibliographic resolution
6 unresolved raw reference
```

The raw citation text is always retained.

The AI-supervised parser should increasingly extract structured bibliographic components, but failure to structure them must not delete the raw reference.

---

# 9. Acceptance philosophy

The target is not 100% extraction completeness.

The target is:

> maximize reliable information yield across a heterogeneous personal scholarly library while keeping per-document work bounded and provenance auditable.

Accordingly:

- `ACCEPT_PARTIAL` is a normal successful outcome;
- `UNRESOLVED` is acceptable;
- `NEEDS_OCR` is acceptable;
- one bad document never blocks the batch;
- false citation edges are worse than missing citation edges;
- fixed-code systematic errors should be fixed globally;
- long-tail layout variation belongs to the AI-controlled retry layer.

---

# 10. Operational contract

The detailed local-AI behavior is defined in:

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

Production orchestration should present that prompt together with the per-document review context and require structured output conforming to the future `pdf_evidence_review` schema.

Until that schema is implemented, the prompt's required attempt-log structure is normative.