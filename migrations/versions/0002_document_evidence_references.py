"""Phase 3 migration 0002: document evidence and references

Revision ID: 0002_document_evidence_references
Revises: 0001_zotero_persistence
Create Date: 2026-08-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002_document_evidence_references'
down_revision: Union[str, None] = '0001_zotero_persistence'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('document_extraction_runs',
    sa.Column('extraction_run_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('trigger', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('document_change_key', sa.Text(), nullable=True),
    sa.Column('extractor_version', sa.Text(), nullable=False),
    sa.Column('prompt_version', sa.Text(), nullable=True),
    sa.Column('prompt_hash', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('final_status', sa.Text(), nullable=True),
    sa.Column('accepted_attempt_id', sa.Integer(), nullable=True),
    sa.Column('error_type', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('STARTED','COMPLETED','FAILED')"),
    sa.CheckConstraint("trigger IN ('FIRST_AVAILABLE','FILE_CHANGED','EXTRACTOR_CHANGED','PROMPT_CHANGED','MANUAL_REBUILD')"),
    sa.ForeignKeyConstraint(['document_id'], ['paper_documents.document_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('extraction_run_id')
    )
    op.create_table('document_extraction_attempts',
    sa.Column('attempt_id', sa.Integer(), nullable=False),
    sa.Column('extraction_run_id', sa.Integer(), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=False),
    sa.Column('actor', sa.Text(), nullable=False),
    sa.Column('strategy', sa.Text(), nullable=False),
    sa.Column('strategy_parameters_json', sa.Text(), nullable=True),
    sa.Column('backend', sa.Text(), nullable=True),
    sa.Column('backend_version', sa.Text(), nullable=True),
    sa.Column('text_source', sa.Text(), nullable=False),
    sa.Column('text_channel', sa.Text(), nullable=True),
    sa.Column('channels_evaluated_json', sa.Text(), nullable=True),
    sa.Column('prompt_version', sa.Text(), nullable=True),
    sa.Column('prompt_hash', sa.Text(), nullable=True),
    sa.Column('decision', sa.Text(), nullable=False),
    sa.Column('problem_codes_json', sa.Text(), nullable=True),
    sa.Column('section_confidence', sa.Text(), nullable=True),
    sa.Column('segmentation_confidence', sa.Text(), nullable=True),
    sa.Column('entry_text_quality', sa.Text(), nullable=True),
    sa.Column('front_matter_status', sa.Text(), nullable=True),
    sa.Column('reference_status', sa.Text(), nullable=True),
    sa.Column('output_hash', sa.Text(), nullable=True),
    sa.Column('quality_notes', sa.Text(), nullable=True),
    sa.Column('runtime_artifact_path', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("actor IN ('DETERMINISTIC','LOCAL_AI_CONTROLLED','OCR')"),
    sa.CheckConstraint("decision IN ('PASS','ACCEPT_PARTIAL','RETRY','UNRESOLVED','NEEDS_OCR')"),
    sa.CheckConstraint('attempt_number BETWEEN 1 AND 3'),
    sa.ForeignKeyConstraint(['extraction_run_id'], ['document_extraction_runs.extraction_run_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('attempt_id'),
    sa.UniqueConstraint('extraction_run_id', 'attempt_number', name='uq_attempt_number')
    )
    op.create_table('document_evidence_spans',
    sa.Column('evidence_span_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('attempt_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('page_start', sa.Integer(), nullable=False),
    sa.Column('page_end', sa.Integer(), nullable=True),
    sa.Column('bbox_json', sa.Text(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('raw_text_hash', sa.Text(), nullable=False),
    sa.Column('text_source', sa.Text(), nullable=False),
    sa.Column('text_channel', sa.Text(), nullable=True),
    sa.Column('acceptance_status', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    sa.ForeignKeyConstraint(['attempt_id'], ['document_extraction_attempts.attempt_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['document_id'], ['paper_documents.document_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('evidence_span_id')
    )
    op.create_table('paper_reference_sections',
    sa.Column('reference_section_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('attempt_id', sa.Integer(), nullable=False),
    sa.Column('heading', sa.Text(), nullable=True),
    sa.Column('is_explicit_heading', sa.Boolean(), nullable=False),
    sa.Column('start_page', sa.Integer(), nullable=False),
    sa.Column('end_page', sa.Integer(), nullable=True),
    sa.Column('parse_method', sa.Text(), nullable=True),
    sa.Column('section_confidence', sa.Text(), nullable=True),
    sa.Column('segmentation_confidence', sa.Text(), nullable=True),
    sa.Column('entry_text_quality', sa.Text(), nullable=True),
    sa.Column('text_source', sa.Text(), nullable=False),
    sa.Column('text_channel', sa.Text(), nullable=True),
    sa.Column('acceptance_status', sa.Text(), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('raw_text_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    sa.ForeignKeyConstraint(['attempt_id'], ['document_extraction_attempts.attempt_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['document_id'], ['paper_documents.document_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('reference_section_id')
    )
    op.create_table('paper_references',
    sa.Column('reference_id', sa.Integer(), nullable=False),
    sa.Column('citing_paper_id', sa.Integer(), nullable=False),
    sa.Column('reference_section_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('originating_attempt_id', sa.Integer(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('raw_text_hash', sa.Text(), nullable=False),
    sa.Column('acceptance_status', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"),
    sa.ForeignKeyConstraint(['citing_paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['document_id'], ['paper_documents.document_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['originating_attempt_id'], ['document_extraction_attempts.attempt_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reference_section_id'], ['paper_reference_sections.reference_section_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('reference_id'),
    sa.UniqueConstraint('reference_section_id', 'ordinal', name='uq_ref_section_ordinal')
    )
    op.create_table('paper_reference_identifiers',
    sa.Column('reference_identifier_id', sa.Integer(), nullable=False),
    sa.Column('reference_id', sa.Integer(), nullable=False),
    sa.Column('identifier_type', sa.Text(), nullable=False),
    sa.Column('identifier_value', sa.Text(), nullable=False),
    sa.Column('normalized_value', sa.Text(), nullable=False),
    sa.Column('extractor', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['reference_id'], ['paper_references.reference_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('reference_identifier_id'),
    sa.UniqueConstraint('reference_id', 'identifier_type', 'normalized_value', name='uq_reference_identifier')
    )
    op.create_table('paper_reference_matches',
    sa.Column('reference_match_id', sa.Integer(), nullable=False),
    sa.Column('reference_id', sa.Integer(), nullable=False),
    sa.Column('cited_paper_id', sa.Integer(), nullable=False),
    sa.Column('match_type', sa.Text(), nullable=True),
    sa.Column('match_score', sa.Float(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('resolver', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED')"),
    sa.ForeignKeyConstraint(['cited_paper_id'], ['papers.paper_id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reference_id'], ['paper_references.reference_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('reference_match_id')
    )
    with op.batch_alter_table("document_extraction_runs", schema=None) as batch_op:
        batch_op.create_index("ix_extraction_runs_document_started", ["document_id", "started_at"], unique=False)
    with op.batch_alter_table("document_evidence_spans", schema=None) as batch_op:
        batch_op.create_index("ix_evidence_document_kind", ["document_id", "kind"], unique=False)
    with op.batch_alter_table("paper_reference_sections", schema=None) as batch_op:
        batch_op.create_index("ix_ref_sections_document_status", ["document_id", "acceptance_status"], unique=False)
    with op.batch_alter_table("paper_references", schema=None) as batch_op:
        batch_op.create_index("ix_references_citing_paper", ["citing_paper_id"], unique=False)
    with op.batch_alter_table("paper_reference_identifiers", schema=None) as batch_op:
        batch_op.create_index("ix_ref_identifiers_type_value", ["identifier_type", "normalized_value"], unique=False)
    with op.batch_alter_table("paper_reference_matches", schema=None) as batch_op:
        batch_op.create_index("ix_ref_matches_reference_status", ["reference_id", "status"], unique=False)
    with op.batch_alter_table("paper_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("current_extraction_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_document_current_extraction_run",
            "document_extraction_runs",
            ["current_extraction_run_id"],
            ["extraction_run_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("paper_documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_document_current_extraction_run", type_="foreignkey")
        batch_op.drop_column("current_extraction_run_id")
    with op.batch_alter_table("paper_reference_matches", schema=None) as batch_op:
        batch_op.drop_index("ix_ref_matches_reference_status")
    with op.batch_alter_table("paper_reference_identifiers", schema=None) as batch_op:
        batch_op.drop_index("ix_ref_identifiers_type_value")
    with op.batch_alter_table("paper_references", schema=None) as batch_op:
        batch_op.drop_index("ix_references_citing_paper")
    with op.batch_alter_table("paper_reference_sections", schema=None) as batch_op:
        batch_op.drop_index("ix_ref_sections_document_status")
    with op.batch_alter_table("document_evidence_spans", schema=None) as batch_op:
        batch_op.drop_index("ix_evidence_document_kind")
    with op.batch_alter_table("document_extraction_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_extraction_runs_document_started")
    op.drop_table('paper_reference_matches')
    op.drop_table('paper_reference_identifiers')
    op.drop_table('paper_references')
    op.drop_table('paper_reference_sections')
    op.drop_table('document_evidence_spans')
    op.drop_table('document_extraction_attempts')
    op.drop_table('document_extraction_runs')
