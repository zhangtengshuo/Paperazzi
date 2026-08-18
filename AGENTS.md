# Paperazzi Agent Contract

This file is loaded at the beginning of local-AI work. Its rules are mandatory.

## 1. Git workflow — absolute rules

- Work directly on the currently requested target branch. For normal Paperazzi work, that branch is `main`.
- **Never create a branch unless the user explicitly commands creation of a new branch.**
- **Never create a pull request.** Do not create Draft PRs, Ready-for-review PRs, temporary PRs, or review PRs.
- Do not use a PR as an intermediate merge mechanism. When changes are requested and validated, commit/push them directly to the requested target branch.
- Do not rewrite or discard unrelated user work.

## 2. Source boundaries and read-only user data

- Zotero database, Zotero storage, and source PDFs are read-only.
- `data/wos.sqlite3` is a Paperazzi-owned **independent Web of Science background corpus**. It must not contain Zotero item IDs, Zotero collection IDs, Paperazzi `paper_id`, attachment IDs, or other Zotero/Paperazzi foreign identities.
- `data/paperazzi.sqlite3` may store a logical bridge from a Paperazzi paper to a WoS `UT`; WoS remains independently usable and independently growable.
- A validation/audit task must not write inferred correspondence, identities, document roles, references, or other semantic truth into the live Paperazzi database unless the task explicitly requests a production update.
- Validation output belongs under an ignored validation/output directory.

## 3. WoS is the preferred production structured source

For metadata explicitly structured by an imported WoS Full Record, production consumption should prefer WoS over reconstructing the same fact from PDF layout.

Initial source preference:

```text
WoS structured Full Record
    -> publisher structured metadata (future/optional)
    -> local PDF deterministic extraction
    -> local-AI PDF recovery
```

This is a preference for effective presentation/resolution, not permission to erase provenance. Zotero, WoS, publisher, PDF and manual evidence remain distinguishable.

WoS coverage is opportunistic and monotonic, **not a completeness requirement**:

- a missing local WoS record is normal;
- a missing WoS database is normal for existing Zotero/PDF workflows;
- `WOS_NOT_IN_LOCAL_CORPUS` means only that the currently imported local WoS corpus lacks an accepted match; it does not claim that the article is absent from Web of Science;
- missing WoS data must never block Zotero ingestion, Paperazzi browsing, PDF access, identity work, validation, or unrelated tasks;
- never turn a few missing WoS records into a full-library failure condition.

The canonical architecture is documented in:

`docs/architecture/WOS_BACKGROUND_CORPUS.md`

## 4. WoS RP correspondence semantics — mandatory

WoS `RP` is a Corresponding/Reprint Address **group** representation. The `(corresponding author)` marker applies to the preceding author-name group attached to that address, not only to the immediately adjacent name.

Example:

```text
RP Xie, XY; Ma, HB (corresponding author), Shandong Univ, ...
```

means **both** `Xie, XY` and `Ma, HB` are corresponding authors.

Likewise:

```text
RP A; B; C (corresponding author), ADDRESS1.; D (corresponding author), ADDRESS2.
```

means corresponding authors `{A, B, C, D}` in two Corresponding Address groups.

Rules:

- never reduce a group to only the author immediately next to `(corresponding author)`;
- preserve repeated RP groups when one author has multiple addresses, then de-duplicate people only at the consumer/presentation layer;
- `EM` is contact data and must not by itself define the corresponding-author role;
- do not assume `EM` ordering maps positionally to RP author ordering;
- retain raw RP/EM values for provenance and debugging.

## 5. Mandatory protocol for explicit PDF correspondence audits

The following forensic protocol applies when a task **explicitly audits or validates PDF-derived correspondence/PDF evidence**, creates PDF ground truth, or benchmarks the PDF fallback parser. It does **not** require full-library PDF review merely because production correspondence can instead be obtained from structured WoS data.

For an explicit PDF correspondence/full-library PDF audit, read and obey:

`prompts/local_ai/FULL_LIBRARY_CORRESPONDENCE_FORENSIC_REVIEW_AGENT.md`

That document defines the PDF-audit completion contract.

For such a PDF audit, the following shortcuts are forbidden:

- deciding from Paperazzi/parser predictions without opening the actual PDF;
- copying `machine_predicted_corresponding_authors` into ground truth;
- treating `role_candidates`, `contact_candidates`, risk flags, extracted e-mails, metadata, author order, or filenames as PDF ground truth;
- reviewing a sample and extrapolating to uninspected papers;
- generating PDF ground-truth rows in bulk from regexes, scripts, heuristics, templates, or another model;
- silently skipping required PDF cases;
- declaring `NONE_EXPLICIT` merely because the parser found no correspondence candidate;
- stopping after the first corresponding author;
- claiming PDF-audit completion when any required paper lacks direct-PDF evidence.

The PDF-audit AI must process **one paper at a time**. It must open/read that paper's real PDF, inspect the author header and correspondence/contact/footnote region, write an evidence-bearing review record for that single paper, and only then proceed to the next paper.

A PDF forensic review record without direct-PDF evidence is invalid even if its final answer happens to be correct.

## 6. Blind PDF review and mechanical evidence validation

For PDF correspondence ground-truth creation, use a blind review queue produced by:

`python scripts/build_blind_correspondence_review_queue.py ...`

The local AI must not inspect parser predictions until its independent PDF decision for that paper has been recorded.

After review, validate the evidence contract with:

`python scripts/validate_forensic_correspondence_reviews.py ... --require-all`

If this validator fails, the PDF audit is incomplete. Do not weaken the validator or edit review truth merely to make it pass.

After and only after the forensic validator passes, score the frozen PDF ground truth directly with:

`python scripts/score_forensic_correspondence_reviews.py ...`

**Do not manually convert, regenerate, normalize, summarize, or rewrite the frozen forensic ground-truth rows before scoring.** Any older instruction suggesting manual conversion to the legacy `ai_reviews.jsonl` schema is superseded by this rule.

## 7. Audit and repair are separate tasks

During a ground-truth/PDF audit:

- record failures and recurring publisher/layout patterns;
- do not change production PDF parsing rules while judging the same corpus;
- do not tune ground truth to improve precision/recall;
- finish and freeze the audit evidence first.

Production fixes belong to a later, explicitly requested repair step.

WoS import/matching is not a PDF audit. Deterministic parsing of Clarivate tagged plain text, exact DOI/title matching, citation-edge resolution and ordinary WoS corpus maintenance may run in bulk because they operate on structured exported data rather than generating PDF ground truth.
