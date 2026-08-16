from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.zotero_sqlite.adapters import UnsupportedZoteroSchema
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader, resolve_attachment_path


class ZoteroReaderTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[sqlite3.Connection, Path]:
        db = root / "zotero.sqlite"
        storage = root / "storage" / "ATTACH01"
        storage.mkdir(parents=True)
        (storage / "paper.pdf").write_bytes(b"%PDF-fixture")

        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE itemTypes (
                itemTypeID INTEGER PRIMARY KEY,
                typeName TEXT
            );
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                itemTypeID INT,
                dateAdded TIMESTAMP,
                dateModified TIMESTAMP,
                clientDateModified TIMESTAMP,
                libraryID INT,
                key TEXT,
                version INT,
                synced INT
            );
            CREATE TABLE itemData (
                itemID INT,
                fieldID INT,
                valueID INTEGER
            );
            CREATE TABLE itemDataValues (
                valueID INTEGER PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE fieldsCombined (
                fieldID INTEGER PRIMARY KEY,
                fieldName TEXT
            );
            CREATE TABLE creators (
                creatorID INTEGER PRIMARY KEY,
                firstName TEXT,
                lastName TEXT,
                fieldMode INT
            );
            CREATE TABLE creatorTypes (
                creatorTypeID INTEGER PRIMARY KEY,
                creatorType TEXT
            );
            CREATE TABLE itemCreators (
                itemID INT,
                creatorID INT,
                creatorTypeID INT,
                orderIndex INT
            );
            CREATE TABLE collections (
                collectionID INTEGER PRIMARY KEY,
                collectionName TEXT,
                parentCollectionID INT,
                libraryID INT,
                key TEXT
            );
            CREATE TABLE collectionItems (
                collectionID INT,
                itemID INT,
                orderIndex INT
            );
            CREATE TABLE tags (
                tagID INTEGER PRIMARY KEY,
                name TEXT
            );
            CREATE TABLE itemTags (
                itemID INT,
                tagID INT,
                type INT
            );
            CREATE TABLE itemAttachments (
                itemID INTEGER PRIMARY KEY,
                parentItemID INT,
                linkMode INT,
                contentType TEXT,
                path TEXT,
                syncState INT,
                storageModTime INT,
                storageHash TEXT
            );
            CREATE TABLE deletedItems (
                itemID INTEGER PRIMARY KEY,
                dateDeleted TEXT
            );
            CREATE TABLE libraries (
                libraryID INTEGER PRIMARY KEY,
                type TEXT,
                editable INT,
                filesEditable INT,
                version INT,
                storageVersion INT,
                lastSync INT,
                archived INT,
                isAdmin INT
            );
            CREATE TABLE version (
                schema TEXT PRIMARY KEY,
                version INT
            );

            INSERT INTO itemTypes VALUES (1, 'journalArticle');
            INSERT INTO itemTypes VALUES (2, 'attachment');
            INSERT INTO itemTypes VALUES (3, 'note');

            INSERT INTO items VALUES
                (1, 1, '2026-01-01', '2026-02-01', '2026-02-01', 1, 'SAMEKEY1', 10, 1),
                (2, 2, '2026-01-01', '2026-02-01', '2026-02-01', 1, 'ATTACH01', 4, 1),
                (3, 1, '2026-01-02', '2026-02-02', '2026-02-02', 1, 'DELETED1', 3, 1),
                (4, 1, '2026-01-03', '2026-02-03', '2026-02-03', 2, 'SAMEKEY1', 7, 1),
                (5, 3, '2026-01-04', '2026-02-04', '2026-02-04', 1, 'NOTE0001', 1, 1);

            INSERT INTO fieldsCombined VALUES (1, 'title');
            INSERT INTO fieldsCombined VALUES (2, 'DOI');
            INSERT INTO itemDataValues VALUES (1, 'Fixture Paper');
            INSERT INTO itemDataValues VALUES (2, '10.1000/fixture');
            INSERT INTO itemDataValues VALUES (3, 'Deleted Paper');
            INSERT INTO itemDataValues VALUES (4, 'Group Paper');
            INSERT INTO itemData VALUES (1, 1, 1);
            INSERT INTO itemData VALUES (1, 2, 2);
            INSERT INTO itemData VALUES (3, 1, 3);
            INSERT INTO itemData VALUES (4, 1, 4);

            INSERT INTO creatorTypes VALUES (1, 'author');
            INSERT INTO creators VALUES (1, 'Ada', 'Lovelace', 0);
            INSERT INTO creators VALUES (2, 'Grace', 'Hopper', 0);
            INSERT INTO creators VALUES (3, NULL, 'Fixture Consortium', 1);
            INSERT INTO itemCreators VALUES (1, 1, 1, 0);
            INSERT INTO itemCreators VALUES (1, 2, 1, 1);
            INSERT INTO itemCreators VALUES (4, 3, 1, 0);

            INSERT INTO collections VALUES (10, 'Parent', NULL, 1, 'COLLPAR1');
            INSERT INTO collections VALUES (11, 'Child', 10, 1, 'COLLCHD1');
            INSERT INTO collectionItems VALUES (11, 1, 0);

            INSERT INTO tags VALUES (20, 'quantum chemistry');
            INSERT INTO itemTags VALUES (1, 20, 0);

            INSERT INTO itemAttachments VALUES
                (2, 1, 1, 'application/pdf', 'storage:paper.pdf', 1, 123456, 'abc123');

            INSERT INTO deletedItems VALUES (3, '2026-02-10');

            INSERT INTO libraries VALUES (1, 'user', 1, 1, 100, 100, 0, 0, 0);
            INSERT INTO libraries VALUES (2, 'group', 1, 1, 20, 20, 0, 0, 1);

            INSERT INTO version VALUES ('userdata', 125);
            INSERT INTO version VALUES ('globalSchema', 42);
            """
        )
        conn.commit()
        conn.row_factory = sqlite3.Row
        return conn, root

    def test_reader_maps_fields_creators_collections_tags_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn, data_dir = self.make_fixture(Path(tmp))
            try:
                reader = ZoteroSQLiteReader(conn, data_dir)
                items = reader.read_items()
            finally:
                conn.close()

            self.assertEqual(len(items), 2)
            user_item = next(item for item in items if item.library_id == 1)
            group_item = next(item for item in items if item.library_id == 2)

            self.assertEqual(user_item.title, 'Fixture Paper')
            self.assertEqual(user_item.doi, '10.1000/fixture')
            self.assertEqual([c.display_name for c in user_item.creators], ['Ada Lovelace', 'Grace Hopper'])
            self.assertEqual(user_item.collections[0].collection_key, 'COLLCHD1')
            self.assertEqual(user_item.collections[0].parent_collection_key, 'COLLPAR1')
            self.assertEqual(user_item.tags[0].name, 'quantum chemistry')
            self.assertEqual(user_item.attachments[0].link_mode_name, 'imported_url')
            self.assertTrue(user_item.attachments[0].local_exists)

            # Same Zotero item key is legal in different libraries.
            self.assertEqual(user_item.item_key, group_item.item_key)
            self.assertNotEqual(user_item.zotero_identity, group_item.zotero_identity)
            self.assertEqual(group_item.creators[0].display_name, 'Fixture Consortium')

    def test_deleted_items_are_excluded_by_default_but_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn, data_dir = self.make_fixture(Path(tmp))
            try:
                reader = ZoteroSQLiteReader(conn, data_dir)
                active = reader.read_items()
                with_deleted = reader.read_items(include_deleted=True)
            finally:
                conn.close()

            self.assertEqual(len(active), 2)
            self.assertEqual(len(with_deleted), 3)
            deleted = next(item for item in with_deleted if item.item_key == 'DELETED1')
            self.assertTrue(deleted.deleted)

    def test_content_hash_ignores_sqlite_internal_item_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn, data_dir = self.make_fixture(Path(tmp))
            try:
                item = ZoteroSQLiteReader(conn, data_dir).read_items()[0]
            finally:
                conn.close()

            changed_internal_id = replace(item, item_id=999999)
            self.assertEqual(item.content_hash(), changed_internal_id.content_hash())

    def test_unknown_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn, data_dir = self.make_fixture(Path(tmp))
            conn.execute("UPDATE version SET version=126 WHERE schema='userdata'")
            conn.commit()
            try:
                with self.assertRaises(UnsupportedZoteroSchema):
                    ZoteroSQLiteReader(conn, data_dir)
            finally:
                conn.close()

    def test_linked_base_directory_is_not_guessed(self) -> None:
        path, exists, resolution = resolve_attachment_path(
            zotero_data_dir=Path('/tmp/zotero'),
            item_key='ABCDEFGH',
            link_mode=2,
            stored_path='attachments:paper.pdf',
        )
        self.assertIsNone(path)
        self.assertIsNone(exists)
        self.assertEqual(resolution, 'linked-base-directory-required')


if __name__ == '__main__':
    unittest.main()
