"""Provenance, document-role, and retraction support.

Keep this package initializer lightweight.  ``paperazzi.provenance.models`` is imported
by Alembic while the ORM metadata is being registered, so importing service modules
here would create a cycle through ``paperazzi.identity``.  Service exports remain
available lazily for compatibility without executing them during package import.
"""

from .models import DocumentRole, RetractionEvent, RetractionImpact

_SERVICE_EXPORTS = {
    "classify_document_role",
    "effective_document_role",
    "retract_document_derivations",
    "retract_extraction_attempt",
    "select_primary_document",
    "set_document_role",
}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DocumentRole",
    "RetractionEvent",
    "RetractionImpact",
    *_SERVICE_EXPORTS,
]
