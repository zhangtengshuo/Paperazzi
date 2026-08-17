"""Phase 4C tests for accepted PDF evidence and paper-scoped authorship roles."""

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
from paperazzi.database.models import DocumentEvidenceSpan, Paper, PaperDocument  # noqa: E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    persist_evidence_spans,
    record_extraction_review,
)
from paperazzi.identity.authorship_evidence import propose_authorship_evidence  # noqa: E402
from paperazzi.identity.models import (  # noqa: E402
    Authorship,
    AuthorshipEvidence,
    CreatorMentionRoleEvidence,
    ResolutionReviewQueue,
)
from paperazzi.identity.service import bootstrap_author_identities  # noqa: E402
from paperazzi.ingest.models import (  # noqa: E402
    CanonicalAttachment,
    CanonicalCreator,
    CanonicalZoteroItem,
)


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
        item_key="PAPER",
        item_type="journalArticle",
        zotero_version=1,
        synced=1,
        date_added="2026-01-01",
        date_modified="2026-01-01",
        client_date_modified="2026-01-01",
        deleted=False,
        fields={"title": "Evidence Paper", "date": "2020"},
        creators=(
            CanonicalCreator(
                creator_id=10,
                creator_type="author",
                order_index=0,
                first_name="Alice",
                last_name="Smith",
            ),
            CanonicalCreator(
                creator_id=20,
                creator_type="author",
                order_index=1,
                first_name="Bob",
                last_name="Jones",
            ),
        ),
        collections=(),
        tags=(),
        attachments=(
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key="ATT",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path="storage:ATT/paper.pdf",
                resolved_path="/tmp/paper.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash="h1",
            ),
        ),
    )


