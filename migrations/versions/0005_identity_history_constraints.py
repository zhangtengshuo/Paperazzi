"""Phase 4 migration 0005: make identity history repeatable

Revision ID: 0005_identity_history_constraints
Revises: 0004_identity_resolution
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_identity_history_constraints"
down_revision: Union[str, None] = "0004_identity_resolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Historical membership rows must be allowed to revisit the same state across
    # merge/split/re-resolution cycles. The partial ACCEPTED index from 0004 is the
    # actual invariant we need: at most one accepted author per creator mention.
    with op.batch_alter_table("author_identity_memberships", schema=None) as batch_op:
        batch_op.drop_constraint("uq_identity_membership_state", type_="unique")

    # External identifiers are authoritative only when ACCEPTED. Candidate/rejected
    # conflicting records must remain persistable for review provenance.
    with op.batch_alter_table("author_external_ids", schema=None) as batch_op:
        batch_op.drop_constraint("uq_author_external_id", type_="unique")
    op.create_index(
        "uq_author_external_id_accepted",
        "author_external_ids",
        ["namespace", "normalized_value"],
        unique=True,
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_author_external_id_accepted", table_name="author_external_ids")
    with op.batch_alter_table("author_external_ids", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_author_external_id", ["namespace", "normalized_value"]
        )
    with op.batch_alter_table("author_identity_memberships", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_identity_membership_state",
            ["creator_mention_id", "author_id", "status"],
        )
