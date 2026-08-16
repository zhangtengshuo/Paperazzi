"""Phase 3.1 migration 0003: extraction review provenance

Revision ID: 0003_extraction_reviews
Revises: 0002_document_evidence_references
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_extraction_reviews"
down_revision: Union[str, None] = "0002_document_evidence_references"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_extraction_reviews",
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_type", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("prompt_hash", sa.Text(), nullable=True),
        sa.Column("reviewer_runtime", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("problem_codes_json", sa.Text(), nullable=True),
        sa.Column("quality_notes", sa.Text(), nullable=True),
        sa.Column("section_confidence", sa.Text(), nullable=True),
        sa.Column("segmentation_confidence", sa.Text(), nullable=True),
        sa.Column("entry_text_quality", sa.Text(), nullable=True),
        sa.Column("review_output_hash", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("reviewer_type IN ('LOCAL_AI','MANUAL')"),
        sa.CheckConstraint(
            "decision IN ('PASS','ACCEPT_PARTIAL','RETRY','UNRESOLVED','NEEDS_OCR')"
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["document_extraction_attempts.attempt_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_id"),
    )
    with op.batch_alter_table("document_extraction_reviews", schema=None) as batch_op:
        batch_op.create_index(
            "ix_extraction_reviews_attempt",
            ["attempt_id", "reviewed_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("document_extraction_reviews", schema=None) as batch_op:
        batch_op.drop_index("ix_extraction_reviews_attempt")
    op.drop_table("document_extraction_reviews")
