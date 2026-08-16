from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.ingest.models import CanonicalZoteroItem


class CanonicalHashTests(unittest.TestCase):
    def make_item(self) -> CanonicalZoteroItem:
        return CanonicalZoteroItem(
            library_id=1,
            item_id=100,
            item_key="ABCDEFGH",
            item_type="journalArticle",
            zotero_version=10,
            synced=1,
            date_added="2026-01-01",
            date_modified="2026-01-02",
            client_date_modified="2026-01-02",
            deleted=False,
            fields={"title": "A paper", "DOI": "10.1000/test"},
        )

    def test_bookkeeping_changes_do_not_change_content_hash(self) -> None:
        item = self.make_item()
        bookkeeping_only = replace(
            item,
            item_id=999,
            zotero_version=999,
            synced=0,
            date_added="2030-01-01",
            date_modified="2030-01-02",
            client_date_modified="2030-01-02",
            deleted=True,
        )
        self.assertEqual(item.content_hash(), bookkeeping_only.content_hash())

    def test_semantic_field_change_changes_content_hash(self) -> None:
        item = self.make_item()
        changed = replace(item, fields={"title": "A different paper", "DOI": "10.1000/test"})
        self.assertNotEqual(item.content_hash(), changed.content_hash())


if __name__ == "__main__":
    unittest.main()
