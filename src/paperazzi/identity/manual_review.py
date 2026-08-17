"""Human-in-the-loop author identity review helpers.

Source creator strings are immutable evidence.  Canonical authors group source mentions;
they never replace or normalize away the sourced spelling.  This module provides:

* reconciliation of every accepted source-name spelling into AuthorNameVariant;
* conservative similar-name suggestions for manual review;
* compare/link/not-same/create/merge actions with decision history preserved by the
  existing Phase 4 identity services.

Name similarity is a review hint only.  It never auto-merges identities.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

import sqlalchemy as sa

from paperazzi.database.base import utcnow
from paperazzi.database.models import Paper, PaperCreatorMention

from .models import (
    Author,
    AuthorExternalID,
    AuthorIdentityMembership,
    AuthorNameVariant,
    Authorship,
    ResolutionReviewQueue,
)
from .normalization import compatible_initials, name_features, normalize_search_text
from .operations import mark_not_same_person
from .review import enqueue_review, resolve_review_item
from .service import (
    IdentityResolutionError,
    accept_membership,
    create_author_for_mention,
    merge_authors,
)

_SEPARATOR_RE = re.compile(r"[\s'\-_.·•]+", re.UNICODE)


def _compact(value: str | None) -> str:
    return _SEPARATOR_RE.sub("", normalize_search_text(value)).casefold()


def _mention_name(mention: PaperCreatorMention) -> str:
    return mention.display_name or " ".join(
        part for part in (mention.first_name, mention.last_name) if part
    ) or "Unknown author"


def _ensure_variant_for_mention(session: Any, author_id: str, mention: PaperCreatorMention) -> bool:
    """Ensure one sourced spelling is represented on a canonical author.

    Memberships retain every occurrence/paper relationship.  NameVariant stores distinct
    sourced spellings, with one representative source mention for provenance.
    """
    features = name_features(mention.first_name, mention.last_name, mention.display_name)
    raw = features.raw_name or _mention_name(mention)
    existing = (
        session.query(AuthorNameVariant)
        .filter(
            AuthorNameVariant.author_id == author_id,
            AuthorNameVariant.variant_type == "SOURCE",
            AuthorNameVariant.raw_name == raw,
        )
        .first()
    )
    if existing is not None:
        return False
    session.add(
        AuthorNameVariant(
            author_id=author_id,
            source_creator_mention_id=mention.creator_mention_id,
            raw_name=raw,
            normalized_name=features.normalized_name,
            family_name=features.family_name,
            given_name=features.given_name,
            initials=features.initials,
            search_form=features.search_form,
            variant_type="SOURCE",
            provenance="paper_creator_mentions",
        )
    )
    return True


def sync_author_name_variants(session: Any, author_id: str | None = None) -> dict[str, int]:
    """Backfill all accepted source spellings into AuthorNameVariant.

    Safe and idempotent.  This is intentionally independent from identity inference:
    it records spellings only for already-accepted memberships.
    """
    query = (
        session.query(AuthorIdentityMembership, PaperCreatorMention)
        .join(
            PaperCreatorMention,
            PaperCreatorMention.creator_mention_id
            == AuthorIdentityMembership.creator_mention_id,
        )
        .filter(AuthorIdentityMembership.status == "ACCEPTED")
    )
    if author_id is not None:
        query = query.filter(AuthorIdentityMembership.author_id == author_id)
    added = 0
    seen = 0
    for membership, mention in query.all():
        seen += 1
        if _ensure_variant_for_mention(session, membership.author_id, mention):
            added += 1
    session.flush()
    return {"accepted_mentions_seen": seen, "variants_added": added}


def _variant_pair_score(left: AuthorNameVariant, right: AuthorNameVariant) -> tuple[float, dict[str, float]]:
    """Conservative similarity for review suggestions, never automatic identity truth."""
    components: dict[str, float] = {}
    lf, rf = _compact(left.family_name), _compact(right.family_name)
    lg, rg = _compact(left.given_name), _compact(right.given_name)
    lfull, rfull = _compact(left.raw_name), _compact(right.raw_name)
    if not lf or not rf or lf != rf:
        return 0.0, components
    components["family_exact"] = 0.25
    if left.normalized_name and left.normalized_name == right.normalized_name:
        components["normalized_full_exact"] = 0.75
    elif lfull and lfull == rfull:
        # Covers Tengshuo Zhang / Teng-Shuo Zhang / Teng Shuo Zhang.
        components["separator_insensitive_full"] = 0.70
    elif lg and rg and lg == rg:
        components["given_separator_insensitive"] = 0.60
    elif lg and rg and (lg.startswith(rg) or rg.startswith(lg)) and min(len(lg), len(rg)) >= 2:
        components["given_prefix"] = 0.40
    elif compatible_initials(left.initials, right.initials):
        # Abbreviation/full-name pair (e.g. T Zhang / Tengshuo Zhang). Review only.
        components["compatible_initials"] = 0.25
    return min(1.0, sum(components.values())), components


def _author_variant_map(session: Any) -> dict[str, list[AuthorNameVariant]]:
    rows = (
        session.query(AuthorNameVariant)
        .join(Author, Author.author_id == AuthorNameVariant.author_id)
        .filter(Author.status == "ACTIVE")
        .all()
    )
    out: dict[str, list[AuthorNameVariant]] = defaultdict(list)
    for row in rows:
        out[row.author_id].append(row)
    return out


def _active_papers(session: Any, author_id: str) -> set[int]:
    return {
        int(paper_id)
        for (paper_id,) in session.query(Authorship.paper_id)
        .filter_by(author_id=author_id, status="ACTIVE")
        .all()
    }


def _best_author_pair_score(
    left: list[AuthorNameVariant], right: list[AuthorNameVariant]
) -> tuple[float, dict[str, float], tuple[str, str] | None]:
    best_score = 0.0
    best_components: dict[str, float] = {}
    best_names: tuple[str, str] | None = None
    for lv in left:
        for rv in right:
            score, components = _variant_pair_score(lv, rv)
            if score > best_score:
                best_score, best_components = score, components
                best_names = (lv.raw_name, rv.raw_name)
    return best_score, best_components, best_names


def refresh_similar_identity_reviews(
    session: Any,
    *,
    minimum_score: float = 0.50,
    max_new_reviews: int = 500,
) -> dict[str, int]:
    """Queue likely duplicate canonical authors for human comparison.

    Blocking is family-name + given initial.  Same-paper identities are excluded because
    co-occurrence is a strong negative guard.  Only the strongest candidate per source
    identity is queued; the detail view can show additional candidates on demand.
    """
    sync_author_name_variants(session)
    variants = _author_variant_map(session)
    blocks: dict[tuple[str, str], set[str]] = defaultdict(set)
    for author_id, rows in variants.items():
        for row in rows:
            family = _compact(row.family_name)
            given = _compact(row.given_name)
            initial = given[:1] if given else (row.initials or "")[:1]
            if family and initial:
                blocks[(family, initial)].add(author_id)

    best_for_source: dict[str, tuple[float, str, dict[str, float], tuple[str, str] | None]] = {}
    papers_cache: dict[str, set[int]] = {}
    pair_count = 0
    for ids in blocks.values():
        ordered = sorted(ids)
        for i, left_id in enumerate(ordered):
            for right_id in ordered[i + 1 :]:
                pair_count += 1
                papers_cache.setdefault(left_id, _active_papers(session, left_id))
                papers_cache.setdefault(right_id, _active_papers(session, right_id))
                if papers_cache[left_id] & papers_cache[right_id]:
                    continue
                score, components, names = _best_author_pair_score(
                    variants[left_id], variants[right_id]
                )
                if score < minimum_score:
                    continue
                for source_id, candidate_id in ((left_id, right_id), (right_id, left_id)):
                    prev = best_for_source.get(source_id)
                    if prev is None or score > prev[0]:
                        best_for_source[source_id] = (score, candidate_id, components, names)

    created_or_updated = 0
    for source_id, (score, candidate_id, components, names) in sorted(
        best_for_source.items(), key=lambda item: (-item[1][0], item[0])
    )[:max_new_reviews]:
        enqueue_review(
            session,
            queue_type="IDENTITY_CONFLICT",
            subject_type="author",
            subject_id=source_id,
            candidate_id=candidate_id,
            reason_code="SIMILAR_NAME_VARIANTS",
            payload={
                "similarity_score": score,
                "components": components,
                "representative_names": names,
            },
            priority=95 if score >= 0.90 else 70,
        )
        created_or_updated += 1
    session.flush()
    return {
        "blocked_pairs_examined": pair_count,
        "candidate_sources": len(best_for_source),
        "reviews_created_or_updated": created_or_updated,
    }


def _author_summary(session: Any, author_id: str, *, max_papers: int = 12) -> dict[str, Any]:
    author = session.get(Author, author_id)
    if author is None:
        raise IdentityResolutionError(f"author {author_id} does not exist")
    variants = (
        session.query(AuthorNameVariant)
        .filter_by(author_id=author_id)
        .order_by(AuthorNameVariant.variant_type, AuthorNameVariant.name_variant_id)
        .all()
    )
    publications = (
        session.query(Authorship, Paper)
        .join(Paper, Paper.paper_id == Authorship.paper_id)
        .filter(Authorship.author_id == author_id, Authorship.status == "ACTIVE")
        .order_by(Paper.publication_year.desc().nullslast(), Paper.paper_id.desc())
        .limit(max_papers)
        .all()
    )
    pids = {rel.paper_id for rel, _ in publications}
    coauthor_rows = []
    if pids:
        coauthor_rows = (
            session.query(Authorship.author_id, sa.func.count(sa.distinct(Authorship.paper_id)))
            .filter(
                Authorship.paper_id.in_(pids),
                Authorship.status == "ACTIVE",
                Authorship.author_id != author_id,
            )
            .group_by(Authorship.author_id)
            .order_by(sa.func.count(sa.distinct(Authorship.paper_id)).desc())
            .limit(8)
            .all()
        )
    coauthor_ids = [row[0] for row in coauthor_rows]
    amap = {
        row.author_id: row
        for row in session.query(Author).filter(Author.author_id.in_(coauthor_ids)).all()
    } if coauthor_ids else {}
    external = (
        session.query(AuthorExternalID)
        .filter_by(author_id=author_id, status="ACCEPTED")
        .order_by(AuthorExternalID.namespace)
        .all()
    )
    return {
        "author_id": author.author_id,
        "preferred_name": author.preferred_name,
        "locked": author.locked,
        "variants": [
            {
                "raw_name": row.raw_name,
                "variant_type": row.variant_type,
                "provenance": row.provenance,
                "source_creator_mention_id": row.source_creator_mention_id,
            }
            for row in variants
        ],
        "external_ids": [
            {"namespace": row.namespace, "value": row.normalized_value}
            for row in external
        ],
        "papers": [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.publication_year,
                "source_creator_mention_id": rel.creator_mention_id,
            }
            for rel, paper in publications
        ],
        "coauthors": [
            {
                "author_id": aid,
                "preferred_name": amap[aid].preferred_name if aid in amap else aid,
                "shared_papers": int(count),
            }
            for aid, count in coauthor_rows
        ],
    }


def _candidate_authors_for_mention(
    session: Any, mention: PaperCreatorMention, *, limit: int = 12
) -> list[dict[str, Any]]:
    target = name_features(mention.first_name, mention.last_name, mention.display_name)
    family = _compact(target.family_name)
    initial = _compact(target.given_name)[:1] if target.given_name else (target.initials or "")[:1]
    if not family:
        return []
    variant_rows = (
        session.query(AuthorNameVariant)
        .join(Author, Author.author_id == AuthorNameVariant.author_id)
        .filter(Author.status == "ACTIVE")
        .all()
    )
    grouped: dict[str, list[AuthorNameVariant]] = defaultdict(list)
    for row in variant_rows:
        if _compact(row.family_name) != family:
            continue
        row_given = _compact(row.given_name)
        row_initial = row_given[:1] if row_given else (row.initials or "")[:1]
        if initial and row_initial and initial != row_initial:
            continue
        grouped[row.author_id].append(row)

    pseudo = AuthorNameVariant(
        author_id="",
        raw_name=target.raw_name,
        normalized_name=target.normalized_name,
        family_name=target.family_name,
        given_name=target.given_name,
        initials=target.initials,
        search_form=target.search_form,
        variant_type="DERIVED",
    )
    current_paper_author_ids = {
        aid
        for (aid,) in session.query(Authorship.author_id)
        .filter(Authorship.paper_id == mention.paper_id, Authorship.status == "ACTIVE")
        .all()
    }
    scored = []
    for author_id, rows in grouped.items():
        best_score = 0.0
        best_components: dict[str, float] = {}
        for row in rows:
            score, components = _variant_pair_score(pseudo, row)
            if score > best_score:
                best_score, best_components = score, components
        if best_score <= 0:
            continue
        summary = _author_summary(session, author_id, max_papers=8)
        summary.update(
            similarity_score=best_score,
            similarity_components=best_components,
            same_paper_conflict=author_id in current_paper_author_ids,
        )
        scored.append(summary)
    scored.sort(key=lambda row: (-row["similarity_score"], row["preferred_name"] or "", row["author_id"]))
    return scored[:limit]


def identity_review_detail(session: Any, review_item_id: int) -> dict[str, Any]:
    row = session.get(ResolutionReviewQueue, review_item_id)
    if row is None:
        raise KeyError(f"review_item_id={review_item_id} does not exist")
    payload = json.loads(row.payload_json or "{}")
    result: dict[str, Any] = {
        "review_item_id": row.review_item_id,
        "queue_type": row.queue_type,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "candidate_id": row.candidate_id,
        "reason_code": row.reason_code,
        "status": row.status,
        "payload": payload,
    }
    if row.subject_type == "creator_mention":
        mention = session.get(PaperCreatorMention, int(row.subject_id))
        if mention is None:
            raise IdentityResolutionError("review mention does not exist")
        paper = session.get(Paper, mention.paper_id)
        current = (
            session.query(AuthorIdentityMembership)
            .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
            .one_or_none()
        )
        candidates = _candidate_authors_for_mention(session, mention)
        if row.candidate_id and not any(c["author_id"] == row.candidate_id for c in candidates):
            candidate = session.get(Author, row.candidate_id)
            if candidate is not None and candidate.status == "ACTIVE":
                extra = _author_summary(session, candidate.author_id)
                extra.update(similarity_score=None, similarity_components={}, same_paper_conflict=False)
                candidates.insert(0, extra)
        result.update(
            source_mention={
                "creator_mention_id": mention.creator_mention_id,
                "source_name": _mention_name(mention),
                "first_name": mention.first_name,
                "last_name": mention.last_name,
                "paper_id": mention.paper_id,
                "paper_title": None if paper is None else paper.title,
                "order_index": mention.order_index,
                "current_author_id": None if current is None else current.author_id,
            },
            candidates=candidates,
        )
    elif row.subject_type == "author":
        result["source_author"] = _author_summary(session, row.subject_id)
        result["candidates"] = []
        if row.candidate_id:
            candidate = session.get(Author, row.candidate_id)
            if candidate is not None:
                result["candidates"].append(_author_summary(session, candidate.author_id))
    return result


def link_review_mention(
    session: Any,
    review_item_id: int,
    target_author_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    row = session.get(ResolutionReviewQueue, review_item_id)
    if row is None or row.status != "OPEN" or row.subject_type != "creator_mention":
        raise IdentityResolutionError("review item is not an open creator-mention identity review")
    mention = session.get(PaperCreatorMention, int(row.subject_id))
    target = session.get(Author, target_author_id)
    if mention is None or target is None:
        raise IdentityResolutionError("mention or target author does not exist")
    conflict = (
        session.query(Authorship)
        .filter(
            Authorship.paper_id == mention.paper_id,
            Authorship.author_id == target_author_id,
            Authorship.status == "ACTIVE",
            Authorship.creator_mention_id != mention.creator_mention_id,
        )
        .first()
    )
    if conflict is not None:
        raise IdentityResolutionError("target identity already occurs on this paper; manual link blocked")
    membership = accept_membership(
        session,
        mention,
        target,
        actor="MANUAL",
        reason_code="MANUAL_IDENTITY_REVIEW_LINK",
        notes=notes,
    )
    _ensure_variant_for_mention(session, target_author_id, mention)
    resolve_review_item(session, review_item_id)
    session.flush()
    return {"membership_id": membership.membership_id, "author_id": target_author_id}


def reject_review_candidate(
    session: Any,
    review_item_id: int,
    candidate_author_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    row = session.get(ResolutionReviewQueue, review_item_id)
    if row is None or row.status != "OPEN" or row.subject_type != "creator_mention":
        raise IdentityResolutionError("review item is not an open creator-mention identity review")
    mention_id = int(row.subject_id)
    membership = mark_not_same_person(
        session, mention_id, candidate_author_id, actor="MANUAL", notes=notes
    )
    if row.candidate_id == candidate_author_id:
        row.candidate_id = None
    row.reason_code = "MANUAL_NOT_SAME_REVIEW_CONTINUES"
    row.updated_at = utcnow() if hasattr(row, "updated_at") else None
    session.flush()
    return {"membership_id": membership.membership_id, "blocked_author_id": candidate_author_id}


def create_identity_from_review(
    session: Any,
    review_item_id: int,
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    row = session.get(ResolutionReviewQueue, review_item_id)
    if row is None or row.status != "OPEN" or row.subject_type != "creator_mention":
        raise IdentityResolutionError("review item is not an open creator-mention identity review")
    mention = session.get(PaperCreatorMention, int(row.subject_id))
    if mention is None:
        raise IdentityResolutionError("creator mention does not exist")
    author, membership = create_author_for_mention(
        session, mention, actor="MANUAL", reason_code="MANUAL_SEPARATE_IDENTITY"
    )
    _ensure_variant_for_mention(session, author.author_id, mention)
    resolve_review_item(session, review_item_id)
    session.flush()
    return {"author_id": author.author_id, "membership_id": membership.membership_id}


def merge_identity_review_pair(
    session: Any,
    source_author_id: str,
    target_author_id: str,
    *,
    review_item_id: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Merge two canonical identities while retaining every known source spelling."""
    source_variants = session.query(AuthorNameVariant).filter_by(author_id=source_author_id).all()
    decision = merge_authors(
        session,
        source_author_id,
        target_author_id,
        actor="MANUAL",
        notes=notes,
    )
    # The core merge preserves the source preferred name. Copy every additional sourced
    # spelling as well so abbreviations/hyphenation/transliteration history is retained.
    for variant in source_variants:
        exists = (
            session.query(AuthorNameVariant)
            .filter_by(author_id=target_author_id, raw_name=variant.raw_name)
            .first()
        )
        if exists is None:
            session.add(
                AuthorNameVariant(
                    author_id=target_author_id,
                    source_creator_mention_id=variant.source_creator_mention_id,
                    raw_name=variant.raw_name,
                    normalized_name=variant.normalized_name,
                    family_name=variant.family_name,
                    given_name=variant.given_name,
                    initials=variant.initials,
                    search_form=variant.search_form,
                    variant_type=variant.variant_type,
                    provenance=f"manual-merge:{source_author_id};{variant.provenance or ''}",
                )
            )
    sync_author_name_variants(session, target_author_id)
    if review_item_id is not None:
        row = session.get(ResolutionReviewQueue, review_item_id)
        if row is not None and row.status == "OPEN":
            resolve_review_item(session, review_item_id)
    session.flush()
    return {
        "decision_id": decision.decision_id,
        "source_author_id": source_author_id,
        "target_author_id": target_author_id,
    }
