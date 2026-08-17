# Local AI Full-Library Audit Guide

## Purpose

This run is a **read-only QA audit** of the entire Paperazzi literature library. Its primary goal is to establish whether the production PDF/correspondence pipeline still fails on publisher layouts that are not represented by the tracked 100-PDF regression fixture.

The audit has two layers:

1. deterministic code scans every active Paperazzi paper and every reachable selected primary PDF;
2. a local AI reviewer independently inspects the real PDFs and supplies ground truth, with correspondence-author review performed for **every selected primary PDF**, not only parser-flagged cases.

The AI review must never write assertions back into the live Paperazzi database. Review output is an external JSONL benchmark until a human or a later controlled import step accepts it.

---

## 1. Safety contract

Use the repository's required environment:

```bash
micromamba run -n Paperazzi python --version
```

Expected major/minor: Python 3.13.

During this audit:

- Zotero is read-only.
- The live Paperazzi SQLite database is opened by the audit script with SQLite `mode=ro` and `PRAGMA query_only=ON`.
- Do not run migrations against the live database for the audit.
- Do not call a command that populates `AuthorshipEvidence`, `CreatorMentionRoleEvidence`, references, document roles, or canonical identities in the live database.
- Store all audit output under `data/phase5-validation/full-library-local-ai-audit/` (or another ignored validation directory).
- The AI reviewer may read PDF files directly but must not modify, rename, move, OCR-rewrite, or annotate the source PDFs.

If a command appears to require a write to the live Paperazzi DB, stop that command and record it as a tooling problem.

---

## 2. Baseline regression gates

Before the full-library audit, run the existing deterministic tests on the branch under review:

```bash
micromamba run -n Paperazzi python -m unittest discover -s tests -v
micromamba run -n Paperazzi python scripts/validate_correspondence_pdf_sample.py
```

Both must pass before interpreting full-library failures. The tracked 100-PDF test is a layout regression gate; it is **not** a full person-level ground-truth benchmark.

If the historical reviewed file still exists locally:

```text
data/phase5-validation/phase5_5/correspondence-benchmark-v1.json
```

preserve it. Do not overwrite it. It can later be rescored against the current implementation as an additional historical benchmark.

---

## 3. Deterministic full-library scan

Run:

```bash
micromamba run -n Paperazzi python scripts/audit_full_library_local_ai.py \
  --db-path data/phase4-validation/paperazzi.sqlite3 \
  --output-dir data/phase5-validation/full-library-local-ai-audit
```

Use the actual current Paperazzi DB path if it differs. The database itself remains read-only.

For a smoke test first:

```bash
micromamba run -n Paperazzi python scripts/audit_full_library_local_ai.py \
  --db-path data/phase4-validation/paperazzi.sqlite3 \
  --output-dir data/phase5-validation/full-library-local-ai-audit-smoke \
  --max-papers 25
```

The full run produces:

```text
summary.json
all_papers.jsonl
ai_review_queue.jsonl
```

`all_papers.jsonl` contains every scanned active paper, including papers with no reviewable primary PDF.

`ai_review_queue.jsonl` contains **every paper for which the production selector found a reachable primary PDF**, sorted by risk. This is deliberate: reviewing only flagged papers would make it impossible to discover a new publisher convention that the current parser misses completely.

The deterministic scanner records, among other things:

- primary/SI document selection and multiple-primary ambiguity;
- PDF parse errors and unusable front matter;
- title/front-matter mismatch;
- DOI conflict suggesting the wrong PDF may be attached or selected;
- source-author coverage in the extracted author header;
- correspondence-role candidates;
- contact-only candidates;
- author marker candidates (`*`, `†`, `‡`, `✉`, etc.);
- machine-mapped corresponding authors;
- reference-section presence and confidence.

Risk flags are triage signals, not ground truth.

---

## 4. Local AI review: mandatory correspondence pass over every PDF

### Core rule

The reviewer must independently inspect the actual PDF. **Do not decide ground truth by agreeing with the parser output.** The parser fields in `ai_review_queue.jsonl` are diagnostic hints only.

For every queue row, inspect the selected PDF's front matter. Normally pages 1-2 are sufficient; continue to page 3 or the author-information/footnote area when necessary.

Determine `ground_truth_correspondence_status` using exactly one value:

