"""Phase 6 migration 0010: Paperazzi-side WoS matching state.

Revision ID: 0010_paper_wos_match_state
Revises: 0009_paper_wos_links
Create Date: 2026-08-18
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_paper_wos_match_state"
down_revision: Union[str, None] = "0009_paper_wos_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_wos_match_state",
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('WOS_MATCHED','WOS_NOT_IN_LOCAL_CORPUS','WOS_MATCH_AMBIGUOUS')"
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.paper_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id"),
    )
    op.create_index("ix_paper_wos_match_state_status", "paper_wos_match_state", ["status"])


def downgrade() -> None:
    op.drop_index("ix_paper_wos_match_state_status", table_name="paper_wos_match_state")
    op.drop_table("paper_wos_match_state")
