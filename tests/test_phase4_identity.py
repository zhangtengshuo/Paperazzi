"""Phase 4A/4B synthetic tests for identity persistence and conservative resolution."""

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
from paperazzi.database.models import PaperCreatorMention  # noqa: E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.identity.models import (  # noqa: E402
    Author,
    AuthorIdentityDecision,
    AuthorIdentityMembership,
    Authorship,
    ResolutionReviewQueue,
)
from paperazzi.identity.normalization import name_features, normalize_search_text  # noqa: E402
from paperazzi.identity.service import (  # noqa: E402
    IdentityResolutionError,
    bootstrap_author_identities,
    merge_authors,
    new_author_id,
    split_mention,
)
from paperazzi.ingest.models import CanonicalCreator, CanonicalZoteroItem  # noqa: E402


def alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def item(key: str, item_id: int, creators: list[tuple[int, str, str]]) -> CanonicalZoteroItem:
    return CanonicalZoteroItem(
        library_id=1,
        item_id=item_id,
        item_key=key,
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": f"Paper {key}", "date": "2020"},
        creators=tuple(
            CanonicalCreator(
                creator_id=creator_id,
                creator_type="author",
                order_index=index,
                first_name=first,
                last_name=last,
            )
            for index, (creator_id, first, last) in enumerate(creators)
        ),
        collections=(),
        tags=(),
        attachments=(),
    )


class Phase4IdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "phase4.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def scan(self, items: list[CanonicalZoteroItem]) -> None:
        result = persist_zotero_scan(
            self.sf,
            items,
            {"run_token": "identity-scan", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED", result.error)

    def test_phase4_schema_and_foreign_keys(self) -> None:
        expected = {
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
        with self.engine.connect() as conn:
            self.assertTrue(expected.issubset(set(sa.inspect(conn).get_table_names())))
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall(), [])

    def test_normalization_is_search_only_and_preserves_raw_name(self) -> None:
        features = name_features("  Élodie ", "O’Connor", None)
        self.assertEqual(features.raw_name, "Élodie O’Connor")
        self.assertEqual(features.normalized_name, "élodie o connor")
        self.assertEqual(features.search_form, "elodie o connor")
        self.assertEqual(normalize_search_text("  García   Márquez "), "garcia marquez")
        self.assertEqual(features.initials, "é")

    def test_ulid_ids_are_sortable_length_and_unique(self) -> None:
        left = new_author_id(timestamp_ms=1000)
        right = new_author_id(timestamp_ms=1001)
        self.assertEqual(len(left), 26)
        self.assertEqual(len(right), 26)
        self.assertLess(left, right)
        self.assertNotEqual(left, right)

    def test_unique_names_create_accepted_identities_and_authorships(self) -> None:
        self.scan([
            item("A", 1, [(10, "Alice", "Smith")]),
            item("B", 2, [(20, "Bob", "Jones")]),
        ])
        with self.sf() as session:
            counts = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(counts["created"], 2)
            self.assertEqual(session.query(Author).count(), 2)
            self.assertEqual(
                session.query(AuthorIdentityMembership).filter_by(status="ACCEPTED").count(), 2
            )
            self.assertEqual(session.query(Authorship).filter_by(status="ACTIVE").count(), 2)
            self.assertEqual(session.query(Authorship).filter_by(is_first_author=True).count(), 2)

    def test_name_only_never_auto_merges(self) -> None:
        self.scan([
            item("A", 1, [(10, "Alex", "Wang")]),
            item("B", 2, [(20, "Alex", "Wang")]),
        ])
        with self.sf() as session:
            counts = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(counts["created"], 1)
            self.assertEqual(counts["candidate"], 1)
            self.assertEqual(
                session.query(AuthorIdentityMembership).filter_by(status="ACCEPTED").count(), 1
            )
            self.assertEqual(
                session.query(AuthorIdentityMembership).filter_by(status="CANDIDATE").count(), 1
            )
            self.assertEqual(
                session.query(ResolutionReviewQueue)
                .filter_by(queue_type="AMBIGUOUS_AUTHOR_IDENTITY", status="OPEN")
                .count(),
                1,
            )

    def test_same_name_on_same_paper_is_forced_apart(self) -> None:
        self.scan([item("A", 1, [(10, "Alex", "Wang"), (20, "Alex", "Wang")])])
        with self.sf() as session:
            counts = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(counts["created"], 2)
            self.assertEqual(session.query(Author).count(), 2)
            self.assertEqual(
                session.query(AuthorIdentityMembership).filter_by(status="ACCEPTED").count(), 2
            )

    def test_merge_then_split_preserves_decision_history(self) -> None:
        self.scan([
            item("A", 1, [(10, "Alice", "Smith")]),
            item("B", 2, [(20, "Bob", "Jones")]),
        ])
        with self.sf() as session:
            bootstrap_author_identities(session)
            authors = session.query(Author).order_by(Author.preferred_name).all()
            source, target = authors[0], authors[1]
            source_mention_id = (
                session.query(AuthorIdentityMembership.creator_mention_id)
                .filter_by(author_id=source.author_id, status="ACCEPTED")
                .scalar()
            )
            merge_authors(session, source.author_id, target.author_id, actor="MANUAL")
            session.flush()
            self.assertEqual(source.status, "MERGED")
            accepted = (
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=source_mention_id, status="ACCEPTED")
                .one()
            )
            self.assertEqual(accepted.author_id, target.author_id)

            new_author, _decision = split_mention(session, source_mention_id, actor="MANUAL")
            session.commit()
            self.assertNotEqual(new_author.author_id, target.author_id)
            accepted = (
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=source_mention_id, status="ACCEPTED")
                .one()
            )
            self.assertEqual(accepted.author_id, new_author.author_id)
            operations = {
                row.operation for row in session.query(AuthorIdentityDecision).all()
            }
            self.assertIn("MERGE_IDENTITY", operations)
            self.assertIn("SPLIT_IDENTITY", operations)
            self.assertGreaterEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=source_mention_id, status="SUPERSEDED")
                .count(),
                2,
            )

    def test_locked_identity_blocks_automatic_merge(self) -> None:
        self.scan([
            item("A", 1, [(10, "Alice", "Smith")]),
            item("B", 2, [(20, "Bob", "Jones")]),
        ])
        with self.sf() as session:
            bootstrap_author_identities(session)
            source, target = session.query(Author).all()
            source.locked = True
            with self.assertRaises(IdentityResolutionError):
                merge_authors(
                    session, source.author_id, target.author_id, actor="DETERMINISTIC"
                )

    def test_database_rejects_two_accepted_memberships_for_one_mention(self) -> None:
        self.scan([item("A", 1, [(10, "Alice", "Smith")])])
        with self.sf() as session:
            bootstrap_author_identities(session)
            mention = session.query(PaperCreatorMention).one()
            other = Author(
                author_id=new_author_id(),
                preferred_name="Other Alice",
                normalized_name="other alice",
                status="ACTIVE",
                locked=False,
            )
            session.add(other)
            session.flush()
            session.add(
                AuthorIdentityMembership(
                    creator_mention_id=mention.creator_mention_id,
                    author_id=other.author_id,
                    status="ACCEPTED",
                    resolver="test",
                )
            )
            with self.assertRaises(sa.exc.IntegrityError):
                session.flush()


if __name__ == "__main__":
    unittest.main()
