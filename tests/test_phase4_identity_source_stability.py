"""Regression tests for immutable-source Phase 4 identity resolution."""

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
    AuthorIdentityDecision,
    AuthorIdentityMembership,
    Authorship,
)
from paperazzi.identity.service import bootstrap_author_identities  # noqa: E402
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


def paper(
    key: str,
    item_id: int,
    creators: list[tuple[int, str, str, str]],
) -> CanonicalZoteroItem:
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
                creator_type=creator_type,
                order_index=index,
                first_name=first,
                last_name=last,
            )
            for index, (creator_id, creator_type, first, last) in enumerate(creators)
        ),
        collections=(),
        tags=(),
        attachments=(),
    )


def author(creator_id: int, first: str, last: str):
    return (creator_id, "author", first, last)


class Phase4SourceStableIdentityTests(unittest.TestCase):
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
            {"run_token": "source-stable-scan", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED", result.error)

    def cascade_corpus(self) -> list[CanonicalZoteroItem]:
        # Old mutable-graph behavior:
        # P1 seeds Alex with A/B collaborators.
        # P2 (C/D) is initially weak.
        # P3 overlaps P1 via A/B, gets accepted, and then injects C/D into the
        # canonical collaboration neighborhood; P2 becomes accepted only on rerun.
        # The source-stable resolver sees P1+P3 while evaluating P2 on the first run.
        return [
            paper(
                "P1",
                1,
                [
                    author(10, "Alex", "Wang"),
                    author(100, "Alice", "A"),
                    author(101, "Bob", "B"),
                ],
            ),
            paper(
                "P2",
                2,
                [
                    author(10, "Alex", "Wang"),
                    author(102, "Carol", "C"),
                    author(103, "David", "D"),
                ],
            ),
            paper(
                "P3",
                3,
                [
                    author(10, "Alex", "Wang"),
                    author(100, "Alice", "A"),
                    author(101, "Bob", "B"),
                    author(102, "Carol", "C"),
                    author(103, "David", "D"),
                ],
            ),
        ]

    def test_cascade_trap_resolves_on_first_run_and_rerun_is_strictly_idempotent(self) -> None:
        self.scan(self.cascade_corpus())
        with self.sf() as session:
            first = bootstrap_author_identities(session)
            session.commit()
            decisions_after_first = session.query(AuthorIdentityDecision).count()
            memberships_after_first = session.query(AuthorIdentityMembership).count()

            alex_mentions = (
                session.query(PaperCreatorMention)
                .filter_by(source_creator_id=10, creator_type="author")
                .all()
            )
            alex_author_ids = {
                session.query(AuthorIdentityMembership.author_id)
                .filter_by(
                    creator_mention_id=mention.creator_mention_id,
                    status="ACCEPTED",
                )
                .scalar()
                for mention in alex_mentions
            }
            self.assertEqual(len(alex_author_ids), 1)
            self.assertGreaterEqual(first["linked"], 2)

            second = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(second["created"], 0)
            self.assertEqual(second["linked"], 0)
            self.assertEqual(
                session.query(AuthorIdentityDecision).count(), decisions_after_first
            )
            self.assertEqual(
                session.query(AuthorIdentityMembership).count(), memberships_after_first
            )

    def test_logical_partition_is_independent_of_input_item_order(self) -> None:
        # Compare source-creator -> number of accepted canonical IDs rather than ULIDs.
        corpus = self.cascade_corpus()
        self.scan(list(reversed(corpus)))
        with self.sf() as session:
            bootstrap_author_identities(session)
            session.commit()
            alex_author_ids = {
                author_id
                for (author_id,) in (
                    session.query(AuthorIdentityMembership.author_id)
                    .join(
                        PaperCreatorMention,
                        PaperCreatorMention.creator_mention_id
                        == AuthorIdentityMembership.creator_mention_id,
                    )
                    .filter(
                        PaperCreatorMention.source_creator_id == 10,
                        PaperCreatorMention.creator_type == "author",
                        AuthorIdentityMembership.status == "ACCEPTED",
                    )
                    .all()
                )
            }
            self.assertEqual(len(alex_author_ids), 1)

    def test_every_paper_author_is_source_recorded_and_roles_are_additive(self) -> None:
        self.scan([
            paper(
                "ROLE",
                1,
                [
                    author(10, "First", "Author"),
                    author(20, "Middle", "Author"),
                    author(30, "Last", "Author"),
                ],
            )
        ])
        with self.sf() as session:
            counts = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(counts["source_author_mentions"], 3)
            self.assertEqual(
                session.query(PaperCreatorMention).filter_by(creator_type="author").count(),
                3,
            )
            self.assertEqual(session.query(Authorship).filter_by(status="ACTIVE").count(), 3)
            self.assertEqual(
                session.query(Authorship)
                .filter_by(status="ACTIVE", is_first_author=True)
                .count(),
                1,
            )
            self.assertEqual(
                session.query(Authorship)
                .filter_by(status="ACTIVE", is_corresponding_author=True)
                .count(),
                0,
            )

    def test_non_author_creators_remain_source_records_but_are_not_author_identities(self) -> None:
        self.scan([
            paper(
                "CREATOR-TYPES",
                1,
                [
                    author(10, "Alice", "Author"),
                    (99, "editor", "Eve", "Editor"),
                ],
            )
        ])
        with self.sf() as session:
            counts = bootstrap_author_identities(session)
            session.commit()
            self.assertEqual(session.query(PaperCreatorMention).count(), 2)
            self.assertEqual(counts["source_author_mentions"], 1)
            editor = session.query(PaperCreatorMention).filter_by(creator_type="editor").one()
            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=editor.creator_mention_id)
                .count(),
                0,
            )
            self.assertEqual(
                session.query(Authorship)
                .filter_by(creator_mention_id=editor.creator_mention_id)
                .count(),
                0,
            )


if __name__ == "__main__":
    unittest.main()
