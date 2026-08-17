# Paperazzi Full-Library Correspondence Forensic Review Agent

## THIS IS A FORENSIC GROUND-TRUTH TASK, NOT A PARSER TEST

Your job is to independently determine the corresponding-author truth of **every reviewable primary article PDF in the local Paperazzi library** and to preserve direct evidence for every judgment.

The production parser is the system under test. Its answer is **not evidence**. Agreement with the parser is not a review.

This protocol is fail-closed: if you cannot demonstrate that you inspected a particular PDF, that paper is **UNRESOLVED**, never implicitly correct and never `NONE_EXPLICIT`.

---

# 0. ABSOLUTE PROHIBITIONS

You MUST NOT:

1. create a Git branch;
2. create any pull request;
3. modify Zotero, source PDFs, or semantic truth in the live Paperazzi DB;
4. use `machine_predicted_corresponding_authors` as ground truth;
5. use `role_candidates`, `contact_candidates`, `author_marker_candidates`, parser risk flags, or parser classifications to decide ground truth;
6. read the diagnostic parser-output queue before the blind review is frozen;
7. infer a corresponding author from author order, last-author status, first-author status, e-mail existence, e-mail local-part similarity, affiliation, filename, DOI metadata, or common academic convention alone;
8. generate review decisions with a loop, regex, heuristic script, template fill, bulk LLM call, or another model;
9. review a sample and extrapolate to the remaining papers;
10. generate several review rows first and inspect PDFs afterward;
11. silently skip a difficult PDF;
12. mark a difficult/unreadable PDF `NONE_EXPLICIT`;
13. stop after finding the first corresponding author when the paper may name several;
14. weaken any validation rule to make your output pass;
15. change production correspondence code while creating ground truth.

Violation of any item above invalidates the audit.

---

# 1. REQUIRED EXECUTION ENVIRONMENT

Work on current `main`. Do not create another branch.

Use only the dedicated environment:

```bash
micromamba run -n Paperazzi python --version
micromamba run -n Paperazzi python scripts/check_paperazzi_environment.py
```

Python must be 3.13 and the environment checker must pass before authoritative work.

Read before execution:

```text
AGENTS.md
docs/LOCAL_AI_FULL_LIBRARY_AUDIT.md
scripts/audit_full_library_local_ai.py
scripts/build_blind_correspondence_review_queue.py
scripts/validate_forensic_correspondence_reviews.py
scripts/score_full_library_ai_review.py
```

---

# 2. PREPARE THE FULL LIBRARY, THEN BLIND YOURSELF

Run the deterministic audit against the actual existing Paperazzi DB, never a newly created empty DB:

```bash
micromamba run -n Paperazzi python scripts/audit_full_library_local_ai.py \
  --db-path <REAL_PAPERAZZI_DB> \
  --output-dir data/phase5-validation/full-library-local-ai-audit
```

Then immediately produce the blind queue:

```bash
micromamba run -n Paperazzi python scripts/build_blind_correspondence_review_queue.py \
  --audit-jsonl data/phase5-validation/full-library-local-ai-audit/all_papers.jsonl \
  --output data/phase5-validation/full-library-local-ai-audit/ai_blind_review_queue.jsonl
```

From this point until all ground-truth rows are frozen:

**YOU MAY READ `ai_blind_review_queue.jsonl`. YOU MAY NOT READ `all_papers.jsonl`, `ai_review_queue.jsonl`, `score.json`, or any file exposing the parser's corresponding-author prediction for the current paper.**

The blind queue intentionally contains no parser answer.

---

# 3. THE ONLY VALID UNIT OF WORK IS ONE PAPER

Process the blind queue in its exact order. Do not reorder by convenience.

For each queue item, perform ALL steps A through H before touching the next queue item.

## A. Identify exactly one paper

Record:

```text
review_sequence
paper_id
title
selected_pdf_path
selected_pdf_sha256
source_authors
page_count
```

Do not inspect another paper until this one has a completed review row.

## B. Open/read the actual PDF

You must access `selected_pdf_path` itself.

Inspect page 1 directly. You are looking for the **visible article front matter**, not merely database metadata.

Confirm that the file is the article described by the queue row. If it is SI, a different article, corrupted, inaccessible, or otherwise wrong, record the problem and use `UNRESOLVED` where correspondence truth cannot be established.

## C. Inspect the complete author header

On page 1, identify:

- all visible author names;
- superscripts and affiliation markers;
- `*`, `†`, `‡`, `§`, `#`, envelope/mail symbols, letters, numbers, and other role markers adjacent to names;
- whether multiple authors carry the same or different markers;
- equal-contribution and present-address markers so they are not confused with correspondence markers.

Write a concrete `author_header_observation`. Generic text such as `looks normal`, `authors checked`, `OK`, or `no issue` is invalid.

## D. Inspect correspondence/contact/footnote evidence

Still on this same paper, inspect every visible author-information/contact area relevant to correspondence. This may be:

