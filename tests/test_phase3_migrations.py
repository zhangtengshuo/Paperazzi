"""Phase 3A gate tests — migrations, engine pragmas, constraints."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402


EXPECTED_TABLES = {
    "zotero_scan_runs", "papers", "zotero_item_state", "zotero_item_versions",
    "paper_creator_mentions", "zotero_item_tags", "zotero_item_collections",
    "zotero_attachments", "paper_documents",
    "document_extraction_runs", "document_extraction_attempts",
    "document_evidence_spans", "paper_reference_sections", "paper_references",
    "paper_reference_identifiers", "paper_reference_matches",
}

EXPECTED_INDEXES = {
    "ix_papers_doi", "ix_papers_title", "ix_papers_publication_year",
    "ix_zotero_item_state_last_seen_run_id", "ix_mentions_paper_order",
    "ix_paper_documents_paper_id", "ix_paper_documents_change_key",
    "ix_extraction_runs_document_started",
    "ix_evidence_document_kind", "ix_ref_sections_document_status",
    "ix_references_citing_paper", "ix_ref_identifiers_type_value",
    "ix_ref_matches_reference_status",
}


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )


class Phase3MigrationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "gate.sqlite3"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_upgrade_to_head_creates_full_schema(self) -> None:
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])

        engine = create_paperazzi_engine(self.db)
        self.addCleanup(engine.dispose)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            all_indexes = set()
            for t in EXPECTED_TABLES:
                for ix in sa.inspect(conn).get_indexes(t):
                    all_indexes.add(ix["name"])
            self.assertTrue(EXPECTED_TABLES.issubset(tables), tables - EXPECTED_TABLES)
            self.assertTrue(EXPECTED_INDEXES.issubset(all_indexes), EXPECTED_INDEXES - all_indexes)
            self.assertEqual(
                conn.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1
            )
            self.assertEqual(
                conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), []
            )

    def test_second_upgrade_is_noop(self) -> None:
        alembic("upgrade", "head", db_path=self.db)
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Running upgrade", proc.stdout)

    def test_downgrade_upgrade_roundtrip(self) -> None:
        alembic("upgrade", "head", db_path=self.db)
        down = alembic("downgrade", "0001", db_path=self.db)
        self.assertEqual(down.returncode, 0, down.stderr[-500:])
        engine = create_paperazzi_engine(self.db)
        self.addCleanup(engine.dispose)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertNotIn("document_extraction_runs", tables)
            self.assertIn("papers", tables)
        up = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(up.returncode, 0, up.stderr[-500:])

    def test_unique_foreign_and_check_constraints(self) -> None:
        alembic("upgrade", "head", db_path=self.db)
        engine = create_paperazzi_engine(self.db)
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO papers (paper_id, active_in_zotero, created_at, updated_at) "
                "VALUES (1, 1, '2026-08-17', '2026-08-17')"
            )
            conn.exec_driver_sql(
                "INSERT INTO zotero_scan_runs (scan_run_id, run_token, status, "
                "source_db_path, started_at) VALUES (1, 't', 'STARTED', 'x', '2026-08-17')"
            )
            conn.exec_driver_sql(
                "INSERT INTO zotero_item_state (paper_id, library_id, item_key, deleted, "
                "present_in_last_scan, first_seen_run_id, last_seen_run_id, created_at, "
                "updated_at) VALUES (1, 1, 'K', 0, 1, 1, 1, '2026-08-17', '2026-08-17')"
            )
        with self.assertRaises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO zotero_item_state (paper_id, library_id, item_key, deleted, "
                    "present_in_last_scan, first_seen_run_id, last_seen_run_id, created_at, "
                    "updated_at) VALUES (1, 1, 'K', 0, 1, 1, 1, '2026-08-17', '2026-08-17')"
                )
        with self.assertRaises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO paper_creator_mentions (paper_id, zotero_item_state_id, "
                    "order_index, created_at) VALUES (1, 999, 0, '2026-08-17')"
                )
        with self.assertRaises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO document_extraction_attempts (extraction_run_id, "
                    "attempt_number, actor, strategy, text_source, decision, started_at) "
                    "VALUES (1, 4, 'DETERMINISTIC', 's', 't', 'PASS', '2026-08-17')"
                )


if __name__ == "__main__":
    unittest.main()