- `EXPLICIT`: the PDF explicitly identifies one or more corresponding/contact-for-correspondence authors through wording or a publisher role convention.
- `NONE_EXPLICIT`: no explicit corresponding-author designation is present in the inspected article front matter.
- `UNCERTAIN`: the PDF is unreadable or the publisher convention cannot be resolved confidently.

### What counts as explicit role evidence

Examples include:

- `Corresponding author`, `Correspondence`, `Correspondence to`;
- `Author to whom correspondence should be addressed`;
- a publisher's clearly role-bearing `CONTACT` block;
- an envelope marker or star/footnote marker that is clearly linked from the author header to the contact footnote;
- multiple symbol-to-author mappings where more than one author is explicitly designated.

### What does **not** count by itself

Do not infer corresponding-author status from:

- a bare `E-mail:` line;
- a bare `Electronic mail:` line;
- the existence of an email address in an affiliation;
- being the final author;
- being the first author;
- an institutional or publisher customer-service email;
- a plausible-looking author-email local-part match without role evidence.

This distinction is mandatory because the historical false-positive failure was caused by treating ordinary electronic-mail contact information as correspondence-role evidence.

### Multiple corresponding authors

The ground truth is a set of 0/1/N authors. Never stop after finding the first corresponding author. Inspect the entire correspondence block and every linked footnote marker.

### Ground-truth author spelling

When the status is `EXPLICIT`, copy author names **exactly from the queue row's `source_authors` list** into `ground_truth_corresponding_authors`. This ensures the scorer can compare person-level sets without inventing another name-normalization problem.

If the PDF clearly names a corresponding author who cannot be matched to any `source_authors` value, mark the case `UNRESOLVED` and explain the mismatch in `notes`; do not invent a new author identity.

---

## 5. Other checks performed by the local AI

Correspondence review is mandatory for every queued PDF. The following checks are also recorded for every reviewed row, but deeper investigation should prioritize P0/P1/P2 cases.

### `primary_document_status`

- `OK`: selected PDF is the article itself.
- `BAD`: selected PDF is SI/supporting information, a different article, a cover page without the article, or another clearly wrong document.
- `UNCERTAIN`: cannot determine.
- `NOT_APPLICABLE`: use only when the concept truly does not apply.

For papers with several reachable PDFs, inspect filenames and first pages. This is a high-priority check because a wrong primary selection invalidates all downstream role/reference evidence.

### `text_extraction_status`

- `OK`: extracted front matter shown in the audit row represents the actual author/title/contact area well enough for deterministic parsing.
- `BAD`: important text is absent, garbled, column-interleaved beyond use, image-only, or materially different from the visible PDF.
- `UNCERTAIN` / `NOT_APPLICABLE` as above.

### `author_header_status`

- `OK`: source authors and visible PDF author header are consistent enough for role mapping.
- `BAD`: an author is missing/misattributed, ordering is materially wrong, or marker-to-author association cannot be represented by the extraction.
- `UNCERTAIN` / `NOT_APPLICABLE` as above.

Pay special attention to grouped affiliations, symbol chains, superscripts, equal-contribution notes, present-address footnotes, and names split across lines/columns.

### `reference_section_status`

Use the deterministic `reference_status` as a cue. For P0/P1/P2 cases or cases flagged `NO_REFERENCE_SECTION`, inspect the end of the article when practical:

- `OK`: parser found the correct bibliography or correctly left a truly absent bibliography empty.
- `BAD`: bibliography exists but parser missed it, segmented non-reference numbered material as references, or selected the wrong section.
- `UNCERTAIN` / `NOT_APPLICABLE` as above.

Do not require complete reference-by-reference verification during this audit; the objective is section detection and gross segmentation correctness.

---

## 6. Review JSONL schema

Write one JSON object per line to:

```text
data/phase5-validation/full-library-local-ai-audit/ai_reviews.jsonl
```

Use this schema:

```json
{
  "paper_id": 123,
  "review_status": "REVIEWED",
  "ground_truth_correspondence_status": "EXPLICIT",
  "ground_truth_corresponding_authors": ["Exact Source Author Name"],
  "primary_document_status": "OK",
  "text_extraction_status": "OK",
  "author_header_status": "OK",
  "reference_section_status": "OK",
  "issues": [],
  "notes": "Visible star on author header maps to Correspondence footnote on page 1."
}
```

