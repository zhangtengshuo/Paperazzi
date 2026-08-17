"""Phase 5 query/service and FastAPI MVP tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import Paper  # noqa: E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.identity import bootstrap_author_identities  # noqa: E402
from paperazzi.identity.models import Authorship  # noqa: E402
from paperazzi.ingest.models import CanonicalCreator, CanonicalZoteroItem  # noqa: E402
from paperazzi.web.api import create_app  # noqa: E402
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


def item(
    key: str,
    item_id: int,
    title: str,
    creators: list[tuple[int, str, str]],
    *,
    year: str = "2025",
    venue: str = "Journal of Tests",
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
        fields={"title": title, "date": year, "publicationTitle": venue},
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


class Phase5WebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "phase5.sqlite3"
        proc = alembic("upgrade", "head", db_path=self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        self.engine = create_paperazzi_engine(self.db)
        self.sf = sa.orm.sessionmaker(bind=self.engine)
        scan = persist_zotero_scan(
            self.sf,
            [
                item("A", 1, "Alpha paper", [(10, "Alice", "Smith"), (11, "Bob", "Jones")]),
                item("B", 2, "First Alex paper", [(20, "Alex", "Wang")]),
                item("C", 3, "Second Alex paper", [(21, "Alex", "Wang")]),
            ],
            {"run_token": "phase5-scan", "source_db_path": "/tmp/fake"},
        )
        self.assertEqual(scan.status, "COMPLETED", scan.error)
        with self.sf() as session:
            bootstrap_author_identities(session)
            alpha = session.query(Paper).filter_by(title="Alpha paper").one()
            bob_authorship = (
                session.query(Authorship)
                .filter(Authorship.paper_id == alpha.paper_id, Authorship.order_index == 1)
                .one()
            )
            bob_authorship.is_corresponding_author = True
            bob_authorship.corresponding_status = "ACCEPTED"
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_paper_detail_starts_from_complete_source_authors(self) -> None:
        with self.sf() as session:
            service = PaperazziQueryService(session)
            alpha = session.query(Paper).filter_by(title="Alpha paper").one()
            detail = service.get_paper(alpha.paper_id)
            self.assertEqual(len(detail["authors"]), 2)
            self.assertEqual(detail["authors"][0]["source_name"], "Alice Smith")
            self.assertIn("FIRST", detail["authors"][0]["roles"])
            self.assertIn("CORRESPONDING", detail["authors"][1]["roles"])

            second_alex = session.query(Paper).filter_by(title="Second Alex paper").one()
            alex_detail = service.get_paper(second_alex.paper_id)
            self.assertEqual(len(alex_detail["authors"]), 1)
            self.assertEqual(alex_detail["authors"][0]["source_name"], "Alex Wang")
            self.assertEqual(alex_detail["authors"][0]["identity_status"], "UNRESOLVED")
            self.assertIn("FIRST", alex_detail["authors"][0]["roles"])

    def test_author_profile_and_search(self) -> None:
        with self.sf() as session:
            service = PaperazziQueryService(session)
            search = service.search("Alice")
            self.assertEqual(len(search["authors"]), 1)
            author_id = search["authors"][0]["author_id"]
            profile = service.get_author(author_id)
            self.assertEqual(profile["preferred_name"], "Alice Smith")
            self.assertEqual(profile["paper_count"], 1)
            self.assertEqual(profile["first_author_count"], 1)
            self.assertTrue(profile["enrichment_priority"])

            papers = service.search("Alpha")
            self.assertEqual(papers["papers"][0]["title"], "Alpha paper")

    def test_http_mvp_routes(self) -> None:
        client = TestClient(create_app(self.db))
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn("Paperazzi", client.get("/").text)
        self.assertEqual(client.get("/health").json()["status"], "OK")

        papers = client.get("/api/papers", params={"limit": 20}).json()
        self.assertEqual(papers["total"], 3)
        alpha = next(row for row in papers["items"] if row["title"] == "Alpha paper")
        detail = client.get(f"/api/papers/{alpha['paper_id']}").json()
        self.assertEqual(len(detail["authors"]), 2)
        self.assertEqual(client.get(f"/api/papers/{alpha['paper_id']}/pdf").status_code, 404)

        search = client.get("/api/search", params={"q": "Alice"}).json()
        self.assertEqual(search["authors"][0]["preferred_name"], "Alice Smith")
        author_id = search["authors"][0]["author_id"]
        profile = client.get(f"/api/authors/{author_id}").json()
        self.assertEqual(profile["preferred_name"], "Alice Smith")
        self.assertEqual(client.get("/api/reviews/identity").status_code, 200)


if __name__ == "__main__":
    unittest.main()
