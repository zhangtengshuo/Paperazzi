# Phase 2.5c — Deterministic PDF v3 validation

## Objective

This is the final validation before freezing the deterministic PDF baseline and moving to Phase 3.

Phase 2.5b already validated the architecture:

```text
deterministic Attempt 1
        ↓
mandatory local-AI review
        ↓
targeted Attempt 2
        ↓
optional Attempt 3
```

Phase 2.5c has a narrower purpose. Three generalizable patterns discovered by the local AI have now been promoted into committed deterministic code:

1. strict ordinal-chain filtering for noisy numbered bibliographies;
2. implicit late-document numbered-reference recovery when no literal `References` heading is extracted, including multi-line entries;
3. parenthesized main-reference syntax such as `(8) (a) ... (b) ...`.

The goal is to confirm that these changes reduce avoidable AI retries **without introducing false citation sections or false reference boundaries**.

---

## 1. Read before running

The local AI must read:

```text
DESIGN.md
prompts/local_ai/PDF_EVIDENCE_AGENT.md
docs/phase2_5/runs/20260817-013714-ai-adaptive-review/AI_REVIEW_REPORT.md
```

The previous Phase 2.5 baseline for comparison is:

```text
docs/phase2_5/runs/20260817-005040-pdf-evidence-v1/pdf_evidence_report.json
```

Do not modify Zotero, any PDF, or production parser source during this validation.

---

## 2. First gate — unit tests

Run:

```bash
python -m unittest discover -s tests -v
```

The PDF tests must include and pass regressions for:

```text
publication years are not ordinals
noisy marker streams select a strict plausible ordinal chain
(n) main references are supported
(n)(a)/(b) subreferences remain within the same main reference
multi-line [n] reference starts can recover a late bibliography without a heading
short ordinary numbered lists are not automatically treated as References
publisher/front-matter noise remains rejected
```

If any test fails, stop the real-library run, diagnose it, and commit the code/test fix before continuing.

---

## 3. Real-library deterministic run

Use the same deterministic 200-document stratified sample size as Phase 2.5:

```bash
python scripts/validate_pdf_evidence.py --db /mnt/d/zotero/zotero.sqlite --data-dir /mnt/d/zotero --limit 200 --label pdf-evidence-v3
```

The validator now distinguishes:

```text
with_reference_section
with_explicit_reference_heading
with_implicit_reference_section
with_segmented_references
```

Do not interpret an implicit recovered section as if a literal `References` heading existed.

---

## 4. Mandatory local-AI review

After the deterministic run, the local AI must inspect the generated JSON, not only the aggregate Markdown.

### 4.1 Review every newly implicit section

For every document where:

```text
references.heading == ""
references.method starts with "implicit-"
```

check that:

- the section is genuinely a bibliography/reference list;
- it occurs in the latter part of the paper;
- the ordinal chain is plausible;
- entry boundaries are not body equations, conclusions, steps, figure numbers, or other numbered prose;
- multi-line entries remain grouped correctly;
- the first/last several entries are citation-like.

Record any false positive explicitly.

### 4.2 Review all parenthesized-reference cases

For every method:

```text
numbered-parenthesized
implicit-numbered-parenthesized
```

verify that `(a)/(b)/(c)` subreferences are not split into separate main `paper_reference` records.

### 4.3 Review suspicious ordinal chains

Inspect any segmented output whose ordinals:

- do not begin near the expected local sequence;
- contain gaps > 10;
- are not predominantly consecutive;
- contain values that look like years/page numbers;
- produce an implausibly short/long reference entry.

A deterministic `HIGH` remains a candidate for AI review, not an unquestionable fact.

---

## 5. Required anchor checks

If present in the selected sample, explicitly report:

### QuTiP-BoFiN

Expected direction after v3:

```text
Attempt-1 deterministic parser should ideally recover the no-heading numbered bibliography
without requiring the previous Round-3 block reconstruction.
```

Check approximate 1..78 continuity and inspect first/last entries. Do not require exactly 78 if the actual PDF extraction differs, but explain any difference.

### Rota 1964

Publication years such as `1943/1962/1954` must remain unsegmented author-year evidence, never ordinals.

### Soriano & Palacios 2014

Check whether the bibliography is now recovered deterministically and that genuine front-matter e-mails/affiliations remain intact.

### Previous implausible-HIGH cases

Recheck the Phase 2.5b documents noted as having ordinal streams such as:

```text
[20,2,3,...]
[3,6,1,2,9,3,...]
```

The v3 result must either select a defensible strict chain or fall back to raw/unsegmented evidence. It must not reproduce the old false HIGH segmentation.

---

## 6. Compare against previous results

Produce a compact comparison with at least:

```text
unit_tests_passed
selected_documents
parse_errors

v1_reference_sections
v3_reference_sections
v3_explicit_reference_headings
v3_implicit_reference_sections

v1_segmented_reference_documents
v3_segmented_reference_documents
v1_segmented_reference_entries
v3_segmented_reference_entries

new_implicit_sections_reviewed
new_implicit_false_positives
parenthesized_cases_reviewed
parenthesized_false_splits
ordinal_chain_false_positives
```

Also estimate, using the Phase 2.5b 40-document set where possible:

```text
how many previous Round-2/3 retries would now be unnecessary under deterministic v3
```

This is an estimate for architecture tuning, not a hard acceptance metric.

---

## 7. Acceptance rule

Phase 2.5c passes if:

- all unit tests pass;
- no known year-as-ordinal regression returns;
- no known implausible-HIGH ordinal case returns;
- implicit no-heading recovery produces no material false-positive pattern in the reviewed 200-doc sample;
- `(n)/(n)(a)` handling does not create false subreference splits;
- parser failures remain non-fatal;
- local AI confirms the new deterministic rules reduce repeated mechanical retry work.

Coverage does **not** need to be perfect. Nature-style separated numbering, complex author-year bibliographies, OCR-only scans, and unusual column layouts may remain AI-supervised long-tail cases.

If these conditions hold, mark:

```text
PHASE_2_5_STATUS = PASS
DETERMINISTIC_PDF_BASELINE = FROZEN_V3
NEXT_PHASE = PHASE_3_PERSISTENCE
```

---

## 8. Output / commit policy

Commit only compact diagnostics:

```text
docs/phase2_5/runs/<timestamp>-pdf-evidence-v3/
├── PDF_EVIDENCE_REPORT.md
├── pdf_evidence_report.json
└── V3_REVIEW.md
```

`V3_REVIEW.md` should contain the comparison, anchor checks, newly implicit-section review, false-positive assessment, and final PASS/FAIL recommendation.

Do not commit:

```text
PDF files
zotero.sqlite
snapshot sqlite files
full extracted article text
full raw bibliographies
runtime/temp scripts
```

If fixes are required during the test, commit code/test fixes separately from the final result report so the history remains auditable.
