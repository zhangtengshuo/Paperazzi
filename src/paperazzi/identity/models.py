"""Phase 4 author identity and authorship models."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from paperazzi.database.base import Base, utcnow


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = (
        sa.Index("ix_authors_normalized_name", "normalized_preferred_name"),
        sa.CheckConstraint("status IN ('ACTIVE','MERGED','SUPERSEDED')"),
    )

    author_id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    preferred_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    normalized_preferred_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="ACTIVE")
    merged_into_author_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="RESTRICT"), nullable=True
    )
    locked: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class AuthorNameVariant(Base):
    __tablename__ = "author_name_variants"
    __table_args__ = (
        sa.Index("ix_author_name_variants_normalized", "normalized_name"),
        sa.Index("ix_author_name_variants_author", "author_id"),
    )

    name_variant_id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[str] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="CASCADE"), nullable=False
    )
    source_creator_mention_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("paper_creator_mentions.creator_mention_id", ondelete="RESTRICT"), nullable=True
    )
    raw_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    family_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    given_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    initials: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    search_form: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    variant_type: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint("variant_type IN ('SOURCE','DERIVED','MANUAL')"),
        nullable=False,
        default="SOURCE",
    )
    provenance: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class AuthorExternalID(Base):
    __tablename__ = "author_external_ids"
    __table_args__ = (
        sa.Index("ix_author_external_ids_author", "author_id"),
        sa.Index(
            "uq_author_external_id_accepted",
            "namespace",
            "normalized_value",
            unique=True,
            sqlite_where=sa.text("status = 'ACCEPTED'"),
        ),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    )

    external_id_id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[str] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(sa.Text, nullable=False)
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CANDIDATE")
    provenance: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class AuthorIdentityMembership(Base):
    __tablename__ = "author_identity_memberships"
    __table_args__ = (
        sa.Index("ix_identity_memberships_mention_status", "creator_mention_id", "status"),
        sa.Index(
            "uq_identity_membership_one_accepted",
            "creator_mention_id",
            unique=True,
            sqlite_where=sa.text("status = 'ACCEPTED'"),
        ),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    )

    membership_id: Mapped[int] = mapped_column(primary_key=True)
    creator_mention_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_creator_mentions.creator_mention_id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    resolver: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    decision_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("author_identity_decisions.decision_id", ondelete="SET NULL"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class AuthorIdentityDecision(Base):
    __tablename__ = "author_identity_decisions"

    decision_id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(sa.Text, nullable=False)
    actor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_author_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="RESTRICT"), nullable=True
    )
    target_author_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="RESTRICT"), nullable=True
    )
    creator_mention_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("paper_creator_mentions.creator_mention_id", ondelete="RESTRICT"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    previous_state_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resulting_state_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class AuthorIdentityEvidence(Base):
    __tablename__ = "author_identity_evidence"

    identity_evidence_id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("author_identity_memberships.membership_id", ondelete="CASCADE"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    component: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    provenance: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class Authorship(Base):
    __tablename__ = "authorships"
    __table_args__ = (
        sa.Index("ix_authorships_paper_order", "paper_id", "order_index"),
        sa.Index(
            "uq_authorship_active_mention",
            "creator_mention_id",
            unique=True,
            sqlite_where=sa.text("status = 'ACTIVE'"),
        ),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED')"),
        sa.CheckConstraint("corresponding_status IN ('UNKNOWN','CANDIDATE','ACCEPTED','REJECTED')"),
    )

    authorship_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        sa.ForeignKey("authors.author_id", ondelete="RESTRICT"), nullable=False
    )
    creator_mention_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_creator_mentions.creator_mention_id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_first_author: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    is_corresponding_author: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    corresponding_status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="UNKNOWN")
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="ACTIVE")
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class AuthorshipEvidence(Base):
    __tablename__ = "authorship_evidence"
    __table_args__ = (
        sa.CheckConstraint(
            "evidence_type IN ('AFFILIATION','CORRESPONDING_AUTHOR','EMAIL','STRUCTURED','MANUAL')"
        ),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    )

    authorship_evidence_id: Mapped[int] = mapped_column(primary_key=True)
    authorship_id: Mapped[int] = mapped_column(
        sa.ForeignKey("authorships.authorship_id", ondelete="RESTRICT"), nullable=False
    )
    evidence_span_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("document_evidence_spans.evidence_span_id", ondelete="RESTRICT"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resolver: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class ReferenceMatchEvidence(Base):
    __tablename__ = "reference_match_evidence"
    __table_args__ = (sa.Index("ix_reference_match_evidence_match", "reference_match_id"),)

    match_evidence_id: Mapped[int] = mapped_column(primary_key=True)
    reference_match_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_reference_matches.reference_match_id", ondelete="CASCADE"), nullable=False
    )
    component: Mapped[str] = mapped_column(sa.Text, nullable=False)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    contradiction: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class ResolutionReviewQueue(Base):
    __tablename__ = "resolution_review_queue"
    __table_args__ = (
        sa.Index("ix_resolution_review_queue_open", "queue_type", "status", "priority"),
        sa.Index(
            "uq_resolution_review_open_subject",
            "queue_type",
            "subject_type",
            "subject_id",
            unique=True,
            sqlite_where=sa.text("status = 'OPEN'"),
        ),
    )

    review_item_id: Mapped[int] = mapped_column(primary_key=True)
    queue_type: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "queue_type IN ('AMBIGUOUS_AUTHOR_IDENTITY','IDENTITY_CONFLICT','SIMILAR_AUTHOR_IDENTITY','UNRESOLVED_CORRESPONDING_AUTHOR','AMBIGUOUS_REFERENCE_MATCH','REFERENCE_CONTRADICTION','UNRESOLVED_REFERENCE')"
        ),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),
        nullable=False,
        default="OPEN",
    )
    reason_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    resolved_at: Mapped[Any] = mapped_column(sa.DateTime(), nullable=True)