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

The merge does not rewrite any `PaperCreatorMention`. Publication pages keep the sourced
name/order; the canonical author profile aggregates the occurrences and exposes all variants.

## Similarity is not identity

Separator-insensitive spelling, compatible initials, transliteration similarity, or structured
name-order reversal are blocking/review signals only. A name signal alone never auto-merges two
people.

The UI may suggest likely identities, but a manual reviewer must compare:

- all recorded name variants;
- publication history;
- coauthors;
- external IDs when present;
- same-paper co-occurrence conflicts.

The compare page lists several similar canonical identities rather than forcing a single candidate.
Same-paper co-occurrence is displayed as a strong negative guard and blocks merge by default.

## Manual operations

Identity Review supports:

1. **Link mention to identity** — an unresolved paper-author occurrence is assigned to an existing canonical author. The source spelling is added as a `SOURCE` name variant.
2. **Not same person (mention → author)** — writes an explicit negative membership/evidence record; that candidate remains blocked for future automatic resolution of the mention.
3. **Create separate identity** — closes the mention review by creating a new canonical author for that occurrence.
4. **Merge identities** — combines two canonical authors after manual comparison. All source memberships, publications and distinct name variants are retained; the source canonical author becomes `MERGED` and the existing decision ledger records the operation.
5. **Different people (canonical pair)** — records a manual `NOT_SAME_PERSON` decision with both canonical author IDs. The unordered pair is excluded from future similar-name suggestions, so a rejected pair does not reappear every time the candidate scan runs.

These operations are auditable identity decisions; they do not destructively rewrite Zotero data or
source creator mentions.

## Variant reconciliation

Historical identities created before interactive review may have accepted source mentions whose
spelling was not copied into `author_name_variants`. `sync_author_name_variants()` and
`scripts/sync_author_name_variants.py` repair this deterministically from accepted memberships.
The operation is idempotent and does not make identity decisions.

## Similar-name review refresh

`scripts/refresh_identity_review_candidates.py` and the UI action **Refresh similar names** scan
active canonical identities and queue conservative review candidates. The current blocking considers:

- family name plus given-name initial;
- separator-insensitive full/given spelling (`Tengshuo` vs `Teng-Shuo`);
- compatible initials (`T Zhang` vs `Tengshuo Zhang`);
- given-name prefixes;
- review-only structured given/family reversal (`Tengshuo Zhang` vs a source structured as `Zhang Tengshuo`).

It never auto-merges. Canonical pairs previously marked **Different people** and same-paper pairs are
excluded from new merge suggestions.

This is intentionally a candidate generator, not a global name-disambiguation algorithm. Future
ORCID, affiliation, coauthor-network and online-profile evidence can improve ranking while retaining
the same manual-decision semantics.
