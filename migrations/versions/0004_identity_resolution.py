"""Phase 4 migration 0004: author identity, authorship, resolution evidence

Revision ID: 0004_identity_resolution
Revises: 0003_extraction_reviews
Create Date: 2026-08-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_identity_resolution"
down_revision: Union[str, None] = "0003_extraction_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "authors",
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("preferred_name", sa.Text(), nullable=True),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("merged_into_author_id", sa.Text(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','MERGED','RETIRED')"),
        sa.ForeignKeyConstraint(
            ["merged_into_author_id"], ["authors.author_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("author_id"),
    )
    op.create_index("ix_authors_normalized_name", "authors", ["normalized_name"])

    op.create_table(
        "author_name_variants",
        sa.Column("name_variant_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("source_creator_mention_id", sa.Integer(), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("family_name", sa.Text(), nullable=True),
        sa.Column("given_name", sa.Text(), nullable=True),
        sa.Column("initials", sa.Text(), nullable=True),
        sa.Column("search_form", sa.Text(), nullable=True),
        sa.Column("variant_type", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("variant_type IN ('SOURCE','DERIVED','MANUAL')"),
        sa.ForeignKeyConstraint(["author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_creator_mention_id"],
            ["paper_creator_mentions.creator_mention_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("name_variant_id"),
    )
    op.create_index(
        "ix_author_name_variants_normalized",
        "author_name_variants",
        ["normalized_name"],
    )
    op.create_index(
        "ix_author_name_variants_author",
        "author_name_variants",
        ["author_id"],
    )

    op.create_table(
        "author_external_ids",
        sa.Column("external_id_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('ACCEPTED','REJECTED','SUPERSEDED')"),
        sa.ForeignKeyConstraint(["author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("external_id_id"),
        sa.UniqueConstraint("namespace", "normalized_value", name="uq_author_external_id"),
    )

    op.create_table(
        "author_identity_memberships",
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("creator_mention_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolver", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_components_json", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
        sa.ForeignKeyConstraint(
            ["creator_mention_id"],
            ["paper_creator_mentions.creator_mention_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("membership_id"),
        sa.UniqueConstraint(
            "creator_mention_id", "author_id", "status",
            name="uq_identity_membership_state",
        ),
    )
    op.create_index(
        "ix_identity_memberships_mention_status",
        "author_identity_memberships",
        ["creator_mention_id", "status"],
    )
    op.create_index(
        "uq_identity_membership_one_accepted",
        "author_identity_memberships",
        ["creator_mention_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )

    op.create_table(
        "author_identity_decisions",
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("creator_mention_id", sa.Integer(), nullable=True),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("source_author_id", sa.Text(), nullable=True),
        sa.Column("target_author_id", sa.Text(), nullable=True),
        sa.Column("algorithm_version", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("previous_state_json", sa.Text(), nullable=True),
        sa.Column("resulting_state_json", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('CREATE_IDENTITY','LINK_MENTION','UNLINK_MENTION','MERGE_IDENTITY','SPLIT_IDENTITY','NOT_SAME_PERSON','LOCK_IDENTITY','UNLOCK_IDENTITY')"
        ),
        sa.CheckConstraint("actor IN ('DETERMINISTIC','LOCAL_AI','MANUAL')"),
        sa.ForeignKeyConstraint(
            ["creator_mention_id"], ["paper_creator_mentions.creator_mention_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["author_identity_memberships.membership_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("decision_id"),
    )

    op.create_table(
        "author_identity_evidence",
        sa.Column("identity_evidence_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("creator_mention_id", sa.Integer(), nullable=False),
        sa.Column("candidate_author_id", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("polarity", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("polarity IN ('POSITIVE','NEGATIVE','CONFLICT')"),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["author_identity_memberships.membership_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["creator_mention_id"], ["paper_creator_mentions.creator_mention_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["candidate_author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("identity_evidence_id"),
    )

    op.create_table(
        "authorships",
        sa.Column("authorship_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("creator_mention_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("creator_type", sa.Text(), nullable=True),
        sa.Column("is_first_author", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_corresponding_author", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("corresponding_status", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("corresponding_status IN ('UNKNOWN','CANDIDATE','ACCEPTED','REJECTED')"),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED')"),
        sa.ForeignKeyConstraint(["author_id"], ["authors.author_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.paper_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["creator_mention_id"], ["paper_creator_mentions.creator_mention_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("authorship_id"),
    )
    op.create_index("ix_authorships_paper_order", "authorships", ["paper_id", "order_index"])
    op.create_index(
        "uq_authorship_active_mention",
        "authorships",
        ["creator_mention_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "authorship_evidence",
        sa.Column("authorship_evidence_id", sa.Integer(), nullable=False),
        sa.Column("authorship_id", sa.Integer(), nullable=False),
        sa.Column("evidence_span_id", sa.Integer(), nullable=True),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("resolver", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('AFFILIATION','CORRESPONDING_AUTHOR','EMAIL','STRUCTURED','MANUAL')"
        ),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
        sa.ForeignKeyConstraint(["authorship_id"], ["authorships.authorship_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"], ["document_evidence_spans.evidence_span_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("authorship_evidence_id"),
    )

    op.create_table(
        "reference_match_evidence",
        sa.Column("match_evidence_id", sa.Integer(), nullable=False),
        sa.Column("reference_match_id", sa.Integer(), nullable=False),
        sa.Column("component", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("contradiction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reference_match_id"], ["paper_reference_matches.reference_match_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("match_evidence_id"),
    )
    op.create_index(
        "ix_reference_match_evidence_match",
        "reference_match_evidence",
        ["reference_match_id"],
    )
    op.create_index(
        "uq_reference_one_accepted_match",
        "paper_reference_matches",
        ["reference_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )

    op.create_table(
        "resolution_review_queue",
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
        sa.CheckConstraint(
            "queue_type IN ('AMBIGUOUS_AUTHOR_IDENTITY','IDENTITY_CONFLICT','UNRESOLVED_CORRESPONDING_AUTHOR','AMBIGUOUS_REFERENCE_MATCH','REFERENCE_CONTRADICTION','UNRESOLVED_REFERENCE')"
        ),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),
        sa.PrimaryKeyConstraint("review_item_id"),
    )
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


def downgrade() -> None:
    op.drop_index("uq_resolution_review_open_subject", table_name="resolution_review_queue")
    op.drop_index("ix_resolution_review_queue_open", table_name="resolution_review_queue")
    op.drop_table("resolution_review_queue")
    op.drop_index("uq_reference_one_accepted_match", table_name="paper_reference_matches")
    op.drop_index("ix_reference_match_evidence_match", table_name="reference_match_evidence")
    op.drop_table("reference_match_evidence")
    op.drop_table("authorship_evidence")
    op.drop_index("uq_authorship_active_mention", table_name="authorships")
    op.drop_index("ix_authorships_paper_order", table_name="authorships")
    op.drop_table("authorships")
    op.drop_table("author_identity_evidence")
    op.drop_table("author_identity_decisions")
    op.drop_index("uq_identity_membership_one_accepted", table_name="author_identity_memberships")
    op.drop_index("ix_identity_memberships_mention_status", table_name="author_identity_memberships")
    op.drop_table("author_identity_memberships")
    op.drop_table("author_external_ids")
    op.drop_index("ix_author_name_variants_author", table_name="author_name_variants")
    op.drop_index("ix_author_name_variants_normalized", table_name="author_name_variants")
    op.drop_table("author_name_variants")
    op.drop_index("ix_authors_normalized_name", table_name="authors")
    op.drop_table("authors")
