"""Compatibility surface for the independent Web of Science corpus store.

The implementation lives in :mod:`paperazzi.wos.store_v3`.  Keeping this module as
the stable import path lets existing callers continue to use
``from paperazzi.wos.store import WosCorpusStore`` while schema v3 adds observation
history and non-destructive merge behavior for repeated WoS exports.
"""

from .store_v3 import SCHEMA_SQL, SCHEMA_VERSION, WosCorpusStore

__all__ = ["SCHEMA_SQL", "SCHEMA_VERSION", "WosCorpusStore"]
