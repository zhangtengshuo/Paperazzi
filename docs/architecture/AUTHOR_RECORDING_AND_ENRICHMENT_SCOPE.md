# Author recording and enrichment scope

This document is normative for Paperazzi author coverage and later enrichment.

## 1. Every paper author is recorded

Paperazzi records **all authors on every Zotero paper**, not only first and corresponding authors.

The complete source-level record is:

```text
paper_creator_mentions
```

For every Zotero creator with `creator_type='author'`, preserve:

- paper identity;
- creator order;
- sourced first/last/display name;
- source creator ID as provenance;
- source item provenance.

An unresolved person identity is not missing author data.  The source author mention remains present and queryable even when Paperazzi cannot yet prove which canonical person it belongs to.

Non-author creator types such as editors remain source creator records but are not part of the Phase-4 canonical **author** resolver.

## 2. Canonical identity is a semantic layer above complete author recording

```text
paper_creator_mentions                complete source authors
        ↓
identity candidate / decision         conservative person resolution
        ↓
authors + authorships                 accepted semantic projection
```

`authorships` is created only when a source author mention has an accepted canonical identity.  This does not change the completeness requirement of `paper_creator_mentions`.

Paperazzi must never delete or hide an ordinary author because identity resolution is ambiguous.

## 3. First and corresponding author are special roles, not separate author classes

All accepted authorships may carry role fields.

```text
is_first_author
is_corresponding_author
corresponding_status
```

First author is derived from ordered source author mentions.

Corresponding author is paper-specific and requires accepted evidence or explicit trusted structured metadata.

A person may be first/corresponding on one paper and an ordinary coauthor on another.

## 4. Enrichment priority

The later online/public-profile enrichment workflow has a narrower target than author recording.

### Priority enrichment set

Actively retrieve and maintain public researcher information for:

```text
first authors
OR
corresponding authors
```

This may later include, when publicly and explicitly available:

- current affiliation;
- education/career history;
- public researcher identifiers;
- institutional/personal research pages;
- portrait/profile image;
- public social/research-network links;
- research-field summaries and publication chronology;
- explicitly public age/gender facts only when directly stated by a reliable public source.

### Ordinary coauthors

Ordinary authors are still fully recorded as authors and participate in:

- paper-author relations;
- author ordering;
- coauthor/network structure;
- identity resolution;
- publication lists;
- citation/research-network analysis where applicable.

Paperazzi does **not** proactively perform broad biographical/profile enrichment for ordinary coauthors unless they later become a first/corresponding author in the local corpus or the user explicitly requests enrichment.

## 5. Required validation metrics

Phase 4 and later validation should distinguish:

```text
source_author_mentions
accepted_author_memberships
unresolved_author_mentions
active_authorships
papers_with_resolved_first_author
papers_with_unresolved_first_author
accepted_corresponding_authorships
papers_with_unresolved_corresponding_author
ordinary_author_mentions
```

Do not collapse `candidate memberships` and `unresolved author mentions` into one number: one unresolved mention may have multiple candidates.

## 6. Invariants

1. Every Zotero paper author is retained as a source author mention.
2. First/corresponding status is additive role metadata; it does not determine whether an author is recorded.
3. Ordinary authors remain part of the author/coauthor graph even without profile enrichment.
4. Canonical identity ambiguity never deletes source authorship information.
5. Future broad public-profile enrichment defaults to first and corresponding authors only.
