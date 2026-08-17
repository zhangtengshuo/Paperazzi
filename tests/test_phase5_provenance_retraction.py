"""Regression tests for document roles, correspondence mapping, and reversible derivations."""
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
from paperazzi.database.models import (  # noqa: E402
    DocumentEvidenceSpan,
    DocumentExtractionRun,
    PaperCreatorMention,
    Paper,
    PaperDocument,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    persist_evidence_spans,
    record_extraction_review,
)
from paperazzi.identity.authorship_evidence import propose_authorship_evidence  # noqa: E402
from paperazzi.identity.models import Authorship, AuthorshipEvidence  # noqa: E402
from paperazzi.identity.service import bootstrap_author_identities  # noqa: E402
from paperazzi.ingest.models import CanonicalAttachment, CanonicalCreator, CanonicalZoteroItem  # noqa: E402
from paperazzi.provenance.models import DocumentRole, RetractionEvent, RetractionImpact  # noqa: E402
from paperazzi.provenance.service import (  # noqa: E402
    retract_extraction_attempt,
    select_primary_document,
    set_document_role,
)
from paperazzi.web.queries import PaperazziQueryService  # noqa: E402


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


def make_item(main_path: Path, si_path: Path) -> CanonicalZoteroItem:
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
        fields={"title": "Document-role regression", "date": "2026"},
        creators=(
            CanonicalCreator(
                creator_id=10,
                creator_type="author",
                order_index=0,
                first_name="Rishab",
                last_name="Dutta",
            ),
            CanonicalCreator(
                creator_id=20,
                creator_type="author",
                order_index=1,
                first_name="Marc",
                last_name="Illa",
            ),
        ),
        collections=(),
        tags=(),
        attachments=(
            CanonicalAttachment(
                library_id=1,
                item_id=2,
                item_key="MAIN",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path="storage:MAIN/article.pdf",
                resolved_path=str(main_path),
                local_exists=True,
                resolution="zotero-storage",
                storage_hash="main-hash",
            ),
            CanonicalAttachment(
                library_id=1,
                item_id=3,
                item_key="SI",
                parent_item_id=1,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path="storage:SI/article_si_001.pdf",
                resolved_path=str(si_path),
                local_exists=True,
                resolution="zotero-storage",
                storage_hash="si-hash",
            ),
        ),
    )


class ProvenanceRetractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "paperazzi.sqlite3"
        self.main_pdf = root / "article.pdf"
        self.si_pdf = root / "article_si_001.pdf"
        self.main_pdf.write_bytes(b"%PDF-1.4\nmain article\n")
        self.si_pdf.write_bytes(b"%PDF-1.4\nsupporting information\n")
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1800:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        result = persist_zotero_scan(
            self.sf,
            [make_item(self.main_pdf, self.si_pdf)],
            {"run_token": "s1", "source_db_path": "/tmp/fake-zotero"},
        )
        self.assertEqual(result.status, "COMPLETED")
        with self.sf() as session:
            bootstrap_author_identities(session)
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _documents(self, session):
        docs = session.query(PaperDocument).order_by(PaperDocument.document_id).all()
        main = next(row for row in docs if Path(row.local_path or "").name == "article.pdf")
        si = next(row for row in docs if "_si_" in Path(row.local_path or "").name)
        return main, si

    def _accepted_span(self, session, document: PaperDocument, text: str) -> tuple[int, int]:
        run = create_extraction_run(
            session,
            document.document_id,
            "MANUAL_REBUILD",
            document.document_change_key,
        )
        attempt = add_extraction_attempt(
            session,
            run,
            attempt_number=1,
            actor="DETERMINISTIC",
            strategy="regression",
            text_source="PDF_NATIVE",
        )
        persist_evidence_spans(
            session,
            document.document_id,
            attempt,
            [{"kind": "correspondence-candidate", "page_index": 0, "text": text}],
        )
        record_extraction_review(session, attempt, reviewer_type="MANUAL", decision="PASS")
        accept_attempt(session, run, attempt, "PASS")
        span = session.query(DocumentEvidenceSpan).filter_by(attempt_id=attempt.attempt_id).one()
        session.flush()
        return attempt.attempt_id, span.evidence_span_id

    def test_primary_pdf_prefers_article_over_si(self) -> None:
        with self.sf() as session:
            paper_id = session.query(Paper).one().paper_id
            selected = select_primary_document(session, paper_id)
            self.assertIsNotNone(selected)
            self.assertEqual(Path(selected.local_path or "").name, "article.pdf")
            self.assertEqual(PaperazziQueryService(session).get_pdf_path(paper_id), self.main_pdf)

    def test_persisted_document_role_overrides_filename_heuristic(self) -> None:
        with self.sf() as session:
            main, si = self._documents(session)
            set_document_role(
                session,
                main.document_id,
                "SUPPLEMENTARY",
                reason_code="TEST_OVERRIDE",
                retract_if_supplementary=False,
            )
            set_document_role(
                session,
                si.document_id,
                "PRIMARY_ARTICLE",
                reason_code="TEST_OVERRIDE",
                retract_if_supplementary=False,
            )
            selected = select_primary_document(session, main.paper_id)
            self.assertEqual(selected.document_id, si.document_id)
            self.assertEqual(session.query(DocumentRole).count(), 2)

    def test_supplementary_reclassification_retracts_derived_role_but_keeps_raw_span(self) -> None:
        with self.sf() as session:
            _main, si = self._documents(session)
            _attempt_id, span_id = self._accepted_span(
                session,
                si,
                "Corresponding author: Rishab Dutta, rishab.dutta@example.org",
            )
            authorship = session.query(Authorship).filter_by(order_index=0, status="ACTIVE").one()
            authorship.is_corresponding_author = True
            authorship.corresponding_status = "ACCEPTED"
            evidence = AuthorshipEvidence(
                authorship_id=authorship.authorship_id,
                evidence_span_id=span_id,
                evidence_type="CORRESPONDING_AUTHOR",
                status="ACCEPTED",
                resolver="legacy-regression",
                score=1.0,
            )
            session.add(evidence)
            session.flush()

            set_document_role(
                session,
                si.document_id,
                "SUPPLEMENTARY",
                reason_code="CONFIRMED_SI",
                notes="Legacy SI evidence must no longer support paper-level roles.",
            )
            session.commit()

            self.assertEqual(session.get(DocumentEvidenceSpan, span_id).acceptance_status, "ACCEPTED")
            self.assertEqual(session.get(AuthorshipEvidence, evidence.authorship_evidence_id).status, "SUPERSEDED")
            refreshed = session.get(Authorship, authorship.authorship_id)
            self.assertFalse(refreshed.is_corresponding_author)
            self.assertEqual(refreshed.corresponding_status, "UNKNOWN")
            self.assertEqual(session.query(RetractionEvent).count(), 1)
            self.assertGreaterEqual(session.query(RetractionImpact).count(), 2)

    def test_retraction_preserves_projection_when_independent_evidence_remains(self) -> None:
        with self.sf() as session:
            main, si = self._documents(session)
            _main_attempt, main_span = self._accepted_span(
                session, main, "Corresponding author: Rishab Dutta, rishab.dutta@example.org"
            )
            _si_attempt, si_span = self._accepted_span(
                session, si, "Corresponding author: Rishab Dutta, rishab.dutta@example.org"
            )
            authorship = session.query(Authorship).filter_by(order_index=0, status="ACTIVE").one()
            for span_id in (main_span, si_span):
                session.add(
                    AuthorshipEvidence(
                        authorship_id=authorship.authorship_id,
                        evidence_span_id=span_id,
                        evidence_type="CORRESPONDING_AUTHOR",
                        status="ACCEPTED",
                        resolver="legacy-regression",
                        score=1.0,
                    )
                )
            authorship.is_corresponding_author = True
            authorship.corresponding_status = "ACCEPTED"
            session.flush()

            set_document_role(
                session,
                si.document_id,
                "SUPPLEMENTARY",
                reason_code="CONFIRMED_SI",
            )
            session.flush()
            refreshed = session.get(Authorship, authorship.authorship_id)
            self.assertTrue(refreshed.is_corresponding_author)
            self.assertEqual(refreshed.corresponding_status, "ACCEPTED")
            self.assertEqual(
                session.query(AuthorshipEvidence)
                .filter_by(authorship_id=authorship.authorship_id, status="ACCEPTED")
                .count(),
                1,
            )

    def test_bad_attempt_retraction_invalidates_raw_output_and_current_run_pointer(self) -> None:
        with self.sf() as session:
            main, _si = self._documents(session)
            attempt_id, span_id = self._accepted_span(
                session, main, "Corresponding author: Rishab Dutta, rishab.dutta@example.org"
            )
            run = session.query(DocumentExtractionRun).filter_by(accepted_attempt_id=attempt_id).one()
            self.assertEqual(run.accepted_attempt_id, attempt_id)
            event = retract_extraction_attempt(
                session,
                attempt_id,
                reason_code="PARSER_DEFECT",
                reason_text="Synthetic bad attempt",
            )
            session.flush()
            self.assertIsNotNone(event.retraction_id)
            self.assertEqual(session.get(DocumentEvidenceSpan, span_id).acceptance_status, "SUPERSEDED")
            self.assertIsNone(run.accepted_attempt_id)
            self.assertEqual(run.final_status, "UNRESOLVED")

    def test_correspondence_email_local_parts_map_two_authors_and_terminal_period(self) -> None:
        with self.sf() as session:
            main, _si = self._documents(session)
            self._accepted_span(
                session,
                main,
                "Corresponding authors: rishab.dutta@pnnl.gov and marc.illasubina@pnnl.gov.",
            )
            result = propose_authorship_evidence(session, main.paper_id)
            session.flush()
            self.assertEqual(result["corresponding_accepted"], 2)
            rows = session.query(Authorship).filter_by(status="ACTIVE").order_by(Authorship.order_index).all()
            self.assertEqual([row.is_corresponding_author for row in rows], [True, True])

    def test_correspondence_email_local_parts_map_initial_authors(self) -> None:
        with self.sf() as session:
            main, _si = self._documents(session)
            mentions = (
                session.query(PaperCreatorMention)
                .filter_by(paper_id=main.paper_id)
                .order_by(PaperCreatorMention.order_index)
                .all()
            )
            mentions[0].first_name = "R"
            mentions[0].display_name = "R Dutta"
            mentions[1].first_name = "M"
            mentions[1].display_name = "M Illa"
            self._accepted_span(
                session,
                main,
                "*Authors to whom correspondence should be addressed: "
                "rishab.dutta@pnnl.gov, marc.illasubina@pnnl.gov.",
            )
            result = propose_authorship_evidence(session, main.paper_id)
            session.flush()
            self.assertEqual(result["corresponding_accepted"], 2)
            rows = session.query(Authorship).filter_by(status="ACTIVE").order_by(Authorship.order_index).all()
            self.assertEqual([row.is_corresponding_author for row in rows], [True, True])

    def test_supplementary_span_cannot_create_corresponding_role(self) -> None:
        with self.sf() as session:
            _main, si = self._documents(session)
            self._accepted_span(
                session,
                si,
                "Corresponding authors: rishab.dutta@pnnl.gov and marc.illasubina@pnnl.gov.",
            )
            result = propose_authorship_evidence(session, si.paper_id)
            self.assertEqual(result["corresponding_accepted"], 0)
            self.assertEqual(session.query(AuthorshipEvidence).count(), 0)
            self.assertEqual(session.query(Authorship).filter_by(is_corresponding_author=True).count(), 0)


if __name__ == "__main__":
    unittest.main()