For a genuinely unresolved PDF:

```json
{
  "paper_id": 123,
  "review_status": "UNRESOLVED",
  "ground_truth_correspondence_status": "UNCERTAIN",
  "ground_truth_corresponding_authors": [],
  "primary_document_status": "UNCERTAIN",
  "text_extraction_status": "UNCERTAIN",
  "author_header_status": "UNCERTAIN",
  "reference_section_status": "UNCERTAIN",
  "issues": ["IMAGE_ONLY_FRONT_MATTER"],
  "notes": "Cannot establish correspondence role without OCR."
}
```

Do not omit a queue item silently. If it cannot be decided, write an `UNRESOLVED` row.

### Checkpointing

Review in deterministic batches of approximately 25-50 papers. Append completed rows to `ai_reviews.jsonl` after each batch. Never rewrite previous reviewed rows merely to make the aggregate metrics look better.

If the local AI changes a judgment after discovering a general convention, record the changed paper IDs and rationale in the final report.

---

## 7. Score the AI ground truth against the parser

After review:

```bash
micromamba run -n Paperazzi python scripts/score_full_library_ai_review.py \
  --audit-jsonl data/phase5-validation/full-library-local-ai-audit/all_papers.jsonl \
  --reviews-jsonl data/phase5-validation/full-library-local-ai-audit/ai_reviews.jsonl \
  --output data/phase5-validation/full-library-local-ai-audit/score.json \
  --require-all-reviewed \
  --fail-on-fp \
  --min-recall 0.90
```

The scorer validates that explicit corresponding-author names come from each paper's source-author list and reports:

- missing/duplicate/invalid reviews;
- TP / FP / FN;
- precision and recall;
- every paper-level correspondence disagreement;
- BAD/OK/UNCERTAIN counts for primary selection, text extraction, author header, and reference section.

The current target gate remains conservative:

```text
false positives = 0
precision = 1.0
recall >= 0.90
```

A failed gate is a useful result. Do not alter ground truth to pass it.

---

## 8. Additional non-PDF regression tests that must remain green

The full-library PDF audit complements, rather than replaces, the unit suite. Before declaring the branch stable, retain regression coverage for:

1. **Manual author merge / future ingest**: a later occurrence using the same stable `source_creator_id` inherits a previous manual `MERGE_IDENTITY`; a different source creator with an identical name does not auto-merge.
2. **Source-mention-first correspondence evidence**: a PDF role can be stored against `PaperCreatorMention` even when canonical identity is unresolved.
3. **Contact versus role semantics**: ordinary `E-mail` / `Electronic mail` remains contact-only.
4. **Multi-corresponding-author mapping**: 0/1/N authors are supported.
5. **Symbol locality**: a marker after `Bob Jones*` must not be assigned to an earlier `Alice Smith` in the same author line.
6. **Primary/SI isolation**: supplementary PDFs must not create paper-level correspondence truth when an article is available.
7. **Provenance/retraction**: retracting bad document evidence invalidates downstream role/reference projections without deleting history.
8. **Migrations and foreign keys**: current Alembic head upgrades cleanly and `PRAGMA foreign_key_check` remains empty on a disposable DB copy.

The normal full unit suite is the authoritative automated gate for these invariants.

---

## 9. Required final deliverables from the local AI

At completion, preserve these files:

```text
summary.json
all_papers.jsonl
ai_review_queue.jsonl
ai_reviews.jsonl
score.json
FULL_LIBRARY_AUDIT_REPORT.md
```

`FULL_LIBRARY_AUDIT_REPORT.md` should contain:

- exact Git revision tested;
- Python/micromamba environment;
- DB path and confirmation that it was opened read-only;
- total active papers scanned;
- total reviewable primary PDFs;
- no-PDF / parse-error / OCR-needed counts;
- correspondence TP/FP/FN, precision, recall, unresolved count;
- every correspondence false positive;
- grouped correspondence false negatives by publisher/layout pattern;
- primary/SI selection failures;
- major text-extraction failures;
- author-header/marker failures;
- reference-section gross failures;
- a short root-cause grouping for each recurring failure class;
- **no production fixes applied unless a separate repair task is explicitly started**.

For any recurring failure pattern, include at least 3 representative `paper_id` values when available. This makes the next repair cycle testable rather than anecdotal.
