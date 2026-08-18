"""Paperazzi-side consumer/link layer for the independent WoS corpus."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from paperazzi.database.models import Paper
from .parser import normalize_doi
from .store import WosCorpusStore

LINK_TABLE = "paper_wos_links"
MATCH_STATE_TABLE = "paper_wos_match_state"


@dataclass(slots=True, frozen=True)
class MatchDecision:
    paper_id: int
    status: str
    wos_ut: str | None = None
    match_method: str | None = None
    match_score: float | None = None
    reason: str | None = None
    candidate_count: int = 0


def _has_table(session: Any, name: str) -> bool:
    return sa.inspect(session.get_bind()).has_table(name)


def _accepted_link(session: Any, paper_id: int) -> dict[str, Any] | None:
    if not _has_table(session, LINK_TABLE):
        return None
    row = session.execute(
        sa.text(
            "SELECT paper_wos_link_id,paper_id,wos_ut,match_method,match_score,status,matched_at,notes "
            "FROM paper_wos_links WHERE paper_id=:paper_id AND status='ACCEPTED' "
            "ORDER BY paper_wos_link_id DESC LIMIT 1"
        ),
        {"paper_id": paper_id},
    ).mappings().first()
    return dict(row) if row else None


def _stored_match_state(session: Any, paper_id: int) -> dict[str, Any] | None:
    if not _has_table(session, MATCH_STATE_TABLE):
        return None
    row = session.execute(
        sa.text(
            "SELECT paper_id,status,candidate_count,reason,checked_at "
            "FROM paper_wos_match_state WHERE paper_id=:paper_id"
        ),
        {"paper_id": paper_id},
    ).mappings().first()
    return dict(row) if row else None


def _record_matches_year(record: dict[str, Any], paper: Paper) -> bool:
    return (
        paper.publication_year is None
        or record.get("publication_year") is None
        or int(record["publication_year"]) == int(paper.publication_year)
    )


def _norm_venue(value: str | None) -> str | None:
    if not value:
        return None
    import re

    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()) or None


def decide_match(paper: Paper, store: WosCorpusStore) -> MatchDecision:
    """Conservatively match one Paper to the local WoS corpus.

    Only unique DOI-exact or exact-title candidates are auto-accepted. Missing local
    WoS coverage is a normal state and never an error.
    """
    doi = normalize_doi(paper.doi)
    if doi:
        candidates = store.find_by_doi(doi)
        if len(candidates) == 1:
            return MatchDecision(
                paper.paper_id,
                "WOS_MATCHED",
                candidates[0]["ut"],
                "DOI_EXACT",
                1.0,
                candidate_count=1,
            )
        if len(candidates) > 1:
            year_candidates = [r for r in candidates if _record_matches_year(r, paper)]
            if len(year_candidates) == 1:
                return MatchDecision(
                    paper.paper_id,
                    "WOS_MATCHED",
                    year_candidates[0]["ut"],
                    "DOI_EXACT",
                    1.0,
                    "DOI duplicate resolved by publication year",
                    len(candidates),
                )
            return MatchDecision(
                paper.paper_id,
                "WOS_MATCH_AMBIGUOUS",
                reason=f"{len(candidates)} WoS records share DOI",
                candidate_count=len(candidates),
            )
    if paper.title:
        candidates = store.find_by_exact_title(paper.title)
        if len(candidates) == 1 and _record_matches_year(candidates[0], paper):
            return MatchDecision(
                paper.paper_id,
                "WOS_MATCHED",
                candidates[0]["ut"],
                "TITLE_EXACT",
                0.99,
                candidate_count=1,
            )
        if candidates:
            year_candidates = [r for r in candidates if _record_matches_year(r, paper)]
            if len(year_candidates) == 1:
                candidate = year_candidates[0]
                pvenue = _norm_venue(paper.venue)
                wvenue = _norm_venue(candidate.get("source_title"))
                if not pvenue or not wvenue or pvenue == wvenue:
                    return MatchDecision(
                        paper.paper_id,
                        "WOS_MATCHED",
                        candidate["ut"],
                        "TITLE_YEAR_JOURNAL",
                        0.995,
                        candidate_count=len(candidates),
                    )
            return MatchDecision(
                paper.paper_id,
                "WOS_MATCH_AMBIGUOUS",
                reason=f"{len(candidates)} exact-title candidates",
                candidate_count=len(candidates),
            )
    return MatchDecision(paper.paper_id, "WOS_NOT_IN_LOCAL_CORPUS", candidate_count=0)


def _persist_match_state(session: Any, decision: MatchDecision) -> None:
    if not _has_table(session, MATCH_STATE_TABLE):
        raise RuntimeError(
            "paper_wos_match_state table is unavailable; run Alembic migration 0010"
        )
    session.execute(
        sa.text(
            "INSERT INTO paper_wos_match_state(paper_id,status,candidate_count,reason,checked_at) "
            "VALUES(:paper_id,:status,:candidate_count,:reason,CURRENT_TIMESTAMP) "
            "ON CONFLICT(paper_id) DO UPDATE SET status=excluded.status,"
            "candidate_count=excluded.candidate_count,reason=excluded.reason,checked_at=CURRENT_TIMESTAMP"
        ),
        {
            "paper_id": decision.paper_id,
            "status": decision.status,
            "candidate_count": decision.candidate_count,
            "reason": decision.reason,
        },
    )


def _supersede_accepted_link(session: Any, paper_id: int) -> bool:
    existing = _accepted_link(session, paper_id)
    if not existing:
        return False
    session.execute(
        sa.text(
            "UPDATE paper_wos_links SET status='SUPERSEDED' "
            "WHERE paper_wos_link_id=:id"
        ),
        {"id": existing["paper_wos_link_id"]},
    )
    return True


def apply_match(session: Any, decision: MatchDecision) -> bool:
    """Persist current match state and maintain at most one accepted WoS bridge.

    A fresh non-match/ambiguous result supersedes an older accepted link. Otherwise
    `WosPaperConsumer` would continue to surface stale WoS data and mask the new
    checked state.
    """
    _persist_match_state(session, decision)
    if not _has_table(session, LINK_TABLE):
        raise RuntimeError("paper_wos_links table is unavailable; run Alembic migration 0009")

    if decision.status != "WOS_MATCHED" or not decision.wos_ut or not decision.match_method:
        _supersede_accepted_link(session, decision.paper_id)
        return False

    existing = _accepted_link(session, decision.paper_id)
    if existing and existing["wos_ut"] == decision.wos_ut:
        return False
    if existing:
        _supersede_accepted_link(session, decision.paper_id)
    session.execute(
        sa.text(
            "INSERT INTO paper_wos_links(paper_id,wos_ut,match_method,match_score,status,notes) "
            "VALUES(:paper_id,:wos_ut,:match_method,:score,'ACCEPTED',:notes) "
            "ON CONFLICT(paper_id,wos_ut) DO UPDATE SET match_method=excluded.match_method,"
            "match_score=excluded.match_score,status='ACCEPTED',notes=excluded.notes,matched_at=CURRENT_TIMESTAMP"
        ),
        {
            "paper_id": decision.paper_id,
            "wos_ut": decision.wos_ut,
            "match_method": decision.match_method,
            "score": decision.match_score,
            "notes": decision.reason,
        },
    )
    return True


def match_all_papers(
    session: Any, wos_db_path: str | Path, *, apply: bool = False
) -> dict[str, Any]:
    store = WosCorpusStore(wos_db_path)
    papers = (
        session.query(Paper)
        .filter(Paper.active_in_zotero.is_(True))
        .order_by(Paper.paper_id)
        .all()
    )
    if not store.path.exists():
        return {
            "wos_database_available": False,
            "papers": len(papers),
            "matched": 0,
            "ambiguous": 0,
            "not_in_local_corpus": 0,
            "not_checked": len(papers),
            "links_written": 0,
            "states_written": 0,
            "decisions": [],
        }
    decisions = [decide_match(p, store) for p in papers]
    links_written = states_written = 0
    if apply:
        for decision in decisions:
            links_written += int(apply_match(session, decision))
            states_written += 1
    return {
        "wos_database_available": True,
        "papers": len(papers),
        "matched": sum(d.status == "WOS_MATCHED" for d in decisions),
        "ambiguous": sum(d.status == "WOS_MATCH_AMBIGUOUS" for d in decisions),
        "not_in_local_corpus": sum(
            d.status == "WOS_NOT_IN_LOCAL_CORPUS" for d in decisions
        ),
        "not_checked": 0,
        "links_written": links_written,
        "states_written": states_written,
        "decisions": [
            {
                "paper_id": d.paper_id,
                "status": d.status,
                "wos_ut": d.wos_ut,
                "match_method": d.match_method,
                "match_score": d.match_score,
                "reason": d.reason,
                "candidate_count": d.candidate_count,
            }
            for d in decisions
        ],
    }


class WosPaperConsumer:
    """Read WoS state/details for Paperazzi without copying WoS data into papers."""

    def __init__(self, session: Any, wos_db_path: str | Path):
        self.session = session
        self.store = WosCorpusStore(wos_db_path)

    @property
    def available(self) -> bool:
        return self.store.path.is_file()

    def state(self, paper_id: int) -> dict[str, Any]:
        if not self.available:
            return {
                "status": "WOS_NOT_CHECKED",
                "available": False,
                "wos_ut": None,
                "match_method": None,
                "reason": "LOCAL_WOS_CORPUS_UNAVAILABLE",
            }
        link = _accepted_link(self.session, paper_id)
        if link is not None:
            if self.store.get_record(str(link["wos_ut"])) is None:
                return {
                    "status": "WOS_NOT_IN_LOCAL_CORPUS",
                    "available": True,
                    "wos_ut": link["wos_ut"],
                    "match_method": link["match_method"],
                    "stale_link": True,
                    "reason": "ACCEPTED_LINK_TARGET_NOT_PRESENT_IN_CURRENT_WOS_CORPUS",
                }
            return {
                "status": "WOS_MATCHED",
                "available": True,
                "wos_ut": link["wos_ut"],
                "match_method": link["match_method"],
                "match_score": link["match_score"],
            }
        stored = _stored_match_state(self.session, paper_id)
        if stored is None:
            return {
                "status": "WOS_NOT_CHECKED",
                "available": True,
                "wos_ut": None,
                "match_method": None,
                "reason": "NO_STORED_MATCH_RUN_FOR_PAPER",
            }
        return {
            "status": stored["status"],
            "available": True,
            "wos_ut": None,
            "match_method": None,
            "candidate_count": stored["candidate_count"],
            "reason": stored["reason"],
            "checked_at": stored["checked_at"],
        }

    def detail(self, paper_id: int) -> dict[str, Any]:
        state = self.state(paper_id)
        if state["status"] != "WOS_MATCHED":
            return state
        record = self.store.get_record(str(state["wos_ut"]))
        assert record is not None
        corresponding: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for group in record.get("correspondence_groups", []):
            for member in group.get("members", []):
                key = (
                    member.get("wos_author_id")
                    or member.get("normalized_member_name")
                    or member.get("raw_member_name")
                )
                if key in seen:
                    continue
                seen.add(key)
                corresponding.append(
                    {
                        "au_name": member.get("au_name")
                        or member.get("raw_member_name"),
                        "full_name": member.get("full_name"),
                        "raw_member_name": member.get("raw_member_name"),
                    }
                )
        return {
            **state,
            "record": {
                "ut": record["ut"],
                "doi": record.get("doi"),
                "title": record.get("title"),
                "source_title": record.get("source_title"),
                "publication_year": record.get("publication_year"),
                "abstract": record.get("abstract"),
                "times_cited_wos": record.get("times_cited_wos"),
                "times_cited_total": record.get("times_cited_total"),
                "pmid": record.get("pmid"),
                "authors": record.get("authors", []),
                "corresponding_authors": corresponding,
                "emails": record.get("emails", []),
                "organizations": record.get("organizations", []),
                "keywords": record.get("keywords", []),
                "classifications": record.get("classifications", []),
                "funding": record.get("funding", {}),
                "reference_count": record.get("reference_count", 0),
                "resolved_reference_count": record.get(
                    "resolved_reference_count", 0
                ),
            },
        }
