from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_forensic_correspondence_reviews.py"
SPEC = importlib.util.spec_from_file_location("forensic_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _pymupdf():
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        import fitz

        return fitz


class ForensicCorrespondenceReviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.pdf = self.root / "paper.pdf"
        pymupdf = _pymupdf()
        document = pymupdf.open()
        page1 = document.new_page()
        page1.insert_text((72, 72), "Alice Smith* and Bob Jones")
        page1.insert_text((72, 100), "* Corresponding author: Alice Smith alice@example.org")
        page2 = document.new_page()
        page2.insert_text((72, 72), "Article text. No additional author information.")
        document.save(self.pdf)
        document.close()
        digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.queue = {
            "paper_id": 10,
            "title": "Example",
            "source_authors": ["Alice Smith", "Bob Jones"],
            "selected_pdf_path": str(self.pdf),
            "selected_pdf_sha256": digest,
            "page_count": 2,
        }
        self.explicit = {
            "review_sequence": 1,
            "paper_id": 10,
            "review_status": "REVIEWED",
            "review_mode": "DIRECT_PDF_INSPECTION",
            "reviewed_pdf_sha256": digest,
            "pages_inspected": [1],
            "parser_prediction_used_for_decision": False,
            "ground_truth_correspondence_status": "EXPLICIT",
            "ground_truth_corresponding_authors": ["Alice Smith"],
            "author_header_observation": "Page 1 shows Alice Smith with an asterisk and Bob Jones without it.",
            "contact_footnote_observation": "Page 1 has an asterisk footnote explicitly naming Alice Smith as corresponding author.",
            "correspondence_evidence": [
                {
                    "page": 1,
                    "quote": "Corresponding author: Alice Smith alice@example.org",
                    "evidence_type": "EXPLICIT_WORDING",
                    "mapped_source_authors": ["Alice Smith"],
                }
            ],
            "negative_checks": [],
            "decision_rationale": "The page-1 asterisk on Alice maps directly to the explicit corresponding-author footnote.",
            "issues": [],
            "notes": "",
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def errors(self, review: dict) -> list[str]:
        return validator._validate_one(self.queue, review, 1)

    def test_valid_explicit_direct_pdf_evidence_passes(self) -> None:
        self.assertEqual([], self.errors(dict(self.explicit)))

    def test_explicit_without_evidence_fails(self) -> None:
        review = dict(self.explicit)
        review["correspondence_evidence"] = []
        self.assertTrue(any("requires correspondence_evidence" in row for row in self.errors(review)))

    def test_negative_requires_page_two_and_all_negative_checks(self) -> None:
        review = dict(self.explicit)
        review.update(
            {
                "ground_truth_correspondence_status": "NONE_EXPLICIT",
                "ground_truth_corresponding_authors": [],
                "correspondence_evidence": [],
                "negative_checks": ["CORRESPONDENCE_WORDING"],
                "decision_rationale": "I inspected the front matter but did not find a role declaration.",
            }
        )
        errors = self.errors(review)
        self.assertTrue(any("negative_checks" in row for row in errors))
        self.assertTrue(any("pages 1 and 2" in row for row in errors))

    def test_pdf_sha_mismatch_fails(self) -> None:
        review = dict(self.explicit)
        review["reviewed_pdf_sha256"] = "0" * 64
        self.assertTrue(any("reviewed_pdf_sha256" in row for row in self.errors(review)))

    def test_parser_prediction_cannot_be_used_for_decision(self) -> None:
        review = dict(self.explicit)
        review["parser_prediction_used_for_decision"] = True
        self.assertTrue(any("must be false" in row for row in self.errors(review)))

    def test_page_one_is_mandatory(self) -> None:
        review = dict(self.explicit)
        review["pages_inspected"] = [2]
        review["correspondence_evidence"] = [
            {
                "page": 2,
                "quote": "Article text",
                "evidence_type": "OTHER_EXPLICIT",
                "mapped_source_authors": ["Alice Smith"],
            }
        ]
        self.assertTrue(any("page 1 must be inspected" in row for row in self.errors(review)))

    def test_hallucinated_quote_is_rejected_when_native_text_exists(self) -> None:
        review = dict(self.explicit)
        review["correspondence_evidence"] = [
            {
                "page": 1,
                "quote": "This sentence does not occur in the PDF",
                "evidence_type": "EXPLICIT_WORDING",
                "mapped_source_authors": ["Alice Smith"],
            }
        ]
        self.assertTrue(any("quote not found" in row for row in self.errors(review)))


if __name__ == "__main__":
    unittest.main()