class Phase4AuthorshipEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "evidence.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.sf,
            [make_item()],
            {"run_token": "s1", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED")
        with self.sf() as session:
            bootstrap_author_identities(session)
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _add_span(self, session, *, kind: str, text: str, accept: bool = True) -> int:
        document = session.query(PaperDocument).one()
        run = create_extraction_run(
            session, document.document_id, "FIRST_AVAILABLE", document.document_change_key
        )
        attempt = add_extraction_attempt(
            session,
            run,
            attempt_number=1,
            actor="DETERMINISTIC",
            strategy="test",
            text_source="PDF_NATIVE",
        )
        persist_evidence_spans(
            session,
            document.document_id,
            attempt,
            [{"kind": kind, "page_index": 0, "text": text}],
        )
        span = session.query(DocumentEvidenceSpan).filter_by(attempt_id=attempt.attempt_id).one()
        if accept:
            record_extraction_review(
                session, attempt, reviewer_type="MANUAL", decision="PASS"
            )
            accept_attempt(session, run, attempt, "PASS")
        session.flush()
        return span.evidence_span_id

    def test_clear_corresponding_author_mapping(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text="Corresponding author: Alice Smith, alice@example.org",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["corresponding_accepted"], 1)
            alice = (
                session.query(Authorship)
                .filter_by(order_index=0, status="ACTIVE")
                .one()
            )
            self.assertTrue(alice.is_corresponding_author)
            self.assertEqual(alice.corresponding_status, "ACCEPTED")
            self.assertEqual(
                session.query(AuthorshipEvidence)
                .filter_by(evidence_type="CORRESPONDING_AUTHOR", status="ACCEPTED")
                .count(),
                1,
            )

    def test_multiple_corresponding_authors(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text=(
                    "Corresponding authors: Alice Smith, alice@example.org; "
                    "Bob Jones, bob@example.org"
                ),
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["corresponding_accepted"], 2)
            self.assertEqual(
                session.query(Authorship)
                .filter_by(status="ACTIVE", is_corresponding_author=True)
                .count(),
                2,
            )

    def test_publisher_service_correspondence_is_rejected(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text=(
                    "Corresponding author: Alice Smith. For publisher customer service "
                    "contact support@publisher.example"
                ),
            )
            paper_id = session.query(Paper).one().paper_id
            propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(
                session.query(AuthorshipEvidence)
                .filter_by(evidence_type="CORRESPONDING_AUTHOR", status="REJECTED")
                .count(),
                1,
            )
            self.assertEqual(
                session.query(Authorship).filter_by(is_corresponding_author=True).count(), 0
            )

    def test_unmapped_corresponding_name_goes_to_review(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text="Corresponding author: Carol White, carol@example.org",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["unresolved"], 1)
            self.assertEqual(
                session.query(ResolutionReviewQueue)
                .filter_by(queue_type="UNRESOLVED_CORRESPONDING_AUTHOR", status="OPEN")
                .count(),
                1,
            )

    def test_candidate_pdf_span_is_not_consumed(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text="Corresponding author: Alice Smith, alice@example.org",
                accept=False,
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            self.assertEqual(result["corresponding_accepted"], 0)
            self.assertEqual(session.query(AuthorshipEvidence).count(), 0)
            self.assertEqual(
                session.query(Authorship).filter_by(is_corresponding_author=True).count(), 0
            )

    def test_affiliation_mapping_stays_candidate(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="affiliation",
                text="Alice Smith, Department of Chemistry, Example University",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["affiliation_candidates"], 1)
            row = session.query(AuthorshipEvidence).filter_by(evidence_type="AFFILIATION").one()
            self.assertEqual(row.status, "CANDIDATE")

    def test_bare_electronic_mail_does_not_create_corresponding_role(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text="a)Electronic mail: alice.smith@example.org",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["mention_role_accepted"], 0)
            self.assertEqual(result["corresponding_accepted"], 0)
            self.assertEqual(session.query(CreatorMentionRoleEvidence).count(), 0)
            self.assertEqual(session.query(ResolutionReviewQueue).count(), 0)

    def test_grouped_explicit_block_prefers_email_mapping_over_extra_name(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="correspondence",
                text=(
                    "Corresponding author: Alice Smith, alice.smith@example.org. "
                    "Bob Jones assisted with correspondence formatting."
                ),
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["mention_role_accepted"], 1)
            corresponding = (
                session.query(Authorship)
                .filter_by(status="ACTIVE", is_corresponding_author=True)
                .all()
            )
            self.assertEqual([row.order_index for row in corresponding], [0])

    def test_symbol_footnote_maps_role_to_marked_source_mention(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="author-marker-candidate",
                text="Alice Smith and Bob Jones*",
            )
            self._add_span(
                session,
                kind="correspondence",
                text="* Author to whom correspondence should be addressed.",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["mention_role_accepted"], 1)
            bob = session.query(Authorship).filter_by(order_index=1, status="ACTIVE").one()
            alice = session.query(Authorship).filter_by(order_index=0, status="ACTIVE").one()
            self.assertTrue(bob.is_corresponding_author)
            self.assertFalse(alice.is_corresponding_author)

    def test_starred_author_plus_affiliation_contact_is_role_evidence(self) -> None:
        with self.sf() as session:
            self._add_span(
                session,
                kind="author-marker-candidate",
                text="Alice Smith and Bob Jones*",
            )
            self._add_span(
                session,
                kind="contact-candidate",
                text="Department of Chemistry, Example University. E-mail: bob.jones@example.org",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["mention_role_accepted"], 1)
            role = session.query(CreatorMentionRoleEvidence).filter_by(status="ACCEPTED").one()
            bob_mention = (
                session.query(__import__("paperazzi.database.models", fromlist=["PaperCreatorMention"]).PaperCreatorMention)
                .filter_by(paper_id=paper_id, order_index=1)
                .one()
            )
            self.assertEqual(role.creator_mention_id, bob_mention.creator_mention_id)

    def test_role_evidence_survives_without_active_canonical_authorship(self) -> None:
        with self.sf() as session:
            alice = session.query(Authorship).filter_by(order_index=0, status="ACTIVE").one()
            alice.status = "SUPERSEDED"
            self._add_span(
                session,
                kind="correspondence",
                text="Corresponding author: Alice Smith, alice.smith@example.org",
            )
            paper_id = session.query(Paper).one().paper_id
            result = propose_authorship_evidence(session, paper_id)
            session.commit()
            self.assertEqual(result["mention_role_accepted"], 1)
            self.assertEqual(result["corresponding_accepted"], 0)
            self.assertEqual(
                session.query(CreatorMentionRoleEvidence).filter_by(status="ACCEPTED").count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
