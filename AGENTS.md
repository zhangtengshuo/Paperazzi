# Paperazzi Agent Contract

This file is loaded at the beginning of local-AI work. Its rules are mandatory.

## 1. Git workflow — absolute rules

- Work directly on the currently requested target branch. For normal Paperazzi work, that branch is `main`.
- **Never create a branch unless the user explicitly commands creation of a new branch.**
- **Never create a pull request.** Do not create Draft PRs, Ready-for-review PRs, temporary PRs, or review PRs.
- Do not use a PR as an intermediate merge mechanism. When changes are requested and validated, commit/push them directly to the requested target branch.
- Do not rewrite or discard unrelated user work.

## 2. Real data are read-only unless a task explicitly says otherwise

- Zotero database, Zotero storage, and source PDFs are read-only.
- A validation/audit task must not write inferred correspondence, identities, document roles, references, or other semantic truth into the live Paperazzi database.
- Validation output belongs under an ignored validation/output directory.

## 3. Mandatory protocol for corresponding-author or full-library PDF validation

Any task that asks to validate corresponding authors, PDF evidence, or the full literature library MUST read and obey:

`prompts/local_ai/FULL_LIBRARY_CORRESPONDENCE_FORENSIC_REVIEW_AGENT.md`

That document is not optional guidance. It defines the completion contract.

For such a task, the following shortcuts are forbidden:

- deciding from Paperazzi/parser predictions without opening the actual PDF;
- copying `machine_predicted_corresponding_authors` into ground truth;
- treating `role_candidates`, `contact_candidates`, risk flags, extracted e-mails, metadata, author order, or filenames as ground truth;
- reviewing a sample and extrapolating to uninspected papers;
- generating ground-truth rows in bulk from regexes, scripts, heuristics, templates, or another model;
- silently skipping papers;
- declaring `NONE_EXPLICIT` merely because the parser found no correspondence candidate;
- stopping after the first corresponding author;
- claiming completion when any required paper lacks direct-PDF evidence.

The AI must process **one paper at a time**. It must open/read that paper's real PDF, inspect the author header and correspondence/contact/footnote region, write an evidence-bearing review record for that single paper, and only then proceed to the next paper.

A review record without direct-PDF evidence is invalid even if its final answer happens to be correct.

## 4. Blind review and mechanical evidence validation are mandatory

For correspondence ground-truth creation, use a blind review queue produced by:

`python scripts/build_blind_correspondence_review_queue.py ...`

The local AI must not inspect parser predictions until its independent PDF decision for that paper has been recorded.

After review, validate the evidence contract with:

`python scripts/validate_forensic_correspondence_reviews.py ... --require-all`

If this validator fails, the audit is incomplete. Do not weaken the validator or edit review truth merely to make it pass.

After and only after the forensic validator passes, score the frozen ground truth directly with:

`python scripts/score_forensic_correspondence_reviews.py ...`

**Do not manually convert, regenerate, normalize, summarize, or rewrite the frozen forensic ground-truth rows before scoring.** Any older instruction suggesting manual conversion to the legacy `ai_reviews.jsonl` schema is superseded by this rule.

## 5. Audit and repair are separate tasks

During a ground-truth/full-library audit:

- record failures and recurring publisher/layout patterns;
- do not change production parsing rules while judging the same corpus;
- do not tune ground truth to improve precision/recall;
- finish and freeze the audit evidence first.

Production fixes belong to a later, explicitly requested repair step.
