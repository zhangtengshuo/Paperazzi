"""Local evidence extraction that is independent of Zotero metadata ingestion."""

from .pdf import (
    EvidenceSpan,
    PdfEvidence,
    ReferenceEntry,
    ReferenceSection,
    extract_dois,
    extract_pdf_evidence,
    find_reference_section,
    segment_reference_entries,
)

__all__ = [
    "EvidenceSpan",
    "PdfEvidence",
    "ReferenceEntry",
    "ReferenceSection",
    "extract_dois",
    "extract_pdf_evidence",
    "find_reference_section",
    "segment_reference_entries",
]
