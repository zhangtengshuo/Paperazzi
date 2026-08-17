"""Regression tests for contact-vs-corresponding-author PDF semantics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.local_evidence.correspondence import classify_correspondence_text  # noqa: E402


class CorrespondenceSemanticTests(unittest.TestCase):
    def assert_kind(self, text: str, kind: str) -> None:
        self.assertEqual(classify_correspondence_text(text).kind, kind)

    def test_explicit_role_phrases_from_real_publishers(self) -> None:
        samples = [
            "* Corresponding author. E-mail address: mnaka@cheng.es.osaka-u.ac.jp (M. Nakano)",
            "a)Author to whom correspondence should be addressed: f.plasser@lboro.ac.uk.",
            "b)Authors to whom correspondence should be addressed: tak.kee@adelaide.edu.au and howesiang@ntu.edu.sg",
            "* Correspondence: carlos.crespo@case.edu; Tel.: +1-216-368-1911",
            "*Correspondence to: Tamal Chatterjee, e-mail: tchatterjee@iciq.es, Emilio Palomares, e-mail: epalomares@iciq.es",
            "* Author for correspondence. e-mail: nchl@cam.ac.uk",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assert_kind(text, "EXPLICIT_ROLE")

    def test_bare_email_and_electronic_mail_are_contact_only(self) -> None:
        samples = [
            "a)Electronic mail: werner@theochem.uni-stuttgart.de.",
            "Department of Chemistry, Example University. E-mail: alice@example.edu",
            "Received July 15, 2003; E-mail: olivucci@unisi.it",
            "a)E-mail: cxc302@case.edu",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assert_kind(text, "CONTACT_ONLY")

    def test_publisher_role_markers_without_correspondence_word(self) -> None:
        samples = [
            "1Department of Chemistry. ✉e-mail: ryan.young@northwestern.edu; m-wasielewski@northwestern.edu",
            "\n* theo.lasser@epfl.ch",
            "* Nino Russo\nnrusso@unical.it",
            "CONTACT Shadan Ghassemi Tabrizi shadan_ghassemi@yahoo.com; Carlos A. Jiménez-Hoyos cjimenezhoyo@wesleyan.edu",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assert_kind(text, "ROLE_MARKER")

    def test_scientific_use_of_corresponding_is_not_role_evidence(self) -> None:
        samples = [
            "the corresponding spin Hamiltonian is given below",
            "the corresponding absorption spectrum is unchanged",
            "the corresponding TDSE is written in the diabatic basis",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assert_kind(text, "NONE")

    def test_publisher_service_contact_is_noise_even_if_role_word_occurs(self) -> None:
        self.assert_kind(
            "Corresponding author: Alice Smith. For publisher customer service contact support@publisher.example",
            "NOISE",
        )


if __name__ == "__main__":
    unittest.main()
