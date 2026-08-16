"""Phase 4D tests for accepted-reference-only local paper matching."""

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
from paperazzi.database.models import (  # noqa: E402
    Paper,
    PaperDocument,
    PaperReference,
    PaperReferenceMatch,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    persist_reference_section,
    record_extraction_review,
)
from paperazzi.identity.models import ReferenceMatchEvidence, ResolutionReviewQueue  # noqa: E402
from paperazzi.identity.reference_resolution import (  # noqa: E402
    LocalReferenceResolver,
    normalize_doi,
)
from paperazzi.ingest.models import (  # noqa: E402
    CanonicalAttachment,
    CanonicalCreator,
    CanonicalZoteroItem,
)
from paperazzi.local_evidence.pdf import ReferenceEntry, ReferenceSection  # noqa: E402


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


def item(
    key: str,
    item_id: int,
    *,
    title: str,
    doi: str | None = None,
    year: str = "2020",
    venue: str = "Journal of Chemical Physics",
    author_last: str = "Smith",
    pdf: bool = False,
) -> CanonicalZoteroItem:
    fields = {"title": title, "date": year, "publicationTitle": venue}
    if doi:
        fields["DOI"] = doi
    attachments = ()
    if pdf:
        attachments = (
            CanonicalAttachment(
                library_id=1,
                item_id=item_id + 1000,
                item_key=f"ATT{key}",
                parent_item_id=item_id,
                link_mode=0,
                link_mode_name="imported_file",
                content_type="application/pdf",
                path=f"storage:ATT{key}/paper.pdf",
                resolved_path=f"/tmp/{key}.pdf",
                local_exists=True,
                resolution="zotero-storage",
                storage_hash=f"hash-{key}",
            ),
        )
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
        fields=fields,
        creators=(
            CanonicalCreator(
                creator_id=item_id * 10,
                creator_type="author",
                order_index=0,
                first_name="Alice",
                last_name=author_last,
            ),
        ),
        collections=(),
        tags=(),
        attachments=attachments,
    )


class Phase4ReferenceResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "refs.sqlite3"
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
            {"run_token": "reference-scan", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(result.status, "COMPLETED", result.error)

    def accepted_reference(
        self,
        session,
        *,
        raw_text: str,
        dois: tuple[str, ...] = (),
        years: tuple[str, ...] = ("2020",),
    ) -> PaperReference:
        citing = session.query(Paper).filter(Paper.title == "Citing Paper").one()
        document = session.query(PaperDocument).filter_by(paper_id=citing.paper_id).one()
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
        section = ReferenceSection(
            heading="References",
            start_page=1,
            end_page=1,
            method="numbered-punctuated",
            confidence="HIGH",
            raw_text=raw_text,
            entries=(
                ReferenceEntry(
                    ordinal=1,
                    raw_text=raw_text,
                    dois=dois,
                    years=years,
                ),
            ),
            text_channel="PYMUPDF_SORTED",
        )
        persist_reference_section(
            session, citing.paper_id, document.document_id, attempt, section
        )
        record_extraction_review(
            session,
            attempt,
            reviewer_type="MANUAL",
            decision="PASS",
            section_confidence="HIGH",
            segmentation_confidence="HIGH",
            entry_text_quality="GOOD",
        )
        accept_attempt(session, run, attempt, "PASS")
        session.flush()
        return session.query(PaperReference).filter_by(citing_paper_id=citing.paper_id).one()

    def test_doi_normalization(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC)."), "10.1000/abc")
        self.assertEqual(normalize_doi("DOI: 10.1/X"), "10.1/x")

    def test_unique_doi_exact_auto_accepts(self) -> None:
        self.scan([
            item("CITE", 1, title="Citing Paper", pdf=True),
            item("TARGET", 2, title="Target Paper", doi="10.1000/target"),
        ])
        with self.sf() as session:
            reference = self.accepted_reference(
                session,
                raw_text="Smith, A. Target Paper. 2020. doi:10.1000/target",
                dois=("10.1000/target",),
            )
            result = LocalReferenceResolver(session).resolve(reference)
            session.commit()
            self.assertEqual(result["status"], "ACCEPTED")
            match = session.query(PaperReferenceMatch).filter_by(status="ACCEPTED").one()
            self.assertEqual(match.match_type, "DOI_EXACT")
            self.assertEqual(match.match_score, 1.0)
            self.assertGreater(session.query(ReferenceMatchEvidence).count(), 0)

    def test_duplicate_local_doi_is_ambiguous(self) -> None:
        self.scan([
            item("CITE", 1, title="Citing Paper", pdf=True),
            item("A", 2, title="Target A", doi="10.1000/dup"),
            item("B", 3, title="Target B", doi="10.1000/dup"),
        ])
        with self.sf() as session:
            reference = self.accepted_reference(
                session,
                raw_text="Target doi:10.1000/dup 2020",
                dois=("10.1000/dup",),
            )
            result = LocalReferenceResolver(session).resolve(reference)
            session.commit()
            self.assertEqual(result["status"], "AMBIGUOUS")
            self.assertEqual(
                session.query(PaperReferenceMatch).filter_by(status="ACCEPTED").count(), 0
            )
            self.assertEqual(
                session.query(ResolutionReviewQueue)
                .filter_by(queue_type="AMBIGUOUS_REFERENCE_MATCH", status="OPEN")
                .count(),
                1,
            )

    def test_title_year_venue_author_composite_can_auto_accept(self) -> None:
        title = "A Very Specific Molecular Dynamics Method"
        self.scan([
            item("CITE", 1, title="Citing Paper", pdf=True),
            item(
                "TARGET",
                2,
                title=title,
                year="2020",
                venue="Journal of Chemical Physics",
                author_last="Smith",
            ),
        ])
        with self.sf() as session:
            reference = self.accepted_reference(
                session,
                raw_text=(
                    "Smith, A. A Very Specific Molecular Dynamics Method. "
                    "Journal of Chemical Physics 2020."
                ),
                years=("2020",),
            )
            result = LocalReferenceResolver(session).resolve(reference)
            session.commit()
            self.assertEqual(result["status"], "ACCEPTED")
            self.assertEqual(result["match_type"], "TITLE_EXACT_NORMALIZED")

    def test_unaccepted_reference_is_never_matched(self) -> None:
        self.scan([
            item("CITE", 1, title="Citing Paper", pdf=True),
            item("TARGET", 2, title="Target Paper", doi="10.1000/target"),
        ])
        with self.sf() as session:
            reference = self.accepted_reference(
                session,
                raw_text="Target Paper doi:10.1000/target 2020",
                dois=("10.1000/target",),
            )
            reference.acceptance_status = "CANDIDATE"
            session.flush()
            result = LocalReferenceResolver(session).resolve(reference)
            self.assertEqual(result["status"], "SKIPPED_UNACCEPTED")
            self.assertEqual(session.query(PaperReferenceMatch).count(), 0)

    def test_self_match_is_excluded(self) -> None:
        self.scan([item("CITE", 1, title="Citing Paper", doi="10.1000/self", pdf=True)])
        with self.sf() as session:
            reference = self.accepted_reference(
                session,
                raw_text="Citing Paper doi:10.1000/self 2020",
                dois=("10.1000/self",),
            )
            result = LocalReferenceResolver(session).resolve(reference)
            session.commit()
            self.assertEqual(result["status"], "UNRESOLVED")
            self.assertEqual(session.query(PaperReferenceMatch).count(), 0)


if __name__ == "__main__":
    unittest.main()
