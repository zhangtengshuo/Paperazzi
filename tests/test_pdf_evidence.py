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

    def test_author_year_lines_are_not_misread_as_bare_reference_ordinals(self) -> None:
        text = """
FRONTERA MARQUES, B.: Una funcion numerica. Zaragoza, 1943.
1962 FRUCHT, R., and G.-C. ROTA: La funcion de Mobius. Scientia.
1954 HARARY, F.: Lattice theory of partitions. Canadian J. Math.
1937 MILES, E.: The inversion problems of Mobius. Duke Math. J.
"""
        entries, method, confidence = segment_reference_entries(text)
        self.assertEqual(entries, ())
        self.assertEqual(method, "raw-author-year-or-unsegmented")
        self.assertEqual(confidence, "MEDIUM")

    def test_strict_chain_discards_implausible_number_noise(self) -> None:
        text = """
[20] unrelated numbered line
[2] B. Beta, Journal B 2, 20 (2020).
[3] C. Gamma, Journal C 3, 30 (2021).
[4] D. Delta, Journal D 4, 40 (2022).
[5] E. Epsilon, Journal E 5, 50 (2023).
[90] unrelated trailing marker
"""
        entries, method, confidence = segment_reference_entries(text)
        self.assertEqual(method, "numbered-punctuated")
        self.assertEqual(confidence, "HIGH")
        self.assertEqual([entry.ordinal for entry in entries], [2, 3, 4, 5])

    def test_parenthesized_main_reference_keeps_subreferences_together(self) -> None:
        text = """
(8) (a) A. Alpha, Journal A 1, 10 (2018). (b) A. Alpha, Journal B 2, 20 (2019).
(9) (a) B. Beta, Journal C 3, 30 (2020). (b) B. Beta, Journal D 4, 40 (2021).
(10) C. Gamma, Journal E 5, 50 (2022).
"""
        entries, method, confidence = segment_reference_entries(text)
        self.assertEqual(method, "numbered-parenthesized")
        self.assertEqual(confidence, "HIGH")
        self.assertEqual([entry.ordinal for entry in entries], [8, 9, 10])
        self.assertIn("(b) A. Alpha", entries[0].raw_text)

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

    def test_implicit_tail_bibliography_supports_multiline_entry_starts(self) -> None:
        pages = [
            "Title\nIntroduction and body text.",
            "Methods\nMore body text.",
            "Discussion\nFinal discussion paragraph.",
            """[1]
A. Alpha, Journal A 1, 10 (2010).
[2]
B. Beta, Journal B 2, 20 (2011).
[3]
C. Gamma, Journal C 3, 30 (2012).
[4]
D. Delta, Journal D 4, 40 (2013).
[5]
E. Epsilon, Journal E 5, 50 (2014).
[6]
F. Zeta, Journal F 6, 60 (2015).
[7]
G. Eta, Journal G 7, 70 (2016).
[8]
H. Theta, Journal H 8, 80 (2017).
[9]
I. Iota, Journal I 9, 90 (2018).
""",
        ]
        section = find_reference_section(pages)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.heading, "")
        self.assertEqual(section.method, "implicit-numbered-punctuated")
        self.assertEqual([entry.ordinal for entry in section.entries], list(range(1, 10)))

    def test_short_numbered_tail_is_not_assumed_to_be_references(self) -> None:
        pages = [
            "Title\nBody",
            "Discussion\nMore body",
            "1. First conclusion\n2. Second conclusion\n3. Third conclusion\n4. Fourth conclusion\n5. Fifth conclusion",
        ]
        self.assertIsNone(find_reference_section(pages))

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
            page1.insert_text((50, 25), "Subscriber access provided by Example University", fontsize=8)
            page1.insert_text((50, 38), "Articles you may be interested in: Example Center for Methods", fontsize=8)
            page1.insert_textbox(
                PYMUPDF.Rect(50, 50, 545, 500),
                """A Synthetic Paper for Paperazzi
Ada Lovelace1 and Grace Hopper2*
1 Department of Computational Science, Example University, London, UK
2 Center for Quantum Research, Example Institute, New York, USA
* Corresponding author. E-mail: grace.hopper@example.edu

Abstract
This synthetic article exists only to exercise local PDF evidence extraction.
The discussion may center upon a difficult scientific question without naming an affiliation.
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
        self.assertFalse(any("Subscriber access provided" in span.text for span in evidence.affiliation_candidates))
        self.assertFalse(any("Articles you may be interested in" in span.text for span in evidence.affiliation_candidates))
        self.assertFalse(any("center upon" in span.text.lower() for span in evidence.affiliation_candidates))
        self.assertIsNotNone(evidence.references)
        assert evidence.references is not None
        self.assertEqual(evidence.references.confidence, "HIGH")
        self.assertEqual(len(evidence.references.entries), 3)
        self.assertEqual(evidence.references.entries[0].dois, ("10.1000/alpha",))
        self.assertEqual(evidence.references.entries[2].dois, ("10.1000/gamma",))


if __name__ == "__main__":
    unittest.main()
