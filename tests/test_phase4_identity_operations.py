"""Phase 4B tests for explicit identity correction operations."""

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
    AuthorExternalID,
    AuthorIdentityDecision,
    AuthorIdentityMembership,
    Authorship,
    ResolutionReviewQueue,
)
from paperazzi.identity.operations import (  # noqa: E402
    add_external_id,
    mark_not_same_person,
    set_identity_lock,
    unlink_mention,
)
from paperazzi.identity.service import (  # noqa: E402
    IdentityResolutionError,
    accept_membership,
    bootstrap_author_identities,
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


def make_item() -> CanonicalZoteroItem:
    return CanonicalZoteroItem(
        library_id=1,
        item_id=1,
        item_key="I1",
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": "Identity Ops"},
        creators=(
            CanonicalCreator(
                creator_id=10,
                creator_type="author",
                order_index=0,
                first_name="Alice",
                last_name="Smith",
            ),
        ),
        collections=(),
        tags=(),
        attachments=(),
    )


class Phase4IdentityOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ops.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.sf,
            [make_item()],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED", result.error)
        with self.sf() as session:
            bootstrap_author_identities(session)
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_unlink_relink_unlink_keeps_repeatable_history(self) -> None:
        with self.sf() as session:
            mention = session.query(PaperCreatorMention).one()
            original = (
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
                .one()
            )
            author = session.get(Author, original.author_id)

            unlink_mention(session, mention.creator_mention_id, actor="MANUAL")
            accept_membership(session, mention, author, actor="MANUAL", reason_code="RELINK")
            unlink_mention(session, mention.creator_mention_id, actor="MANUAL")
            session.commit()

            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(
                    creator_mention_id=mention.creator_mention_id,
                    author_id=author.author_id,
                    status="SUPERSEDED",
                )
                .count(),
                2,
            )
            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
                .count(),
                0,
            )
            self.assertEqual(
                session.query(Authorship)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACTIVE")
                .count(),
                0,
            )

    def test_not_same_person_persists_rejection_and_decision(self) -> None:
        with self.sf() as session:
            mention = session.query(PaperCreatorMention).one()
            original = (
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
                .one()
            )
            rejected = mark_not_same_person(
                session,
                mention.creator_mention_id,
                original.author_id,
                actor="MANUAL",
                notes="known namesake",
            )
            session.commit()
            self.assertEqual(rejected.status, "REJECTED")
            self.assertEqual(
                session.query(AuthorIdentityMembership)
                .filter_by(creator_mention_id=mention.creator_mention_id, status="ACCEPTED")
                .count(),
                0,
            )
            self.assertEqual(
                session.query(AuthorIdentityDecision)
                .filter_by(operation="NOT_SAME_PERSON")
                .count(),
                1,
            )

    def test_lock_unlock_is_manual_authority(self) -> None:
        with self.sf() as session:
            author = session.query(Author).one()
            with self.assertRaises(IdentityResolutionError):
                set_identity_lock(session, author.author_id, True, actor="DETERMINISTIC")
            set_identity_lock(session, author.author_id, True, actor="MANUAL")
            self.assertTrue(author.locked)
            set_identity_lock(session, author.author_id, False, actor="MANUAL")
            session.commit()
            self.assertFalse(author.locked)
            operations = [
                row.operation
                for row in session.query(AuthorIdentityDecision)
                .filter(AuthorIdentityDecision.operation.in_(("LOCK_IDENTITY", "UNLOCK_IDENTITY")))
                .order_by(AuthorIdentityDecision.decision_id)
                .all()
            ]
            self.assertEqual(operations, ["LOCK_IDENTITY", "UNLOCK_IDENTITY"])

    def test_external_id_conflict_is_not_silently_merged(self) -> None:
        with self.sf() as session:
            first = session.query(Author).one()
            second = Author(
                author_id="01K00000000000000000000000",
                preferred_name="Different Person",
                normalized_name="different person",
                status="ACTIVE",
                locked=False,
            )
            session.add(second)
            session.flush()
            add_external_id(
                session,
                first.author_id,
                "ORCID",
                "https://orcid.org/0000-0002-1825-0097",
                source="manual",
            )
            with self.assertRaises(IdentityResolutionError):
                add_external_id(
                    session,
                    second.author_id,
                    "ORCID",
                    "0000-0002-1825-0097",
                    source="manual",
                )
            session.flush()
            self.assertEqual(
                session.query(AuthorExternalID).filter_by(status="ACCEPTED").count(), 1
            )
            self.assertEqual(
                session.query(ResolutionReviewQueue)
                .filter_by(queue_type="IDENTITY_CONFLICT", status="OPEN")
                .count(),
                1,
            )

    def test_rejected_external_id_history_may_repeat_value(self) -> None:
        with self.sf() as session:
            first = session.query(Author).one()
            second = Author(
                author_id="01K00000000000000000000001",
                preferred_name="Other",
                normalized_name="other",
                status="ACTIVE",
                locked=False,
            )
            session.add(second)
            session.flush()
            add_external_id(
                session,
                first.author_id,
                "ORCID",
                "0000-0002-1825-0097",
                source="candidate",
                status="REJECTED",
            )
            add_external_id(
                session,
                second.author_id,
                "ORCID",
                "0000-0002-1825-0097",
                source="candidate",
                status="REJECTED",
            )
            session.commit()
            self.assertEqual(
                session.query(AuthorExternalID).filter_by(status="REJECTED").count(), 2
            )


if __name__ == "__main__":
    unittest.main()
