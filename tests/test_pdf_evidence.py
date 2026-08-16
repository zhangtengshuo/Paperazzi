from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.local_evidence.pdf import (
    extract_dois,
    extract_pdf_evidence,
    find_reference_section,
    segment_reference_entries,
)


def _load_pymupdf_for_test():
    for name in ("pymupdf", "fitz"):
        try:
            return importlib.import_module(name)
        except ImportError:
            pass
    return None


PYMUPDF = _load_pymupdf_for_test()


class PdfEvidenceHeuristicTests(unittest.TestCase):
    def test_doi_extraction_normalizes_and_strips_terminal_punctuation(self) -> None:
        text = (
            "See https://doi.org/10.1021/acs.jpclett.4c01234. "
            "Also DOI: 10.1103/PhysRevB.90.075128); repeated 10.1103/physrevb.90.075128."
        )
        self.assertEqual(
            extract_dois(text),
            (
                "10.1021/acs.jpclett.4c01234",
                "10.1103/physrevb.90.075128",
            ),
        )

    def test_numbered_references_are_segmented_with_identifiers(self) -> None:
        text = """
[1] A. Alpha, Journal 1, 10, 100 (2020). doi:10.1000/alpha.
[2] B. Beta and C. Gamma, Journal 2, 11, 200 (2021).
[3] D. Delta, Journal 3, 12, 300 (2022). https://doi.org/10.1000/delta
"""
        entries, method, confidence = segment_reference_entries(text)
        self.assertEqual(method, "numbered-punctuated")
        self.assertEqual(confidence, "HIGH")
        self.assertEqual([entry.ordinal for entry in entries], [1, 2, 3])
        self.assertEqual(entries[0].dois, ("10.1000/alpha",))
        self.assertEqual(entries[2].dois, ("10.1000/delta",))
        self.assertIn("2021", entries[1].years)

    def test_reference_heading_prefers_late_exact_heading(self) -> None:
        pages = [
            "Contents\nReferences\nIntroduction\nThis is only a table of contents mention.",
            "Main text\nMore main text.",
            "REFERENCES\n[1] A. Alpha (2020).\n[2] B. Beta (2021).\n[3] C. Gamma (2022).",
        ]
        section = find_reference_section(pages)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.start_page, 2)
        self.assertEqual(section.heading, "REFERENCES")
        self.assertEqual(len(section.entries), 3)
        self.assertEqual(section.confidence, "HIGH")

    def test_author_year_section_is_preserved_even_when_not_force_split(self) -> None:
        pages = [
            "Title\nBody",
            "Bibliography\nSmith, J. 2018. First work.\nJones, A. 2020. Second work.\nBrown, B. 2022. Third work.",
        ]
        section = find_reference_section(pages)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.method, "raw-author-year-or-unsegmented")
        self.assertEqual(section.confidence, "MEDIUM")
        self.assertEqual(section.entries, ())
        self.assertIn("Smith, J. 2018", section.raw_text)

    def test_missing_pdf_is_nonfatal_data_state(self) -> None:
        result = extract_pdf_evidence("/path/that/does/not/exist/paper.pdf")
        self.assertEqual(result.text_status, "FILE_UNAVAILABLE")
        self.assertIsNotNone(result.error)
        self.assertEqual(result.page_count, 0)


@unittest.skipUnless(PYMUPDF is not None, "PyMuPDF not installed")
class PdfEvidenceIntegrationTests(unittest.TestCase):
    def _make_pdf(self, path: Path) -> None:
        doc = PYMUPDF.open()
        try:
            page1 = doc.new_page()
            page1.insert_textbox(
                PYMUPDF.Rect(50, 50, 545, 500),
                """A Synthetic Paper for Paperazzi
Ada Lovelace1 and Grace Hopper2*
1 Department of Computational Science, Example University, London, UK
2 Center for Quantum Research, Example Institute, New York, USA
* Corresponding author. E-mail: grace.hopper@example.edu

Abstract
This synthetic article exists only to exercise local PDF evidence extraction.
""",
                fontsize=11,
            )
            page2 = doc.new_page()
            page2.insert_textbox(
                PYMUPDF.Rect(50, 50, 545, 760),
                """Results and discussion
The synthetic body contains enough text to represent a normal native text layer. """
                + ("This sentence is repeated for extraction coverage. " * 12)
                + """

REFERENCES
[1] A. Alpha, J. Example 1, 10 (2020). doi:10.1000/alpha.
[2] B. Beta, J. Example 2, 20 (2021).
[3] C. Gamma, J. Example 3, 30 (2022). https://doi.org/10.1000/gamma
""",
                fontsize=10,
            )
            metadata = {"title": "A Synthetic Paper for Paperazzi", "author": "Ada Lovelace; Grace Hopper"}
            doc.set_metadata(metadata)
            doc.save(str(path))
        finally:
            doc.close()

    def test_end_to_end_native_pdf_extracts_front_matter_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "synthetic.pdf"
            self._make_pdf(pdf)
            evidence = extract_pdf_evidence(pdf)

        self.assertIsNone(evidence.error)
        self.assertEqual(evidence.page_count, 2)
        self.assertIn(evidence.text_status, {"NATIVE_TEXT_GOOD", "NATIVE_TEXT_PARTIAL"})
        self.assertEqual(evidence.metadata.get("title"), "A Synthetic Paper for Paperazzi")
        self.assertIn("grace.hopper@example.edu", evidence.emails)
        self.assertTrue(any("Example University" in span.text for span in evidence.affiliation_candidates))
        self.assertTrue(any("Corresponding author" in span.text for span in evidence.correspondence_candidates))
        self.assertIsNotNone(evidence.references)
        assert evidence.references is not None
        self.assertEqual(evidence.references.confidence, "HIGH")
        self.assertEqual(len(evidence.references.entries), 3)
        self.assertEqual(evidence.references.entries[0].dois, ("10.1000/alpha",))
        self.assertEqual(evidence.references.entries[2].dois, ("10.1000/gamma",))


if __name__ == "__main__":
    unittest.main()
