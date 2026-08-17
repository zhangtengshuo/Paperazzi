"""Phase 5.5 migration 0008: source-mention authorship role evidence

Revision ID: 0008_creator_mention_role_evidence
Revises: 0007_similar_author_review_queue
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_creator_mention_role_evidence"
down_revision: Union[str, None] = "0007_similar_author_review_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "creator_mention_role_evidence",
        sa.Column("role_evidence_id", sa.Integer(), nullable=False),
        sa.Column("creator_mention_id", sa.Integer(), nullable=False),
        sa.Column("evidence_span_id", sa.Integer(), nullable=False),
        sa.Column("role_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("resolver", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role_type IN ('CORRESPONDING_AUTHOR')"),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
        sa.ForeignKeyConstraint(
            ["creator_mention_id"],
            ["paper_creator_mentions.creator_mention_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["document_evidence_spans.evidence_span_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("role_evidence_id"),
        sa.UniqueConstraint(
            "creator_mention_id",
            "evidence_span_id",
            "role_type",
            name="uq_creator_mention_role_evidence",
        ),
    )
    op.create_index(
        "ix_creator_mention_role_status",
        "creator_mention_role_evidence",
        ["creator_mention_id", "role_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_creator_mention_role_status", table_name="creator_mention_role_evidence")
    op.drop_table("creator_mention_role_evidence")
