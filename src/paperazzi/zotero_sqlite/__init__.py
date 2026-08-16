"""Read-only Zotero SQLite access utilities."""

# Python 3.14 removed the deprecated sqlite3.version attribute.  The Phase-1
# probe records that historical diagnostic field but otherwise only needs
# sqlite3.sqlite_version.  Keep the probe runnable on 3.10-3.14 without adding
# a version-specific branch throughout the reconnaissance code.
import sqlite3 as _sqlite3

if not hasattr(_sqlite3, "version"):
    _sqlite3.version = "stdlib-attribute-removed"  # type: ignore[attr-defined]
