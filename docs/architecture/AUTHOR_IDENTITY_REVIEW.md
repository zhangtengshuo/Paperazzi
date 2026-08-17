# Author Identity Review and Name-Variant Semantics

## Invariant

A bibliographic author spelling is source evidence, not a mutable profile field.
Paperazzi must retain every sourced spelling and every paper occurrence even when several
spellings are judged to represent one person.

```text
PaperCreatorMention (one sourced occurrence on one paper)
        ↓ accepted membership
Canonical Author (one person hypothesis)
        ↓
AuthorNameVariant (all recorded spellings)
```

Examples that may belong to one canonical author after review:

```text
Tengshuo Zhang
Teng-Shuo Zhang
Teng Shuo Zhang
T Zhang
T. Zhang
```

The merge does not rewrite any `PaperCreatorMention`.  Publication pages keep the sourced
name/order; the canonical author profile aggregates the occurrences and exposes all variants.

## Similarity is not identity

Separator-insensitive spelling, compatible initials, transliteration similarity, or name order
are blocking/review signals only.  A name signal alone never auto-merges two people.

The UI may suggest likely pairs, but a manual reviewer must compare:

- all recorded name variants;
- publication history;
- coauthors;
- external IDs when present;
- same-paper co-occurrence conflicts.

Same-paper co-occurrence of two active canonical identities blocks merge by default.

## Manual operations

Identity Review supports:

1. **Link mention to identity** — an unresolved paper-author occurrence is assigned to an existing canonical author. The source spelling is added as a `SOURCE` name variant.
2. **Not same person** — writes an explicit negative membership/evidence record; the candidate remains blocked for future automatic resolution.
3. **Create separate identity** — closes the review by creating a new canonical author for that occurrence.
4. **Merge identities** — combines two canonical authors after manual comparison. All source memberships, publications and distinct name variants are retained; the source canonical author becomes `MERGED` and the existing decision ledger records the operation.

All operations are reversible through the existing identity decision/history model; they are not destructive edits of Zotero data.

## Variant reconciliation

Historical identities created before interactive review may have accepted source mentions whose
spelling was not copied into `author_name_variants`. `sync_author_name_variants()` and
`scripts/sync_author_name_variants.py` repair this deterministically from accepted memberships.
The operation is idempotent and does not make identity decisions.

## Similar-name review refresh

`scripts/refresh_identity_review_candidates.py` and the UI action **Refresh similar names** scan
active canonical identities and queue conservative review candidates. The current blocking uses
family name plus given-name initial and considers exact spelling, separator-insensitive spelling,
given-name prefixes and compatible initials. It never auto-merges.

This is intentionally a candidate generator, not a global name-disambiguation algorithm. Future
ORCID, affiliation, coauthor-network and online-profile evidence can improve ranking while retaining
the same manual-decision semantics.
