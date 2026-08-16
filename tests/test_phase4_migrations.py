"""Phase 4 migration gates for identity/resolution schema."""

from __future__ import annotations

import os
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

PHASE4_TABLES = {
    "authors",
    "author_name_variants",
    "author_external_ids",
    "author_identity_memberships",
    "author_identity_decisions",
    "author_identity_evidence",
    "authorships",
    "authorship_evidence",
    "reference_match_evidence",
    "resolution_review_queue",
}


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


class Phase4MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "migration.sqlite3"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fresh_upgrade_reaches_0005_and_has_phase4_schema(self) -> None:
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1800:])
        current = alembic("current", db_path=self.db)
        self.assertEqual(current.returncode, 0, current.stderr[-800:])
        self.assertIn("0005_identity_history_constraints", current.stdout)

        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertTrue(PHASE4_TABLES.issubset(tables), PHASE4_TABLES - tables)
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
            indexes = {
                row[0]: row[1]
                for row in conn.exec_driver_sql(
                    "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
                ).fetchall()
            }
            self.assertIn("uq_identity_membership_one_accepted", indexes)
            self.assertIn("WHERE status = 'ACCEPTED'", indexes["uq_identity_membership_one_accepted"])
            self.assertIn("uq_author_external_id_accepted", indexes)
            self.assertIn("WHERE status = 'ACCEPTED'", indexes["uq_author_external_id_accepted"])
            self.assertNotIn("uq_identity_membership_state", indexes)
        engine.dispose()

    def test_downgrade_to_phase3_then_upgrade_head_roundtrip(self) -> None:
        self.assertEqual(alembic("upgrade", "head", db_path=self.db).returncode, 0)
        down = alembic("downgrade", "0003_extraction_reviews", db_path=self.db)
        self.assertEqual(down.returncode, 0, down.stderr[-1800:])
        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertTrue(PHASE4_TABLES.isdisjoint(tables))
            self.assertIn("document_extraction_reviews", tables)
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
        engine.dispose()

        up = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(up.returncode, 0, up.stderr[-1800:])
        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            self.assertTrue(
                PHASE4_TABLES.issubset(set(sa.inspect(conn).get_table_names()))
            )
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
        engine.dispose()

    def test_second_upgrade_is_noop(self) -> None:
        self.assertEqual(alembic("upgrade", "head", db_path=self.db).returncode, 0)
        second = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(second.returncode, 0, second.stderr[-800:])
        current = alembic("current", db_path=self.db)
        self.assertIn("0005_identity_history_constraints", current.stdout)


if __name__ == "__main__":
    unittest.main()
