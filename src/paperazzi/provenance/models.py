"""Persistent provenance controls for document semantics and reversible derivations."""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from paperazzi.database.base import Base, utcnow


class DocumentRole(Base):
    """Semantic role of a PDF attachment within a paper.

    Heuristic classification is intentionally low-authority and may be replaced by
    MANUAL or LOCAL_AI classification.  Absence of a row means the deterministic
    classifier should be used without mutating the database.
    """

    __tablename__ = "document_roles"
    __table_args__ = (
        sa.CheckConstraint("role IN ('PRIMARY_ARTICLE','SUPPLEMENTARY','UNKNOWN')"),
        sa.CheckConstraint("source IN ('HEURISTIC','LOCAL_AI','MANUAL')"),
        sa.Index("ix_document_roles_role", "role"),
    )

    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_documents.document_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class RetractionEvent(Base):
    """Append-only record explaining why previously accepted derivations were withdrawn."""

    __tablename__ = "retraction_events"
    __table_args__ = (
        sa.CheckConstraint(
            "root_type IN ('DOCUMENT','EXTRACTION_RUN','EXTRACTION_ATTEMPT','EVIDENCE_SPAN')"
        ),
        sa.CheckConstraint(
            "scope IN ('PAPER_LEVEL_DERIVATIONS','ALL_DERIVED_OUTPUTS')"
        ),
        sa.CheckConstraint("actor IN ('DETERMINISTIC','LOCAL_AI','MANUAL')"),
        sa.Index("ix_retraction_events_root", "root_type", "root_id"),
    )

    retraction_id: Mapped[int] = mapped_column(primary_key=True)
    root_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    root_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scope: Mapped[str] = mapped_column(sa.Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    reason_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class RetractionImpact(Base):
    """Append-only before/after record for each entity touched by a retraction."""

    __tablename__ = "retraction_impacts"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["retraction_id"], ["retraction_events.retraction_id"], ondelete="CASCADE"
        ),
        sa.Index("ix_retraction_impacts_event", "retraction_id"),
        sa.Index("ix_retraction_impacts_entity", "entity_type", "entity_id"),
    )

    impact_id: Mapped[int] = mapped_column(primary_key=True)
    retraction_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    previous_state_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resulting_state_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
