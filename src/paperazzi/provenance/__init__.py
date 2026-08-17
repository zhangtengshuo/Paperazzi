"""Provenance, document-role, and retraction support."""

from .models import DocumentRole, RetractionEvent, RetractionImpact
from .service import (
    classify_document_role,
    effective_document_role,
    retract_document_derivations,
    retract_extraction_attempt,
    select_primary_document,
    set_document_role,
)

__all__ = [
    "DocumentRole",
    "RetractionEvent",
    "RetractionImpact",
    "classify_document_role",
    "effective_document_role",
    "retract_document_derivations",
    "retract_extraction_attempt",
    "select_primary_document",
    "set_document_role",
]
