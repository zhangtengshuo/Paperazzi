from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.zotero_sqlite.probe import collect_report, create_snapshot, open_readonly


class ZoteroProbeTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> Path:
        db = root / "zotero.sqlite"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE itemTypes (
                itemTypeID INTEGER PRIMARY KEY,
                typeName TEXT NOT NULL
            );
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                itemTypeID INTEGER NOT NULL,
                libraryID INTEGER NOT NULL,
                key TEXT NOT NULL,
                dateAdded TEXT,
                dateModified TEXT
            );
            CREATE TABLE fields (
                fieldID INTEGER PRIMARY KEY,
                fieldName TEXT NOT NULL
            );
            CREATE TABLE itemDataValues (
                valueID INTEGER PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE itemData (
                itemID INTEGER NOT NULL,
                fieldID INTEGER NOT NULL,
                valueID INTEGER NOT NULL
            );
            CREATE TABLE creatorTypes (
                creatorTypeID INTEGER PRIMARY KEY,
                creatorType TEXT NOT NULL
            );
            CREATE TABLE creators (
                creatorID INTEGER PRIMARY KEY,
                firstName TEXT,
                lastName TEXT,
                fieldMode INTEGER
            );
            CREATE TABLE itemCreators (
                itemID INTEGER NOT NULL,
                creatorID INTEGER NOT NULL,
                creatorTypeID INTEGER NOT NULL,
                orderIndex INTEGER NOT NULL
            );
            CREATE TABLE itemAttachments (
                itemID INTEGER PRIMARY KEY,
                parentItemID INTEGER,
                linkMode INTEGER,
                contentType TEXT,
                path TEXT
            );
            CREATE TABLE libraries (
                libraryID INTEGER PRIMARY KEY,
                type TEXT,
                editable INTEGER,
                filesEditable INTEGER
            );
            CREATE TABLE version (
                schema TEXT PRIMARY KEY,
                version INTEGER NOT NULL
            );

            INSERT INTO itemTypes VALUES (1, 'journalArticle');
            INSERT INTO itemTypes VALUES (2, 'attachment');
            INSERT INTO items VALUES (1, 1, 1, 'ARTICLE1', '2026-01-01', '2026-02-01');
            INSERT INTO items VALUES (2, 2, 1, 'ATTACH01', '2026-01-01', '2026-02-01');
            INSERT INTO fields VALUES (1, 'title');
            INSERT INTO itemDataValues VALUES (1, 'Fixture Paper');
            INSERT INTO itemData VALUES (1, 1, 1);
            INSERT INTO creatorTypes VALUES (1, 'author');
            INSERT INTO creators VALUES (1, 'Ada', 'Lovelace', 0);
            INSERT INTO itemCreators VALUES (1, 1, 1, 0);
            INSERT INTO itemAttachments VALUES (2, 1, 0, 'application/pdf', 'storage:paper.pdf');
            INSERT INTO libraries VALUES (1, 'user', 1, 1);
            INSERT INTO version VALUES ('userdata', 123);
            """
        )
        conn.commit()
        conn.close()
        return db

    def test_source_connection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_fixture(Path(tmp))
            conn = open_readonly(db)
            try:
                self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("CREATE TABLE forbidden_write (x INTEGER)")
            finally:
                conn.close()

    def test_snapshot_is_independent_and_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = self.make_fixture(root)
            snapshot = root / "snapshot.sqlite"
            conn = open_readonly(db)
            try:
                create_snapshot(conn, snapshot)
            finally:
                conn.close()

            self.assertTrue(snapshot.is_file())
            snap = open_readonly(snapshot)
            try:
                self.assertEqual(snap.execute("SELECT COUNT(*) FROM items").fetchone()[0], 2)
            finally:
                snap.close()

    def test_probe_extracts_core_structure_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = self.make_fixture(root)
            conn = open_readonly(db)
            try:
                report = collect_report(
                    conn,
                    source_db=db,
                    analysis_db=db,
                    snapshot_created=False,
                    run_label="fixture",
                    quick_check=True,
                    include_content_samples=True,
                    sample_limit=5,
                )
            finally:
                conn.close()

            self.assertEqual(report["pragmas"]["quick_check"], ["ok"])
            self.assertEqual(report["key_object_counts"]["items"], 2)
            self.assertEqual(report["recent_items"][0]["title"], "Fixture Paper")
            self.assertEqual(report["recent_items"][0]["creators"][0]["lastName"], "Lovelace")
            self.assertEqual(report["pdf_samples"][0]["resolution"], "zotero-storage")


if __name__ == "__main__":
    unittest.main()
