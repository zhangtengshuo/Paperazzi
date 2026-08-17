"""Phase 5.5 migration 0007: dedicated similar-author identity review queue

Revision ID: 0007_similar_author_review_queue
Revises: 0006_document_roles_retractions
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_similar_author_review_queue"
down_revision: Union[str, None] = "0006_document_roles_retractions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_QUEUE_TYPES = (
    "AMBIGUOUS_AUTHOR_IDENTITY",
    "IDENTITY_CONFLICT",
    "SIMILAR_AUTHOR_IDENTITY",
    "UNRESOLVED_CORRESPONDING_AUTHOR",
    "AMBIGUOUS_REFERENCE_MATCH",
    "REFERENCE_CONTRADICTION",
    "UNRESOLVED_REFERENCE",
)
_OLD_QUEUE_TYPES = tuple(value for value in _NEW_QUEUE_TYPES if value != "SIMILAR_AUTHOR_IDENTITY")


def _create_review_table(table_name: str, queue_types: tuple[str, ...]) -> None:
    allowed = ",".join(repr(value) for value in queue_types)
    op.create_table(
        table_name,
        sa.Column("review_item_id", sa.Integer(), nullable=False),
        sa.Column("queue_type", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(f"queue_type IN ({allowed})"),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),
        sa.PrimaryKeyConstraint("review_item_id"),
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_resolution_review_queue_open",
        "resolution_review_queue",
        ["queue_type", "status", "priority"],
    )
    op.create_index(
        "uq_resolution_review_open_subject",
        "resolution_review_queue",
        ["queue_type", "subject_type", "subject_id"],
        unique=True,
        sqlite_where=sa.text("status = 'OPEN'"),
    )


def _rebuild(*, queue_types: tuple[str, ...], exclude_similar: bool = False) -> None:
    old_name = "_resolution_review_queue_0007_old"
    op.rename_table("resolution_review_queue", old_name)
    _create_review_table("resolution_review_queue", queue_types)
    where = " WHERE queue_type != 'SIMILAR_AUTHOR_IDENTITY'" if exclude_similar else ""
    op.execute(
        sa.text(
            "INSERT INTO resolution_review_queue "
            "(review_item_id, queue_type, subject_type, subject_id, candidate_id, priority, "
            " status, reason_code, payload_json, created_at, resolved_at) "
            "SELECT review_item_id, queue_type, subject_type, subject_id, candidate_id, priority, "
            " status, reason_code, payload_json, created_at, resolved_at "
            f"FROM {old_name}{where}"
        )
    )
    # Renaming preserves the old indexes. Dropping the old table removes those names,
    # after which the original index names can safely be recreated on the new table.
    op.drop_table(old_name)
    _create_indexes()


def upgrade() -> None:
    _rebuild(queue_types=_NEW_QUEUE_TYPES)


def downgrade() -> None:
    # Similar-name suggestions are reproducible review hints, not source data or accepted
    # identity decisions. The older schema cannot represent their queue type, so downgrade
    # intentionally drops only those derived OPEN/closed suggestion rows while preserving
    # all other review history.
    _rebuild(queue_types=_OLD_QUEUE_TYPES, exclude_similar=True)
