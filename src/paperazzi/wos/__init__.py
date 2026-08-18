"""Independent Web of Science background corpus support for Paperazzi."""

from .parser import ParsedWosRecord, parse_records
from .store import WosCorpusStore

__all__ = ["ParsedWosRecord", "WosCorpusStore", "parse_records"]
