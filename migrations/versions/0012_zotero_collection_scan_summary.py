"""Phase 5 navigation migration 0012: collection catalog scan summary.

Revision ID: 0012_zotero_collection_scan_summary
Revises: 0011_zotero_collection_catalog
Create Date: 2026-08-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_zotero_collection_scan_summary"
down_revision: Union[str, None] = "0011_zotero_collection_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("zotero_scan_runs") as batch:
        batch.add_column(sa.Column("collection_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("collection_catalog_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("zotero_scan_runs") as batch:
        batch.drop_column("collection_catalog_hash")
        batch.drop_column("collection_count")
