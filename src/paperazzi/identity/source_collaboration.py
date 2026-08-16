"""Immutable source-corpus collaboration features for Phase 4 identity resolution.

This module deliberately depends only on Phase-3 source projections.  It must not read
canonical identity memberships or authorships when constructing collaboration evidence,
otherwise one resolver decision can become evidence for a later resolver decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperazzi.database.models import PaperCreatorMention

from .normalization import name_features


@dataclass(frozen=True)
class CoauthorSet:
    source_creator_ids: frozenset[int]
    normalized_names: frozenset[str]


@dataclass(frozen=True)
class CollaborationOverlap:
    source_creator_overlap: int
    normalized_name_overlap: int

    @property
    def effective_overlap(self) -> int:
        # The two channels commonly describe the same collaborators, so do not add
        # them and double-count evidence.  Creator-ID overlap is preferred when it is
        # available; normalized-name overlap is a fallback/supporting channel.
        return max(self.source_creator_overlap, self.normalized_name_overlap)


class SourceCollaborationIndex:
    """Read-only collaboration index derived from all Zotero author mentions.

    `source_creator_id` is *not* treated as a person identifier.  It is only a stable
    source-local record key.  Automatic identity acceptance still requires independent
    name compatibility and repeated collaboration evidence.
    """

    def __init__(self, mentions: list[PaperCreatorMention]):
        self._mentions_by_paper: dict[int, list[PaperCreatorMention]] = {}
        self._papers_by_source_creator: dict[int, set[int]] = {}
        self._mentions_by_id: dict[int, PaperCreatorMention] = {}

        for mention in mentions:
            self._mentions_by_id[mention.creator_mention_id] = mention
            if mention.creator_type != "author":
                continue
            self._mentions_by_paper.setdefault(mention.paper_id, []).append(mention)
            if mention.source_creator_id is not None:
                self._papers_by_source_creator.setdefault(
                    mention.source_creator_id, set()
                ).add(mention.paper_id)

    @classmethod
    def from_session(cls, session: Any) -> "SourceCollaborationIndex":
        rows = (
            session.query(PaperCreatorMention)
            .filter(PaperCreatorMention.creator_type == "author")
            .order_by(
                PaperCreatorMention.paper_id,
                PaperCreatorMention.order_index,
                PaperCreatorMention.creator_mention_id,
            )
            .all()
        )
        return cls(rows)

    def mention(self, creator_mention_id: int) -> PaperCreatorMention | None:
        return self._mentions_by_id.get(creator_mention_id)

    @staticmethod
    def _normalized_name(mention: PaperCreatorMention) -> str:
        return name_features(
            mention.first_name, mention.last_name, mention.display_name
        ).normalized_name

    def paper_coauthors(
        self,
        mention: PaperCreatorMention,
        *,
        target_name: str | None = None,
    ) -> CoauthorSet:
        creator_ids: set[int] = set()
        names: set[str] = set()
        for row in self._mentions_by_paper.get(mention.paper_id, []):
            if row.creator_mention_id == mention.creator_mention_id:
                continue
            if row.source_creator_id is not None:
                creator_ids.add(row.source_creator_id)
            normalized = self._normalized_name(row)
            if normalized:
                names.add(normalized)
        if target_name:
            names.discard(target_name)
        return CoauthorSet(frozenset(creator_ids), frozenset(names))

    def historical_coauthors(
        self,
        source_creator_id: int,
        *,
        exclude_paper_id: int,
        target_name: str | None = None,
    ) -> CoauthorSet:
        creator_ids: set[int] = set()
        names: set[str] = set()
        for paper_id in self._papers_by_source_creator.get(source_creator_id, set()):
            if paper_id == exclude_paper_id:
                continue
            for row in self._mentions_by_paper.get(paper_id, []):
                # Do not let another occurrence of the same source creator become its
                # own coauthor evidence.
                if row.source_creator_id == source_creator_id:
                    continue
                if row.source_creator_id is not None:
                    creator_ids.add(row.source_creator_id)
                normalized = self._normalized_name(row)
                if normalized:
                    names.add(normalized)
        if target_name:
            names.discard(target_name)
        return CoauthorSet(frozenset(creator_ids), frozenset(names))

    def overlap(
        self,
        mention: PaperCreatorMention,
        anchor_source_creator_ids: set[int],
        *,
        target_name: str,
    ) -> CollaborationOverlap:
        current = self.paper_coauthors(mention, target_name=target_name)
        best_creator = 0
        best_name = 0
        for source_creator_id in anchor_source_creator_ids:
            historical = self.historical_coauthors(
                source_creator_id,
                exclude_paper_id=mention.paper_id,
                target_name=target_name,
            )
            best_creator = max(
                best_creator,
                len(current.source_creator_ids & historical.source_creator_ids),
            )
            best_name = max(
                best_name,
                len(current.normalized_names & historical.normalized_names),
            )
        return CollaborationOverlap(best_creator, best_name)
