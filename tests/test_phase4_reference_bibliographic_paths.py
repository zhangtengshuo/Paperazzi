"""Pure scoring tests for Phase 4D non-DOI bibliographic match classes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.identity.reference_resolution import (  # noqa: E402
    IndexedPaper,
    LocalReferenceResolver,
)


def paper(
    paper_id: int,
    *,
    title: str = "",
    year: int = 2020,
    venue: str = "Journal of Chemical Physics",
    author: str = "smith",
    volume: str | None = None,
    pages: str | None = None,
) -> IndexedPaper:
    return IndexedPaper(
        paper_id=paper_id,
        title=title,
        normalized_title=title.casefold(),
        doi=None,
        year=year,
        venue=venue,
        normalized_venue=venue.casefold(),
        first_author_family=author,
        volume=volume,
        issue=None,
        pages=pages,
        article_number=None,
    )


class Phase4BibliographicPathTests(unittest.TestCase):
    def resolver(self, papers: list[IndexedPaper]) -> LocalReferenceResolver:
        resolver = LocalReferenceResolver.__new__(LocalReferenceResolver)
        resolver.paper_index = papers
        return resolver

    def test_author_year_journal_is_candidate_class_not_auto_truth(self) -> None:
        resolver = self.resolver([paper(2)])
        reference = SimpleNamespace(
            citing_paper_id=1,
            raw_text="Smith, A. Journal of Chemical Physics 2020, unrelated title omitted.",
        )
        candidates = resolver._bibliographic_candidates(reference, {2020}, set())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].match_type, "AUTHOR_YEAR_JOURNAL")
        self.assertGreaterEqual(candidates[0].score, 0.70)
        self.assertLess(candidates[0].score, 0.90)

    def test_journal_volume_page_year_is_strong_class(self) -> None:
        resolver = self.resolver([paper(2, volume="157", pages="1234-1245")])
        reference = SimpleNamespace(
            citing_paper_id=1,
            raw_text="Journal of Chemical Physics 157, 1234-1245 (2020).",
        )
        candidates = resolver._bibliographic_candidates(reference, {2020}, set())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].match_type, "JOURNAL_VOLUME_PAGE_YEAR")
        self.assertGreaterEqual(candidates[0].score, 0.90)

    def test_jvpy_requires_all_four_components(self) -> None:
        resolver = self.resolver([paper(2, volume="157", pages="1234-1245")])
        reference = SimpleNamespace(
            citing_paper_id=1,
            raw_text="Journal of Chemical Physics 157 (2020).",
        )
        candidates = resolver._bibliographic_candidates(reference, {2020}, set())
        self.assertEqual(candidates, [])

    def test_wrong_year_rejects_even_strong_volume_page(self) -> None:
        resolver = self.resolver([paper(2, year=2021, volume="157", pages="1234-1245")])
        reference = SimpleNamespace(
            citing_paper_id=1,
            raw_text="Journal of Chemical Physics 157, 1234-1245 (2020).",
        )
        candidates = resolver._bibliographic_candidates(reference, {2020}, set())
        self.assertEqual(candidates, [])

    def test_reference_doi_conflict_marks_bibliographic_candidate(self) -> None:
        indexed = paper(2, title="specific molecular method")
        indexed = IndexedPaper(
            **{**indexed.__dict__, "doi": "10.1000/local"}
        )
        resolver = self.resolver([indexed])
        reference = SimpleNamespace(
            citing_paper_id=1,
            raw_text=(
                "Smith. Specific molecular method. Journal of Chemical Physics 2020."
            ),
        )
        candidates = resolver._bibliographic_candidates(
            reference, {2020}, {"10.1000/different"}
        )
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].contradiction)


if __name__ == "__main__":
    unittest.main()
