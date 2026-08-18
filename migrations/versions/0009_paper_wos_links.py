"""Phase 6 migration 0009: Paperazzi-to-WoS integration links.

The WoS corpus remains a separate SQLite database.  This table stores only the
Paperazzi-side logical link to an external WoS UT identifier.

Revision ID: 0009_paper_wos_links
Revises: 0008_creator_mention_role_evidence
Create Date: 2026-08-18
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_paper_wos_links"
down_revision: Union[str, None] = "0008_creator_mention_role_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_wos_links",
        sa.Column("paper_wos_link_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("wos_ut", sa.Text(), nullable=False),
        sa.Column("match_method", sa.Text(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "match_method IN ('DOI_EXACT','TITLE_EXACT','TITLE_YEAR_JOURNAL','COMPOSITE','MANUAL')"
        ),
        sa.CheckConstraint("status IN ('ACCEPTED','CANDIDATE','REJECTED','SUPERSEDED')"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.paper_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_wos_link_id"),
        sa.UniqueConstraint("paper_id", "wos_ut", name="uq_paper_wos_link_pair"),
    )
    op.create_index("ix_paper_wos_links_paper_status", "paper_wos_links", ["paper_id", "status"])
    op.create_index("ix_paper_wos_links_ut_status", "paper_wos_links", ["wos_ut", "status"])
    op.create_index(
        "uq_paper_wos_one_accepted",
        "paper_wos_links",
        ["paper_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_paper_wos_one_accepted", table_name="paper_wos_links")
    op.drop_index("ix_paper_wos_links_ut_status", table_name="paper_wos_links")
    op.drop_index("ix_paper_wos_links_paper_status", table_name="paper_wos_links")
    op.drop_table("paper_wos_links")