- footnotes at the bottom of page 1;
- a `Corresponding author` / `Correspondence` block;
- an `Author to whom correspondence should be addressed` statement;
- a publisher `CONTACT` block;
- e-mail lines linked to author markers;
- author information continuing on page 2 or page 3.

For a **negative** judgment (`NONE_EXPLICIT`), page 1 alone is not enough when the PDF has a page 2. You must inspect pages 1 **and 2**. Continue farther if author information visibly continues.

Write a concrete `contact_footnote_observation` describing what you actually saw.

## E. Decide the ground truth independently

Use exactly one status:

### `EXPLICIT`

Use only when the PDF explicitly establishes a correspondence role by wording or a publisher role convention that can be linked to one or more source authors.

Examples of acceptable evidence:

- `Corresponding author`;
- `Correspondence to:`;
- `Author to whom correspondence should be addressed`;
- a clearly role-bearing publisher `CONTACT` block;
- an envelope/star/other symbol on the author header linked to a contact/correspondence footnote;
- multiple independent markers that explicitly designate multiple corresponding authors.

### `NONE_EXPLICIT`

Use only after you have actively checked all four categories:

```text
CORRESPONDENCE_WORDING
EMAIL_CONTACT
AUTHOR_MARKERS
FOOTNOTE_LINKS
```

Absence of a parser candidate is irrelevant. A bare e-mail is contact information and does not by itself establish the role.

### `UNCERTAIN`

If the PDF is unreadable, image-only without reliable inspection, the role convention cannot be mapped confidently, the PDF/source-author lists conflict materially, or the evidence is genuinely ambiguous, set:

```text
review_status = UNRESOLVED
ground_truth_correspondence_status = UNCERTAIN
```

Uncertainty is preferable to invention.

## F. Prove every positive author

For `EXPLICIT`, create one or more `correspondence_evidence` objects.

Each must contain:

```json
{
  "page": 1,
  "quote": "Exact visible text from this PDF page",
  "evidence_type": "EXPLICIT_WORDING | ROLE_MARKER_LINK | CONTACT_ROLE_BLOCK | OTHER_EXPLICIT",
  "mapped_source_authors": ["Exact spelling copied from source_authors"]
}
```

Every author in `ground_truth_corresponding_authors` must be supported by at least one evidence object.

Do not paraphrase the evidence quote. Copy the smallest exact visible phrase that proves the role. The validator will check the quote against native PDF page text when native text exists.

For marker-based layouts, your `decision_rationale` must state the mapping chain explicitly, for example:

```text
Author header: "Alice Smith*". Page-1 footnote: "* Corresponding author: alice@...". Therefore `*` maps Alice Smith to the correspondence role.
```

## G. Write exactly one review row now

Only after A-F are complete, append one JSON object to:

```text
data/phase5-validation/full-library-local-ai-audit/ai_reviews_forensic.jsonl
```

Required schema for a resolved positive case:

```json
{
  "review_sequence": 1,
  "paper_id": 123,
  "review_status": "REVIEWED",
  "review_mode": "DIRECT_PDF_INSPECTION",
  "reviewed_pdf_sha256": "<exact SHA from blind queue>",
  "pages_inspected": [1, 2],
  "parser_prediction_used_for_decision": false,
  "ground_truth_correspondence_status": "EXPLICIT",
  "ground_truth_corresponding_authors": ["Exact Source Author Name"],
  "author_header_observation": "Concrete description of visible author names and markers.",
  "contact_footnote_observation": "Concrete description of visible correspondence/contact/footnote region.",
  "correspondence_evidence": [
    {
      "page": 1,
      "quote": "Corresponding author: ...",
      "evidence_type": "EXPLICIT_WORDING",
      "mapped_source_authors": ["Exact Source Author Name"]
    }
  ],
  "negative_checks": [],
  "decision_rationale": "Explain exactly why the visible evidence establishes the role and how it maps to the source author.",
  "issues": [],
  "notes": ""
}
```

Required resolved negative case:

```json
{
  "review_sequence": 2,
  "paper_id": 124,
  "review_status": "REVIEWED",
  "review_mode": "DIRECT_PDF_INSPECTION",
  "reviewed_pdf_sha256": "<exact SHA from blind queue>",
  "pages_inspected": [1, 2],
  "parser_prediction_used_for_decision": false,
  "ground_truth_correspondence_status": "NONE_EXPLICIT",
  "ground_truth_corresponding_authors": [],
  "author_header_observation": "Describe the visible author header and every potentially relevant marker.",
  "contact_footnote_observation": "Describe the e-mail/contact/footnote material inspected and why none states a correspondence role.",
  "correspondence_evidence": [],
  "negative_checks": [
    "CORRESPONDENCE_WORDING",
    "EMAIL_CONTACT",
    "AUTHOR_MARKERS",
    "FOOTNOTE_LINKS"
  ],
  "decision_rationale": "State why the inspected pages contain contact information but no explicit correspondence designation, or no relevant contact/role material at all.",
  "issues": [],
  "notes": ""
}
```

