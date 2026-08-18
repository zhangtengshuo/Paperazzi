"""Phase 4/5 migration gates for identity, provenance, and retraction schema."""

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
    "creator_mention_role_evidence",
    "reference_match_evidence",
    "resolution_review_queue",
}
PROVENANCE_TABLES = {"document_roles", "retraction_events", "retraction_impacts"}
WOS_TABLES = {"paper_wos_links", "paper_wos_match_state"}
MIGRATION_HEAD = "0010_paper_wos_match_state"


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

    def test_fresh_upgrade_reaches_current_head_and_has_phase4_wos_schema(self) -> None:
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1800:])
        current = alembic("current", db_path=self.db)
        self.assertEqual(current.returncode, 0, current.stderr[-800:])
        self.assertIn(MIGRATION_HEAD, current.stdout)

        engine = create_paperazzi_engine(self.db)
        with engine.begin() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertTrue(PHASE4_TABLES.issubset(tables), PHASE4_TABLES - tables)
            self.assertTrue(PROVENANCE_TABLES.issubset(tables), PROVENANCE_TABLES - tables)
            self.assertTrue(WOS_TABLES.issubset(tables), WOS_TABLES - tables)
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
            self.assertIn("ix_retraction_events_root", indexes)
            self.assertIn("uq_resolution_review_open_subject", indexes)
            # The new dedicated queue type must be representable by the actual DB CHECK,
            # not just by Python-level validation.
            conn.exec_driver_sql(
                "INSERT INTO resolution_review_queue "
                "(queue_type,subject_type,subject_id,candidate_id,priority,status,reason_code,payload_json,created_at) "
                "VALUES ('SIMILAR_AUTHOR_IDENTITY','author','A','B',70,'OPEN','TEST','{}',CURRENT_TIMESTAMP)"
            )
            count = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM resolution_review_queue WHERE queue_type='SIMILAR_AUTHOR_IDENTITY'"
            ).scalar_one()
            self.assertEqual(count, 1)
        engine.dispose()

    def test_downgrade_to_0006_discards_only_reproducible_similar_review_rows(self) -> None:
        self.assertEqual(alembic("upgrade", "head", db_path=self.db).returncode, 0)
        engine = create_paperazzi_engine(self.db)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO resolution_review_queue "
                "(queue_type,subject_type,subject_id,candidate_id,priority,status,reason_code,payload_json,created_at) "
                "VALUES ('SIMILAR_AUTHOR_IDENTITY','author','A','B',70,'OPEN','TEST','{}',CURRENT_TIMESTAMP)"
            )
            conn.exec_driver_sql(
                "INSERT INTO resolution_review_queue "
                "(queue_type,subject_type,subject_id,candidate_id,priority,status,reason_code,payload_json,created_at) "
                "VALUES ('IDENTITY_CONFLICT','author','C','D',70,'OPEN','TEST','{}',CURRENT_TIMESTAMP)"
            )
        engine.dispose()

        down = alembic("downgrade", "0006_document_roles_retractions", db_path=self.db)
        self.assertEqual(down.returncode, 0, down.stderr[-1800:])
        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            self.assertEqual(
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM resolution_review_queue WHERE queue_type='SIMILAR_AUTHOR_IDENTITY'"
                ).scalar_one(),
                0,
            )
            self.assertEqual(
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM resolution_review_queue WHERE queue_type='IDENTITY_CONFLICT'"
                ).scalar_one(),
                1,
            )
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
        engine.dispose()
        up = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(up.returncode, 0, up.stderr[-1800:])

    def test_downgrade_to_phase3_then_upgrade_head_roundtrip(self) -> None:
        self.assertEqual(alembic("upgrade", "head", db_path=self.db).returncode, 0)
        down = alembic("downgrade", "0003_extraction_reviews", db_path=self.db)
        self.assertEqual(down.returncode, 0, down.stderr[-1800:])
        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertTrue(PHASE4_TABLES.isdisjoint(tables))
            self.assertTrue(PROVENANCE_TABLES.isdisjoint(tables))
            self.assertIn("document_extraction_reviews", tables)
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
        engine.dispose()

        up = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(up.returncode, 0, up.stderr[-1800:])
        engine = create_paperazzi_engine(self.db)
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            self.assertTrue(PHASE4_TABLES.issubset(tables))
            self.assertTrue(PROVENANCE_TABLES.issubset(tables))
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])
        engine.dispose()

    def test_second_upgrade_is_noop(self) -> None:
        self.assertEqual(alembic("upgrade", "head", db_path=self.db).returncode, 0)
        second = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(second.returncode, 0, second.stderr[-800:])
        current = alembic("current", db_path=self.db)
        self.assertIn(MIGRATION_HEAD, current.stdout)


if __name__ == "__main__":
    unittest.main()
