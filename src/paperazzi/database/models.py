"""Phase 3 ORM models — normative per docs/architecture/PERSISTENCE_MODEL.md.

Migration 0001 (zotero persistence): zotero_scan_runs, papers, zotero_item_state,
zotero_item_versions, paper_creator_mentions, zotero_item_tags,
zotero_item_collections, zotero_attachments, paper_documents.

Migration 0002 (document evidence/references): document_extraction_runs,
document_extraction_attempts, document_evidence_spans, paper_reference_sections,
paper_references, paper_reference_identifiers, paper_reference_matches,
plus paper_documents.current_extraction_run_id.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class ZoteroScanRun(Base):
    __tablename__ = "zotero_scan_runs"

    scan_run_id: Mapped[int] = mapped_column(primary_key=True)
    run_token: Mapped[str] = mapped_column(sa.Text, unique=True)
    status: Mapped[str] = mapped_column(
        sa.Text, sa.CheckConstraint("status IN ('STARTED','COMPLETED','FAILED')")
    )
    source_db_path: Mapped[str] = mapped_column(sa.Text)
    source_db_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source_db_mtime_ns: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    adapter_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    userdata_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    global_schema_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    started_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    completed_at: Mapped[Any] = mapped_column(sa.DateTime(), nullable=True)
    item_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    new_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    modified_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    unchanged_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    removed_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    restored_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    bibliographic_corpus_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical_corpus_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        sa.Index("ix_papers_doi", "doi"),
        sa.Index("ix_papers_title", "title"),
        sa.Index("ix_papers_publication_year", "publication_year"),
    )

    paper_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    publication_date_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    venue: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    item_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    active_in_zotero: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class ZoteroItemState(Base):
    __tablename__ = "zotero_item_state"
    __table_args__ = (
        sa.UniqueConstraint("library_id", "item_key", name="uq_zotero_item_state_identity"),
        sa.Index("ix_zotero_item_state_last_seen_run_id", "last_seen_run_id"),
    )

    zotero_item_state_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    library_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    zotero_item_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    item_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    zotero_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    date_added: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    date_modified: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    client_date_modified: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    present_in_last_scan: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    first_seen_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    last_seen_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    bibliographic_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    organization_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attachment_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical_payload_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class ZoteroItemVersion(Base):
    __tablename__ = "zotero_item_versions"
    __table_args__ = (
        sa.UniqueConstraint("zotero_item_state_id", "scan_run_id", name="uq_item_version_scan"),
        sa.CheckConstraint("change_type IN ('NEW','MODIFIED','REMOVED','RESTORED')"),
    )

    zotero_item_version_id: Mapped[int] = mapped_column(primary_key=True)
    zotero_item_state_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_item_state.zotero_item_state_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scan_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    change_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    changed_dimensions_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    bibliographic_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    organization_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attachment_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical_payload_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class PaperCreatorMention(Base):
    __tablename__ = "paper_creator_mentions"
    __table_args__ = (sa.Index("ix_mentions_paper_order", "paper_id", "order_index"),)

    creator_mention_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    zotero_item_state_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_item_state.zotero_item_state_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_creator_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    creator_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    order_index: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    first_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    field_mode: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    display_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class ZoteroItemTag(Base):
    __tablename__ = "zotero_item_tags"

    zotero_item_tag_id: Mapped[int] = mapped_column(primary_key=True)
    zotero_item_state_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_item_state.zotero_item_state_id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    tag_type: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class ZoteroItemCollection(Base):
    __tablename__ = "zotero_item_collections"

    zotero_item_collection_id: Mapped[int] = mapped_column(primary_key=True)
    zotero_item_state_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_item_state.zotero_item_state_id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    collection_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parent_collection_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    parent_collection_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    order_index: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class ZoteroAttachment(Base):
    __tablename__ = "zotero_attachments"
    __table_args__ = (
        sa.UniqueConstraint("library_id", "item_key", name="uq_zotero_attachments_identity"),
    )

    zotero_attachment_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    zotero_item_state_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_item_state.zotero_item_state_id", ondelete="RESTRICT"),
        nullable=False,
    )
    library_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    zotero_item_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    parent_item_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    link_mode: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    link_mode_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    stored_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resolved_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    local_exists: Mapped[bool | None] = mapped_column(sa.Boolean(), nullable=True)
    storage_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    storage_mod_time: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    present_in_last_scan: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    last_seen_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class PaperDocument(Base):
    __tablename__ = "paper_documents"
    __table_args__ = (
        sa.UniqueConstraint("zotero_attachment_id", name="uq_document_attachment"),
        sa.Index("ix_paper_documents_paper_id", "paper_id"),
        sa.Index("ix_paper_documents_change_key", "document_change_key"),
    )

    document_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    zotero_attachment_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_attachments.zotero_attachment_id", ondelete="RESTRICT"),
        nullable=False,
    )
    content_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    availability_status: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "availability_status IN "
            "('PDF_AVAILABLE','PDF_RECORD_ONLY','UNRESOLVED_PATH','FILE_UNAVAILABLE')"
        ),
        nullable=True,
    )
    file_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    file_mtime_ns: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    zotero_storage_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    document_change_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    present_in_last_scan: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    first_seen_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    last_seen_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("zotero_scan_runs.scan_run_id"), nullable=False
    )
    current_extraction_run_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    updated_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow, onupdate=utcnow)


class DocumentExtractionRun(Base):
    __tablename__ = "document_extraction_runs"
    __table_args__ = (
        sa.Index("ix_extraction_runs_document_started", "document_id", "started_at"),
        sa.CheckConstraint(
            "trigger IN ('FIRST_AVAILABLE','FILE_CHANGED','EXTRACTOR_CHANGED',"
            "'PROMPT_CHANGED','MANUAL_REBUILD')"
        ),
        sa.CheckConstraint("status IN ('STARTED','COMPLETED','FAILED')"),
    )

    extraction_run_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    document_change_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    extractor_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    completed_at: Mapped[Any] = mapped_column(sa.DateTime(), nullable=True)
    final_status: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "final_status IN ('PASS','ACCEPT_PARTIAL','UNRESOLVED','NEEDS_OCR','FAILED') "
            "OR final_status IS NULL"
        ),
        nullable=True,
    )
    accepted_attempt_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class DocumentExtractionAttempt(Base):
    __tablename__ = "document_extraction_attempts"
    __table_args__ = (
        sa.UniqueConstraint("extraction_run_id", "attempt_number", name="uq_attempt_number"),
        sa.CheckConstraint("attempt_number BETWEEN 1 AND 3"),
        sa.CheckConstraint(
            "actor IN ('DETERMINISTIC','LOCAL_AI_CONTROLLED','OCR')"
        ),
        sa.CheckConstraint(
            "decision IN ('PASS','ACCEPT_PARTIAL','RETRY','UNRESOLVED','NEEDS_OCR')"
        ),
    )

    attempt_id: Mapped[int] = mapped_column(primary_key=True)
    extraction_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("document_extraction_runs.extraction_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    actor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    strategy: Mapped[str] = mapped_column(sa.Text, nullable=False)
    strategy_parameters_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    backend: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    backend_version: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    text_source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    text_channel: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    channels_evaluated_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decision: Mapped[str] = mapped_column(sa.Text, nullable=False)
    problem_codes_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    section_confidence: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    segmentation_confidence: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    entry_text_quality: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    front_matter_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reference_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    quality_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    runtime_artifact_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
    completed_at: Mapped[Any] = mapped_column(sa.DateTime(), nullable=True)


class DocumentEvidenceSpan(Base):
    __tablename__ = "document_evidence_spans"
    __table_args__ = (
        sa.Index("ix_evidence_document_kind", "document_id", "kind"),
        sa.CheckConstraint(
            "acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"
        ),
    )

    evidence_span_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[int] = mapped_column(
        sa.ForeignKey("document_extraction_attempts.attempt_id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    page_start: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    page_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    bbox_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    text_source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    text_channel: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    acceptance_status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CANDIDATE")
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class PaperReferenceSection(Base):
    __tablename__ = "paper_reference_sections"
    __table_args__ = (
        sa.Index("ix_ref_sections_document_status", "document_id", "acceptance_status"),
        sa.CheckConstraint(
            "acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"
        ),
    )

    reference_section_id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[int] = mapped_column(
        sa.ForeignKey("document_extraction_attempts.attempt_id", ondelete="RESTRICT"),
        nullable=False,
    )
    heading: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_explicit_heading: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    start_page: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    end_page: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    parse_method: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    section_confidence: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    segmentation_confidence: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    entry_text_quality: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    text_source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    text_channel: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    acceptance_status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CANDIDATE")
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class PaperReference(Base):
    __tablename__ = "paper_references"
    __table_args__ = (
        sa.UniqueConstraint("reference_section_id", "ordinal", name="uq_ref_section_ordinal"),
        sa.CheckConstraint(
            "acceptance_status IN ('CANDIDATE','ACCEPTED','REJECTED','SUPERSEDED')"
        ),
        sa.Index("ix_references_citing_paper", "citing_paper_id"),
    )

    reference_id: Mapped[int] = mapped_column(primary_key=True)
    citing_paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    reference_section_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_reference_sections.reference_section_id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    originating_attempt_id: Mapped[int] = mapped_column(
        sa.ForeignKey("document_extraction_attempts.attempt_id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    acceptance_status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CANDIDATE")
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class PaperReferenceIdentifier(Base):
    __tablename__ = "paper_reference_identifiers"
    __table_args__ = (
        sa.UniqueConstraint(
            "reference_id", "identifier_type", "normalized_value",
            name="uq_reference_identifier",
        ),
        sa.Index("ix_ref_identifiers_type_value", "identifier_type", "normalized_value"),
    )

    reference_identifier_id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_references.reference_id", ondelete="CASCADE"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    identifier_value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    extractor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)


class PaperReferenceMatch(Base):
    """Reserved for Phase 4 — created empty, never populated in Phase 3."""

    __tablename__ = "paper_reference_matches"
    __table_args__ = (
        sa.Index("ix_ref_matches_reference_status", "reference_id", "status"),
        sa.CheckConstraint("status IN ('CANDIDATE','ACCEPTED','REJECTED')"),
    )

    reference_match_id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(
        sa.ForeignKey("paper_references.reference_id", ondelete="CASCADE"), nullable=False
    )
    cited_paper_id: Mapped[int] = mapped_column(
        sa.ForeignKey("papers.paper_id", ondelete="RESTRICT"), nullable=False
    )
    match_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    match_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CANDIDATE")
    resolver: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(sa.DateTime(), default=utcnow)
