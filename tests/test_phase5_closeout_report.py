"""Regression tests for the Phase 5 closeout-report gate."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_phase5_closeout_report.py"
SPEC = importlib.util.spec_from_file_location("phase5_closeout_checker", SCRIPT)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

VALID = """
PHASE_5_STATUS = PASS
PAPERAZZI_MICROMAMBA_ENV = PASS
EXISTING_ANACONDA_ENV_MODIFIED = NO
PHASE_5_REAL_DB_SMOKE = PASS
PRODUCT_PATH_STATUS = PASS
ASGI_HARNESS_STATUS = PASS
FULL_CORPUS_AUTHOR_PROJECTION = PASS
BROWSER_SEMANTIC_SMOKE = PASS
EXTENDED_SEARCH_VALIDATION = PASS
REAL_UNAVAILABLE_PDF_VALIDATION = PASS
IDENTITY_REVIEW_PERFORMANCE_RECHECK = PASS
MEANINGFUL_WARNINGS_REVIEWED = PASS
ZOTERO_SOURCE_MODIFIED = NO
IDENTITY_PRECISION_AUDIT = NOT_RUN_OPTIONAL
IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED
"""


class Phase5CloseoutReportTests(unittest.TestCase):
    def validate(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            path.write_text(text, encoding="utf-8")
            return checker.validate_report(path)

    def test_complete_report_passes(self) -> None:
        self.assertEqual(self.validate(VALID), [])

    def test_missing_browser_pass_is_rejected(self) -> None:
        text = VALID.replace("BROWSER_SEMANTIC_SMOKE = PASS\n", "")
        errors = self.validate(text)
        self.assertTrue(any("BROWSER_SEMANTIC_SMOKE" in error for error in errors))

    def test_report_cannot_claim_pass_while_saying_browser_not_run(self) -> None:
        errors = self.validate(VALID + "\nManual browser interaction was not run.\n")
        self.assertTrue(any("contradiction" in error for error in errors))

    def test_anaconda_mutation_is_rejected(self) -> None:
        text = VALID.replace(
            "EXISTING_ANACONDA_ENV_MODIFIED = NO",
            "EXISTING_ANACONDA_ENV_MODIFIED = YES",
        )
        errors = self.validate(text)
        self.assertTrue(any("EXISTING_ANACONDA_ENV_MODIFIED" in error for error in errors))

    def test_performance_regression_is_rejected(self) -> None:
        text = VALID.replace(
            "IDENTITY_REVIEW_PERFORMANCE_CLASS = IMPROVED",
            "IDENTITY_REVIEW_PERFORMANCE_CLASS = REGRESSED",
        )
        errors = self.validate(text)
        self.assertTrue(any("IDENTITY_REVIEW_PERFORMANCE_CLASS" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
