"""Phase 4 tests for NOT_SAME_PERSON, locks and co-occurrence merge guards."""

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
from paperazzi.identity.models import Author, AuthorIdentityMembership  # noqa: E402
from paperazzi.identity.operations import (  # noqa: E402
    mark_not_same_person,
    set_identity_lock,
    unlink_mention,
)
from paperazzi.identity.service import (  # noqa: E402
    IdentityResolutionError,
    bootstrap_author_identities,
    merge_authors,
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
        fields={"title": f"Paper {key}"},
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


class Phase4IdentityGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "guards.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def scan(self, items):
        result = persist_zotero_scan(
            self.sf,
            items,
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED", result.error)

    def test_not_same_person_survives_future_bootstrap(self) -> None:
        self.scan([
            item("A", 1, [(10, "Alex", "Wang")]),
            item("B", 2, [(20, "Alex", "Wang")]),
        ])
        with self.sf() as session:
            bootstrap_author_identities(session)
            first_mention, second_mention = (
                session.query(PaperCreatorMention)
                .order_by(PaperCreatorMention.paper_id)
                .all()
            )
            first_author_id = (
                session.query(AuthorIdentityMembership.author_id)
                .filter_by(
                    creator_mention_id=first_mention.creator_mention_id,
                    status="ACCEPTED",
                )
                .scalar()
            )
            mark_not_same_person(
                session,
                second_mention.creator_mention_id,
                first_author_id,
                actor="MANUAL",
            )
            session.commit()

            counts = bootstrap_author_identities(session)
            session.commit()
            accepted = (
                session.query(AuthorIdentityMembership)
                .filter_by(
                    creator_mention_id=second_mention.creator_mention_id,
                    status="ACCEPTED",
                )
                .one()
            )
            self.assertNotEqual(accepted.author_id, first_author_id)
            self.assertGreaterEqual(counts["not_same_blocked"], 1)
            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(
                    creator_mention_id=second_mention.creator_mention_id,
                    author_id=first_author_id,
                    status="CANDIDATE",
                )
                .count(),
                0,
            )

    def test_lock_requires_explicit_unlock_even_for_manual_unlink(self) -> None:
        self.scan([item("A", 1, [(10, "Alice", "Smith")])])
        with self.sf() as session:
            bootstrap_author_identities(session)
            mention = session.query(PaperCreatorMention).one()
            author = session.query(Author).one()
            set_identity_lock(session, author.author_id, True, actor="MANUAL")
            with self.assertRaises(IdentityResolutionError):
                unlink_mention(session, mention.creator_mention_id, actor="MANUAL")
            set_identity_lock(session, author.author_id, False, actor="MANUAL")
            unlink_mention(session, mention.creator_mention_id, actor="MANUAL")
            session.commit()
            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
                .count(),
                0,
            )

    def test_authors_cooccurring_on_same_paper_cannot_merge(self) -> None:
        self.scan([
            item(
                "A",
                1,
                [(10, "Alex", "Wang"), (20, "Alex", "Wang")],
            )
        ])
        with self.sf() as session:
            bootstrap_author_identities(session)
            authors = session.query(Author).all()
            self.assertEqual(len(authors), 2)
            with self.assertRaises(IdentityResolutionError):
                merge_authors(
                    session,
                    authors[0].author_id,
                    authors[1].author_id,
                    actor="MANUAL",
                )


if __name__ == "__main__":
    unittest.main()
