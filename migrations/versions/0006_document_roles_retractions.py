"""Phase 5 migration 0006: document semantics and reversible derivations

Revision ID: 0006_document_roles_retractions
Revises: 0005_identity_history_constraints
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_document_roles_retractions"
down_revision: Union[str, None] = "0005_identity_history_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_roles",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('PRIMARY_ARTICLE','SUPPLEMENTARY','UNKNOWN')"),
        sa.CheckConstraint("source IN ('HEURISTIC','LOCAL_AI','MANUAL')"),
        sa.ForeignKeyConstraint(["document_id"], ["paper_documents.document_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index("ix_document_roles_role", "document_roles", ["role"], unique=False)

    op.create_table(
        "retraction_events",
        sa.Column("retraction_id", sa.Integer(), nullable=False),
        sa.Column("root_type", sa.Text(), nullable=False),
        sa.Column("root_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "root_type IN ('DOCUMENT','EXTRACTION_RUN','EXTRACTION_ATTEMPT','EVIDENCE_SPAN')"
        ),
        sa.CheckConstraint("scope IN ('PAPER_LEVEL_DERIVATIONS','ALL_DERIVED_OUTPUTS')"),
        sa.CheckConstraint("actor IN ('DETERMINISTIC','LOCAL_AI','MANUAL')"),
        sa.PrimaryKeyConstraint("retraction_id"),
    )
    op.create_index(
        "ix_retraction_events_root", "retraction_events", ["root_type", "root_id"], unique=False
    )

    op.create_table(
        "retraction_impacts",
        sa.Column("impact_id", sa.Integer(), nullable=False),
        sa.Column("retraction_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("previous_state_json", sa.Text(), nullable=True),
        sa.Column("resulting_state_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["retraction_id"], ["retraction_events.retraction_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("impact_id"),
    )
    op.create_index(
        "ix_retraction_impacts_event", "retraction_impacts", ["retraction_id"], unique=False
    )
    op.create_index(
        "ix_retraction_impacts_entity",
        "retraction_impacts",
        ["entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_retraction_impacts_entity", table_name="retraction_impacts")
    op.drop_index("ix_retraction_impacts_event", table_name="retraction_impacts")
    op.drop_table("retraction_impacts")
    op.drop_index("ix_retraction_events_root", table_name="retraction_events")
    op.drop_table("retraction_events")
    op.drop_index("ix_document_roles_role", table_name="document_roles")
    op.drop_table("document_roles")
