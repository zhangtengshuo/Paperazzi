"""Targeted correspondence extraction regressions from the Phase 5 browser findings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.local_evidence.pdf import EMAIL_RE  # noqa: E402


class CorrespondenceEmailRegressionTests(unittest.TestCase):
    def test_sentence_period_does_not_hide_second_email(self) -> None:
        text = (
            "Correspondence should be addressed to rishab.dutta@pnnl.gov "
            "and marc.illasubina@pnnl.gov."
        )
        emails = [match.group(1).lower().rstrip(".,;:)]}>\"") for match in EMAIL_RE.finditer(text)]
        self.assertEqual(
            emails,
            ["rishab.dutta@pnnl.gov", "marc.illasubina@pnnl.gov"],
        )


if __name__ == "__main__":
    unittest.main()
