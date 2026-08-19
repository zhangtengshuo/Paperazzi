"""Phase 5 navigation migration 0011: first-class Zotero collection catalog.

Revision ID: 0011_zotero_collection_catalog
Revises: 0010_paper_wos_match_state
Create Date: 2026-08-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_zotero_collection_catalog"
down_revision: Union[str, None] = "0010_paper_wos_match_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zotero_collections",
        sa.Column("zotero_collection_id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("collection_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_collection_id", sa.Integer(), nullable=True),
        sa.Column("parent_collection_key", sa.Text(), nullable=True),
        sa.Column("parent_name", sa.Text(), nullable=True),
        sa.Column("present_in_last_scan", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_run_id", sa.Integer(), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["first_seen_run_id"], ["zotero_scan_runs.scan_run_id"]),
        sa.ForeignKeyConstraint(["last_seen_run_id"], ["zotero_scan_runs.scan_run_id"]),
        sa.PrimaryKeyConstraint("zotero_collection_id"),
        sa.UniqueConstraint("library_id", "collection_key", name="uq_zotero_collections_identity"),
    )
    op.create_index(
        "ix_zotero_collections_library_parent",
        "zotero_collections",
        ["library_id", "parent_collection_key"],
    )
    op.create_index(
        "ix_zotero_collections_present",
        "zotero_collections",
        ["present_in_last_scan"],
    )
    op.create_index(
        "ix_zotero_collections_numeric_id",
        "zotero_collections",
        ["library_id", "collection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_zotero_collections_numeric_id", table_name="zotero_collections")
    op.drop_index("ix_zotero_collections_present", table_name="zotero_collections")
    op.drop_index("ix_zotero_collections_library_parent", table_name="zotero_collections")
    op.drop_table("zotero_collections")
