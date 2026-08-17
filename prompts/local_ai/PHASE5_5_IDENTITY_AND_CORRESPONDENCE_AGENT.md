# Paperazzi Phase 5.5 Identity and Correspondence Validation Agent

Read and follow, in full:

```text
docs/phase5/PHASE5_5_IDENTITY_AND_CORRESPONDENCE_VALIDATION.md
```

That document is authoritative for this run. Expected Alembic head is
`0007_similar_author_review_queue`.

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
2. similar-name candidate generation including abbreviation, hyphenation and review-only structured name-order reversal;
3. multi-candidate Identity Review comparison;
4. mention-level link/not-same/create-separate actions;
5. canonical merge in either direction, preserving all source spellings/publications/history;
6. persistent canonical **Different people** decision and exclusion from future suggestions;
7. same-paper merge guard;
8. sticky/direct-page pagination;
9. Paperazzi ID visibility;
10. explicit `IDENTITY UNRESOLVED` semantics;
11. sourced affiliation/contact evidence API and Author UI;
12. real-PDF correspondence benchmark and scoring.

If a deterministic code defect is found, preserve pre-fix evidence, add/strengthen a regression
test, make the smallest safe fix, rerun the full Python 3.13 suite, recreate/reset the test copy when
mutation history matters, and rerun the affected real-data stage.

Do not auto-merge people because names look similar. Do not reduce correspondence false-positive
safety to increase coverage.

## Human decisions

For real Identity Review pairs whose sameness cannot be established from local evidence, do not
choose on the user's behalf. Record the candidate pair and leave it for user review. In particular,
`UNCERTAIN` is neither Merge nor Different people.

For correspondence benchmark cases, you may inspect the actual local primary PDF and establish
paper-level ground truth from explicit correspondence evidence. Record exact source-author names.
Do not use the current prediction as ground truth.

## Required outputs

Produce the report at the path required by the authoritative document and return:

- the complete status block;
- full test count/runtime/warnings;
- migration head and foreign-key check;
- real name-variant counts before/after/idempotent rerun;
- examples demonstrating full/abbreviated/hyphenated/source-order variants are all retained;
- proof that searching a retained variant reaches the merged canonical profile;
- similar-name refresh runtime and candidate count;
- at least 30 candidate review classifications or `PENDING_USER_REVIEW` where human identity cannot
  be safely determined;
- evidence that one canonical review can show multiple candidates;
- evidence that Merge retains all source spellings/publications;
- evidence that same-paper merge is blocked;
- evidence that Different people creates persistent decision history and prevents re-suggestion;
- browser/API evidence for pagination, Paper ID, identity wording, and multi-candidate compare;
- sourced author-evidence endpoint/UI examples with ACCEPTED versus CANDIDATE clearly distinguished;
- correspondence benchmark sample size, TP/FP/FN, precision/recall and failing paper/style groups;
- explicit statement whether full correspondence population remains blocked.

Never report global PASS while any mandatory status is FAIL or a required human decision is still
pending.
