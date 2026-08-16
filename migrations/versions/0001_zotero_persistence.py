"""Phase 3 migration 0001: Zotero persistence

Revision ID: 0001_zotero_persistence
Revises: None
Create Date: 2026-08-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_zotero_persistence'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('zotero_scan_runs',
    sa.Column('scan_run_id', sa.Integer(), nullable=False),
    sa.Column('run_token', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('source_db_path', sa.Text(), nullable=False),
    sa.Column('source_db_size', sa.Integer(), nullable=True),
    sa.Column('source_db_mtime_ns', sa.Integer(), nullable=True),
    sa.Column('snapshot_path', sa.Text(), nullable=True),
    sa.Column('adapter_name', sa.Text(), nullable=True),
    sa.Column('userdata_version', sa.Integer(), nullable=True),
    sa.Column('global_schema_version', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('item_count', sa.Integer(), nullable=True),
    sa.Column('new_count', sa.Integer(), nullable=True),
    sa.Column('modified_count', sa.Integer(), nullable=True),
    sa.Column('unchanged_count', sa.Integer(), nullable=True),
    sa.Column('removed_count', sa.Integer(), nullable=True),
    sa.Column('restored_count', sa.Integer(), nullable=True),
    sa.Column('bibliographic_corpus_hash', sa.Text(), nullable=True),
    sa.Column('canonical_corpus_hash', sa.Text(), nullable=True),
    sa.Column('error_type', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('scan_run_id'),
    sa.UniqueConstraint('run_token')
    )
    op.create_table('papers',
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('doi', sa.Text(), nullable=True),
    sa.Column('publication_year', sa.Integer(), nullable=True),
    sa.Column('publication_date_text', sa.Text(), nullable=True),
    sa.Column('venue', sa.Text(), nullable=True),
    sa.Column('item_type', sa.Text(), nullable=True),
    sa.Column('active_in_zotero', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('paper_id')
    )
    op.create_table('zotero_item_state',
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('library_id', sa.Integer(), nullable=False),
    sa.Column('item_key', sa.Text(), nullable=False),
    sa.Column('zotero_item_id', sa.Integer(), nullable=True),
    sa.Column('item_type', sa.Text(), nullable=True),
    sa.Column('zotero_version', sa.Integer(), nullable=True),
    sa.Column('date_added', sa.Text(), nullable=True),
    sa.Column('date_modified', sa.Text(), nullable=True),
    sa.Column('client_date_modified', sa.Text(), nullable=True),
    sa.Column('deleted', sa.Boolean(), nullable=False),
    sa.Column('present_in_last_scan', sa.Boolean(), nullable=False),
    sa.Column('first_seen_run_id', sa.Integer(), nullable=False),
    sa.Column('last_seen_run_id', sa.Integer(), nullable=False),
    sa.Column('bibliographic_hash', sa.Text(), nullable=True),
    sa.Column('organization_hash', sa.Text(), nullable=True),
    sa.Column('attachment_hash', sa.Text(), nullable=True),
    sa.Column('canonical_hash', sa.Text(), nullable=True),
    sa.Column('canonical_payload_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['first_seen_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['last_seen_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('zotero_item_state_id'),
    sa.UniqueConstraint('library_id', 'item_key', name='uq_zotero_item_state_identity')
    )
    op.create_table('zotero_item_versions',
    sa.Column('zotero_item_version_id', sa.Integer(), nullable=False),
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('scan_run_id', sa.Integer(), nullable=False),
    sa.Column('change_type', sa.Text(), nullable=False),
    sa.Column('changed_dimensions_json', sa.Text(), nullable=True),
    sa.Column('bibliographic_hash', sa.Text(), nullable=True),
    sa.Column('organization_hash', sa.Text(), nullable=True),
    sa.Column('attachment_hash', sa.Text(), nullable=True),
    sa.Column('canonical_hash', sa.Text(), nullable=True),
    sa.Column('canonical_payload_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("change_type IN ('NEW','MODIFIED','REMOVED','RESTORED')"),
    sa.ForeignKeyConstraint(['scan_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['zotero_item_state_id'], ['zotero_item_state.zotero_item_state_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('zotero_item_version_id'),
    sa.UniqueConstraint('zotero_item_state_id', 'scan_run_id', name='uq_item_version_scan')
    )
    op.create_table('paper_creator_mentions',
    sa.Column('creator_mention_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('source_creator_id', sa.Integer(), nullable=True),
    sa.Column('creator_type', sa.Text(), nullable=True),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('first_name', sa.Text(), nullable=True),
    sa.Column('last_name', sa.Text(), nullable=True),
    sa.Column('field_mode', sa.Integer(), nullable=True),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['zotero_item_state_id'], ['zotero_item_state.zotero_item_state_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('creator_mention_id')
    )
    op.create_table('zotero_item_tags',
    sa.Column('zotero_item_tag_id', sa.Integer(), nullable=False),
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=True),
    sa.Column('tag_type', sa.Integer(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['zotero_item_state_id'], ['zotero_item_state.zotero_item_state_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('zotero_item_tag_id')
    )
    op.create_table('zotero_item_collections',
    sa.Column('zotero_item_collection_id', sa.Integer(), nullable=False),
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('collection_id', sa.Integer(), nullable=True),
    sa.Column('collection_key', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('parent_collection_id', sa.Integer(), nullable=True),
    sa.Column('parent_collection_key', sa.Text(), nullable=True),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['zotero_item_state_id'], ['zotero_item_state.zotero_item_state_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('zotero_item_collection_id')
    )
    op.create_table('zotero_attachments',
    sa.Column('zotero_attachment_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('zotero_item_state_id', sa.Integer(), nullable=False),
    sa.Column('library_id', sa.Integer(), nullable=False),
    sa.Column('item_key', sa.Text(), nullable=False),
    sa.Column('zotero_item_id', sa.Integer(), nullable=True),
    sa.Column('parent_item_id', sa.Integer(), nullable=True),
    sa.Column('link_mode', sa.Integer(), nullable=True),
    sa.Column('link_mode_name', sa.Text(), nullable=True),
    sa.Column('content_type', sa.Text(), nullable=True),
    sa.Column('stored_path', sa.Text(), nullable=True),
    sa.Column('resolved_path', sa.Text(), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('local_exists', sa.Boolean(), nullable=True),
    sa.Column('storage_hash', sa.Text(), nullable=True),
    sa.Column('storage_mod_time', sa.Integer(), nullable=True),
    sa.Column('present_in_last_scan', sa.Boolean(), nullable=False),
    sa.Column('last_seen_run_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['last_seen_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['zotero_item_state_id'], ['zotero_item_state.zotero_item_state_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('zotero_attachment_id'),
    sa.UniqueConstraint('library_id', 'item_key', name='uq_zotero_attachments_identity')
    )
    op.create_table('paper_documents',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('zotero_attachment_id', sa.Integer(), nullable=False),
    sa.Column('content_type', sa.Text(), nullable=True),
    sa.Column('local_path', sa.Text(), nullable=True),
    sa.Column('availability_status', sa.Text(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('file_mtime_ns', sa.Integer(), nullable=True),
    sa.Column('zotero_storage_hash', sa.Text(), nullable=True),
    sa.Column('document_change_key', sa.Text(), nullable=True),
    sa.Column('present_in_last_scan', sa.Boolean(), nullable=False),
    sa.Column('first_seen_run_id', sa.Integer(), nullable=False),
    sa.Column('last_seen_run_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['first_seen_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['last_seen_run_id'], ['zotero_scan_runs.scan_run_id'], ),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['zotero_attachment_id'], ['zotero_attachments.zotero_attachment_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('document_id'),
    sa.UniqueConstraint('zotero_attachment_id', name='uq_document_attachment')
    )
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.create_index("ix_papers_doi", ["doi"], unique=False)
        batch_op.create_index("ix_papers_publication_year", ["publication_year"], unique=False)
        batch_op.create_index("ix_papers_title", ["title"], unique=False)
    with op.batch_alter_table("zotero_item_state", schema=None) as batch_op:
        batch_op.create_index("ix_zotero_item_state_last_seen_run_id", ["last_seen_run_id"], unique=False)
    with op.batch_alter_table("paper_creator_mentions", schema=None) as batch_op:
        batch_op.create_index("ix_mentions_paper_order", ["paper_id", "order_index"], unique=False)
    with op.batch_alter_table("paper_documents", schema=None) as batch_op:
        batch_op.create_index("ix_paper_documents_change_key", ["document_change_key"], unique=False)
        batch_op.create_index("ix_paper_documents_paper_id", ["paper_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("paper_documents", schema=None) as batch_op:
        batch_op.drop_index("ix_paper_documents_paper_id")
        batch_op.drop_index("ix_paper_documents_change_key")
    with op.batch_alter_table("paper_creator_mentions", schema=None) as batch_op:
        batch_op.drop_index("ix_mentions_paper_order")
    with op.batch_alter_table("zotero_item_state", schema=None) as batch_op:
        batch_op.drop_index("ix_zotero_item_state_last_seen_run_id")
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_index("ix_papers_title")
        batch_op.drop_index("ix_papers_publication_year")
        batch_op.drop_index("ix_papers_doi")
    op.drop_table('paper_documents')
    op.drop_table('zotero_attachments')
    op.drop_table('zotero_item_collections')
    op.drop_table('zotero_item_tags')
    op.drop_table('paper_creator_mentions')
    op.drop_table('zotero_item_versions')
    op.drop_table('zotero_item_state')
    op.drop_table('papers')
    op.drop_table('zotero_scan_runs')
