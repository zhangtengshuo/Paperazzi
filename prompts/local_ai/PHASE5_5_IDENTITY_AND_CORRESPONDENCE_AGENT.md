# Paperazzi Phase 5.5 Identity and Correspondence Validation Agent

Read and follow, in full:

```text
docs/phase5/PHASE5_5_IDENTITY_AND_CORRESPONDENCE_VALIDATION.md
```

That document is authoritative for this run.

## Runtime

Use only the dedicated micromamba environment:

```text
environment = Paperazzi
Python = 3.13
```

Do not modify Anaconda/base, system Python, Zotero, Zotero PDFs, or the live Paperazzi DB.
Create a SQLite Backup API test copy and perform all write-path validation on the copy.

## Mission

Validate all currently implemented fixes, not only author-name similarity:

1. full source-name variant retention;
2. similar-name candidate generation including abbreviation/hyphenation;
3. interactive Identity Review compare/link/not-same/create/merge actions;
4. merge history and same-paper guard;
5. sticky/direct-page pagination;
6. Paperazzi ID visibility;
7. explicit `IDENTITY UNRESOLVED` semantics;
8. sourced affiliation/contact evidence API;
9. real-PDF correspondence benchmark and scoring.

If a deterministic code defect is found, preserve pre-fix evidence, add/strengthen a regression
test, make the smallest safe fix, rerun the full Python 3.13 suite, recreate/reset the test copy when
mutation history matters, and rerun the affected real-data stage.

Do not auto-merge people because names look similar. Do not reduce correspondence false-positive
safety to increase coverage.

## Human decisions

For real Identity Review pairs whose sameness cannot be established from local evidence, do not
choose on the user's behalf. Record the candidate pair and leave it for user review.

For correspondence benchmark cases, you may inspect the actual local primary PDF and establish
paper-level ground truth from explicit correspondence evidence. Record exact source-author names.
Do not use the current prediction as ground truth.

## Required outputs

Produce the report at the path required by the authoritative document and return:

- the complete status block;
- full test count/runtime;
- real name-variant counts before/after/idempotent rerun;
- similar-name refresh runtime and candidate count;
- at least 30 candidate review classifications or `PENDING_USER_REVIEW` where human identity cannot
  be safely determined;
- evidence that merge retains all source spellings/publications;
- evidence that same-paper merge is blocked;
- browser/API evidence for pagination, Paper ID, and identity wording;
- sourced author-evidence endpoint examples;
- correspondence benchmark sample size, TP/FP/FN, precision/recall and failing paper/style groups;
- explicit statement whether full correspondence population remains blocked.

Never report global PASS while any mandatory status is FAIL or a required human decision is still
pending.
