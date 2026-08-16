"""Accepted-reference-only local citation resolver for Phase 4.

The resolver is intentionally conservative: unique DOI exact matches may be accepted
immediately. Bibliographic matches require exact normalized title evidence reinforced
by metadata and a clear score margin. Ambiguity is persisted to the review queue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from paperazzi.database.models import (
    Paper,
    PaperCreatorMention,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceMatch,
)

from .models import ReferenceMatchEvidence
from .normalization import normalize_search_text
from .review import enqueue_review

RESOLVER_VERSION = "phase4-reference-v1"
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True)
class IndexedPaper:
    paper_id: int
    title: str
    normalized_title: str
    doi: str | None
    year: int | None
    venue: str
    normalized_venue: str
    first_author_family: str | None


@dataclass(frozen=True)
class MatchCandidate:
    paper: IndexedPaper
    match_type: str
    score: float
    components: dict[str, float]
    contradiction: bool = False


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = _DOI_PREFIX_RE.sub("", value.strip()).strip().lower()
    value = value.rstrip(".,;)"] if value else value
    return value or None


def normalize_title(value: str | None) -> str:
    return normalize_search_text(value)


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value) if len(token) > 1}


def _title_coverage(title: str, reference_text: str) -> float:
    title_tokens = _tokens(title)
    if not title_tokens:
        return 0.0
    ref_tokens = _tokens(reference_text)
    return len(title_tokens & ref_tokens) / len(title_tokens)


def _first_author_family(session: Any, paper_id: int) -> str | None:
    mention = (
        session.query(PaperCreatorMention)
        .filter_by(paper_id=paper_id, creator_type="author")
        .order_by(PaperCreatorMention.order_index)
        .first()
    )
    return normalize_search_text(mention.last_name) if mention and mention.last_name else None


class LocalReferenceResolver:
    def __init__(self, session: Any, *, resolver_version: str = RESOLVER_VERSION):
        self.session = session
        self.resolver_version = resolver_version
        self.paper_index = [
            IndexedPaper(
                paper_id=paper.paper_id,
                title=paper.title or "",
                normalized_title=normalize_title(paper.title),
                doi=normalize_doi(paper.doi),
                year=paper.publication_year,
                venue=paper.venue or "",
                normalized_venue=normalize_search_text(paper.venue),
                first_author_family=_first_author_family(session, paper.paper_id),
            )
            for paper in session.query(Paper).all()
        ]
        self.by_doi: dict[str, list[IndexedPaper]] = {}
        for paper in self.paper_index:
            if paper.doi:
                self.by_doi.setdefault(paper.doi, []).append(paper)

    def _reference_identifiers(self, reference_id: int) -> tuple[set[str], set[int]]:
        rows = (
            self.session.query(PaperReferenceIdentifier)
            .filter_by(reference_id=reference_id)
            .all()
        )
        dois = {
            doi
            for doi in (
                normalize_doi(row.normalized_value or row.identifier_value)
                for row in rows
                if row.identifier_type == "DOI"
            )
            if doi
        }
        years: set[int] = set()
        for row in rows:
            if row.identifier_type != "YEAR":
                continue
            try:
                years.add(int(row.normalized_value or row.identifier_value))
            except (TypeError, ValueError):
                pass
        return dois, years

    def _existing_accepted(self, reference_id: int) -> PaperReferenceMatch | None:
        return (
            self.session.query(PaperReferenceMatch)
            .filter_by(reference_id=reference_id, status="ACCEPTED")
            .one_or_none()
        )

    def _persist_match(self, reference: PaperReference, candidate: MatchCandidate, status: str):
        row = (
            self.session.query(PaperReferenceMatch)
            .filter_by(
                reference_id=reference.reference_id,
                cited_paper_id=candidate.paper.paper_id,
                resolver=self.resolver_version,
            )
            .one_or_none()
        )
        if row is None:
            row = PaperReferenceMatch(
                reference_id=reference.reference_id,
                cited_paper_id=candidate.paper.paper_id,
                match_type=candidate.match_type,
                match_score=candidate.score,
                status=status,
                resolver=self.resolver_version,
            )
            self.session.add(row)
            self.session.flush()
        else:
            row.match_type = candidate.match_type
            row.match_score = candidate.score
            row.status = status
            self.session.flush()
            self.session.query(ReferenceMatchEvidence).filter_by(
                reference_match_id=row.reference_match_id
            ).delete()

        for component, score in candidate.components.items():
            self.session.add(
                ReferenceMatchEvidence(
                    reference_match_id=row.reference_match_id,
                    component=component,
                    score=score,
                    value=None,
                    contradiction=candidate.contradiction,
                )
            )
        self.session.flush()
        return row

    def _doi_candidates(
        self, reference: PaperReference, dois: set[str]
    ) -> list[MatchCandidate]:
        seen: dict[int, MatchCandidate] = {}
        for doi in dois:
            for paper in self.by_doi.get(doi, []):
                if paper.paper_id == reference.citing_paper_id:
                    continue
                seen[paper.paper_id] = MatchCandidate(
                    paper=paper,
                    match_type="DOI_EXACT",
                    score=1.0,
                    components={"identifier_score": 1.0},
                )
        return list(seen.values())

    def _bibliographic_candidates(
        self,
        reference: PaperReference,
        years: set[int],
        reference_dois: set[str],
    ) -> list[MatchCandidate]:
        raw = normalize_search_text(reference.raw_text)
        candidates: list[MatchCandidate] = []
        for paper in self.paper_index:
            if paper.paper_id == reference.citing_paper_id:
                continue
            if years and paper.year is not None and paper.year not in years:
                continue
            if not paper.normalized_title or len(paper.normalized_title) < 10:
                continue

            components: dict[str, float] = {}
            exact_title = paper.normalized_title in raw
            coverage = _title_coverage(paper.normalized_title, raw)
            if exact_title:
                components["title_score"] = 0.72
            elif coverage >= 0.65:
                components["title_score"] = round(0.55 * coverage, 6)
            else:
                continue

            if years and paper.year in years:
                components["year_score"] = 0.12
            if paper.normalized_venue:
                venue_tokens = _tokens(paper.normalized_venue)
                raw_tokens = _tokens(raw)
                venue_coverage = (
                    len(venue_tokens & raw_tokens) / len(venue_tokens)
                    if venue_tokens else 0.0
                )
                if paper.normalized_venue in raw or venue_coverage >= 0.7:
                    components["venue_score"] = 0.08
            if paper.first_author_family and paper.first_author_family in raw:
                components["author_score"] = 0.08

            contradiction = bool(
                reference_dois and paper.doi and paper.doi not in reference_dois
            )
            score = min(1.0, sum(components.values()))
            if score < 0.55:
                continue
            candidates.append(
                MatchCandidate(
                    paper=paper,
                    match_type=(
                        "TITLE_EXACT_NORMALIZED"
                        if exact_title
                        else "BIBLIOGRAPHIC_COMPOSITE"
                    ),
                    score=score,
                    components=components,
                    contradiction=contradiction,
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates

    def resolve(self, reference: PaperReference) -> dict[str, Any]:
        if reference.acceptance_status != "ACCEPTED":
            return {"status": "SKIPPED_UNACCEPTED", "reference_id": reference.reference_id}

        already = self._existing_accepted(reference.reference_id)
        if already is not None:
            return {
                "status": "ALREADY_ACCEPTED",
                "reference_id": reference.reference_id,
                "cited_paper_id": already.cited_paper_id,
            }

        dois, years = self._reference_identifiers(reference.reference_id)
        doi_candidates = self._doi_candidates(reference, dois)
        if len(doi_candidates) == 1:
            match = self._persist_match(reference, doi_candidates[0], "ACCEPTED")
            return {
                "status": "ACCEPTED",
                "match_type": "DOI_EXACT",
                "reference_match_id": match.reference_match_id,
                "cited_paper_id": match.cited_paper_id,
            }
        if len(doi_candidates) > 1:
            for candidate in doi_candidates[:5]:
                self._persist_match(reference, candidate, "CANDIDATE")
            enqueue_review(
                self.session,
                queue_type="AMBIGUOUS_REFERENCE_MATCH",
                subject_type="paper_reference",
                subject_id=reference.reference_id,
                reason_code="DUPLICATE_LOCAL_DOI",
                payload={"candidate_paper_ids": [c.paper.paper_id for c in doi_candidates]},
                priority=90,
            )
            return {"status": "AMBIGUOUS", "candidate_count": len(doi_candidates)}

        candidates = self._bibliographic_candidates(reference, years, dois)
        if not candidates:
            enqueue_review(
                self.session,
                queue_type="UNRESOLVED_REFERENCE",
                subject_type="paper_reference",
                subject_id=reference.reference_id,
                reason_code="NO_LOCAL_CANDIDATE",
                payload={"years": sorted(years), "dois": sorted(dois)},
                priority=30,
            )
            return {"status": "UNRESOLVED", "candidate_count": 0}

        top = candidates[0]
        second = candidates[1].score if len(candidates) > 1 else 0.0
        for candidate in candidates[:5]:
            self._persist_match(reference, candidate, "CANDIDATE")

        if top.contradiction:
            enqueue_review(
                self.session,
                queue_type="REFERENCE_CONTRADICTION",
                subject_type="paper_reference",
                subject_id=reference.reference_id,
                candidate_id=top.paper.paper_id,
                reason_code="BIBLIOGRAPHIC_MATCH_CONTRADICTS_DOI",
                payload={"score": top.score, "components": top.components},
                priority=95,
            )
            return {"status": "CONTRADICTION", "candidate_count": len(candidates)}

        exact_title = top.match_type == "TITLE_EXACT_NORMALIZED"
        if exact_title and top.score >= 0.90 and top.score - second >= 0.12:
            match = self._persist_match(reference, top, "ACCEPTED")
            return {
                "status": "ACCEPTED",
                "match_type": top.match_type,
                "reference_match_id": match.reference_match_id,
                "cited_paper_id": match.cited_paper_id,
                "score": top.score,
            }

        enqueue_review(
            self.session,
            queue_type="AMBIGUOUS_REFERENCE_MATCH",
            subject_type="paper_reference",
            subject_id=reference.reference_id,
            candidate_id=top.paper.paper_id,
            reason_code="COMPOSITE_MATCH_REQUIRES_REVIEW",
            payload={
                "top_score": top.score,
                "second_score": second,
                "candidate_count": len(candidates),
                "components": top.components,
            },
            priority=70 if top.score >= 0.8 else 50,
        )
        return {"status": "AMBIGUOUS", "candidate_count": len(candidates)}

    def resolve_all(self, *, limit: int | None = None) -> dict[str, int]:
        query = self.session.query(PaperReference).filter_by(acceptance_status="ACCEPTED")
        if limit is not None:
            query = query.limit(limit)
        counts: dict[str, int] = {}
        for reference in query.all():
            result = self.resolve(reference)
            status = result["status"]
            counts[status] = counts.get(status, 0) + 1
        self.session.flush()
        return counts