For a one-page PDF, `pages_inspected: [1]` is sufficient for a negative case. Otherwise a negative case must include page 2.

## H. Validate this work before proceeding

After every small checkpoint batch, run the forensic validator. Do not wait until the end to discover that evidence is invalid.

```bash
micromamba run -n Paperazzi python scripts/validate_forensic_correspondence_reviews.py \
  --blind-queue data/phase5-validation/full-library-local-ai-audit/ai_blind_review_queue.jsonl \
  --reviews-jsonl data/phase5-validation/full-library-local-ai-audit/ai_reviews_forensic.jsonl \
  --output data/phase5-validation/full-library-local-ai-audit/forensic_validation.json
```

During an incomplete run, missing future paper IDs are expected because `--require-all` is not supplied. **Evidence-contract errors for already reviewed papers are not acceptable. Fix the evidence record before moving on.**

Only after this paper has a valid evidence-bearing row may you advance to the next queue item.

---

# 4. ANTI-SHORTCUT SELF-CHECK BEFORE EVERY ROW

Before appending each row, answer internally YES to all applicable statements:

```text
I accessed this paper's selected_pdf_path itself.
I inspected page 1 of this exact PDF.
I inspected the visible author header, not just extracted metadata.
I checked marker-to-author relationships.
I checked the contact/correspondence/footnote area.
If I claim NONE_EXPLICIT and page 2 exists, I inspected page 2.
If I claim EXPLICIT, I recorded exact visible evidence and mapped every claimed author.
I did not look at the parser's predicted corresponding author for this decision.
I did not infer the answer from e-mail presence or author order.
I am writing this row before opening the next paper.
```

If any answer is NO, **do not append a resolved judgment**.

---

# 5. COMPLETION IS MECHANICALLY DEFINED

After the final queue row, run:

```bash
micromamba run -n Paperazzi python scripts/validate_forensic_correspondence_reviews.py \
  --blind-queue data/phase5-validation/full-library-local-ai-audit/ai_blind_review_queue.jsonl \
  --reviews-jsonl data/phase5-validation/full-library-local-ai-audit/ai_reviews_forensic.jsonl \
  --output data/phase5-validation/full-library-local-ai-audit/forensic_validation.json \
  --require-all
```

The audit is **not complete** unless:

```text
pass = true
missing_review_ids = []
unexpected_review_ids = []
evidence_contract_errors = []
```

Only now may you reveal/use the production parser output and compare it with the frozen ground truth.

Convert/copy the frozen ground-truth fields into the metric scorer input if needed, then calculate TP/FP/FN. Do not edit a ground-truth judgment merely because it disagrees with the parser.

---

# 6. REQUIRED FAILURE ANALYSIS AFTER UNBLINDING

Once forensic ground truth is frozen, compare it against production output and group every error by root cause.

For each false positive and false negative, record:

```text
paper_id
publisher / venue
PDF layout convention
ground-truth corresponding author set
parser predicted set
exact ground-truth evidence
which extraction/classification/mapping stage failed
whether the failure is recurring
representative paper IDs with the same pattern
```

Distinguish at least:

```text
ROLE_TEXT_NOT_EXTRACTED
ROLE_TEXT_MISCLASSIFIED
MARKER_NOT_EXTRACTED
MARKER_TO_AUTHOR_MAPPING_FAILED
EMAIL_TO_AUTHOR_MAPPING_FAILED
MULTIPLE_CORRESPONDING_AUTHOR_TRUNCATION
CONTACT_FALSE_POSITIVE
PRIMARY_SI_SELECTION_ERROR
PDF_TEXT_EXTRACTION_FAILURE
SOURCE_AUTHOR_MISMATCH
UNKNOWN_PUBLISHER_CONVENTION
```

Do not repair production code during this forensic pass. First produce the full failure inventory.

---

# 7. REQUIRED FINAL ARTIFACTS

Do not return only a prose summary. Preserve:

```text
data/phase5-validation/full-library-local-ai-audit/summary.json
data/phase5-validation/full-library-local-ai-audit/all_papers.jsonl
data/phase5-validation/full-library-local-ai-audit/ai_blind_review_queue.jsonl
data/phase5-validation/full-library-local-ai-audit/ai_reviews_forensic.jsonl
data/phase5-validation/full-library-local-ai-audit/forensic_validation.json
data/phase5-validation/full-library-local-ai-audit/score.json
data/phase5-validation/full-library-local-ai-audit/FULL_LIBRARY_FORENSIC_REPORT.md
```

`FULL_LIBRARY_FORENSIC_REPORT.md` must state the number of queue rows and reviewed rows. If they differ, the report must say **INCOMPLETE**, not PASS.

The final report must explicitly state:

```text
All corresponding-author ground truth was created blind to parser predictions = YES/NO
Every resolved review has direct-PDF evidence = YES/NO
Every required PDF received a review row = YES/NO
Forensic validator pass = YES/NO
```

A truthful NO is acceptable. A fabricated YES invalidates the benchmark.
