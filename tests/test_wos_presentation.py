from __future__ import annotations

import unittest

from paperazzi.wos.presentation import apply_wos_effective_roles, compatible_person_name


class WosPresentationTests(unittest.TestCase):
    def test_name_compatibility_is_order_insensitive(self) -> None:
        self.assertTrue(compatible_person_name("Xiaoyu Xie", "Xie, Xiaoyu"))
        self.assertTrue(compatible_person_name("Haibo Ma", "Ma, Haibo"))
        self.assertTrue(compatible_person_name("Dirk M Guldi", "Guldi, Dirk M."))
        self.assertFalse(compatible_person_name("Haibo Ma", "Xiaoyu Xie"))

    def test_complete_wos_mapping_replaces_pdf_correspondence_for_presentation(self) -> None:
        paper = {
            "authors": [
                {"order_index": 0, "source_name": "Xiaoyu Xie", "roles": ["FIRST"]},
                {"order_index": 1, "source_name": "Haibo Ma", "roles": ["CORRESPONDING"]},
                {"order_index": 2, "source_name": "Ordinary Author", "roles": ["CORRESPONDING"]},
            ],
            "corresponding_authors": ["Haibo Ma", "Ordinary Author"],
        }
        wos = {
            "status": "WOS_MATCHED",
            "wos_ut": "WOS:1",
            "match_method": "DOI_EXACT",
            "record": {
                "authors": [
                    {"order_index": 0, "au_name": "Xie, XY", "full_name": "Xie, Xiaoyu"},
                    {"order_index": 1, "au_name": "Ma, HB", "full_name": "Ma, Haibo"},
                    {"order_index": 2, "au_name": "Author, O", "full_name": "Author, Ordinary"},
                ],
                "corresponding_authors": [
                    {"au_name": "Xie, XY", "full_name": "Xie, Xiaoyu"},
                    {"au_name": "Ma, HB", "full_name": "Ma, Haibo"},
                ],
            },
        }
        result = apply_wos_effective_roles(paper, wos)
        self.assertEqual(result["correspondence_resolution"]["mapping_status"], "COMPLETE")
        self.assertEqual(result["correspondence_resolution"]["effective_source"], "WOS_RP")
        self.assertIn("CORRESPONDING", result["authors"][0]["roles"])
        self.assertIn("CORRESPONDING", result["authors"][1]["roles"])
        self.assertNotIn("CORRESPONDING", result["authors"][2]["roles"])
        self.assertEqual(result["authors"][2]["source_roles"], ["CORRESPONDING"])
        self.assertEqual(result["corresponding_authors"], ["Xiaoyu Xie", "Haibo Ma"])

    def test_partial_wos_mapping_is_additive_not_destructive(self) -> None:
        paper = {
            "authors": [
                {"order_index": 0, "source_name": "Xiaoyu Xie", "roles": ["FIRST"]},
                {"order_index": 1, "source_name": "Legacy PDF Person", "roles": ["CORRESPONDING"]},
            ],
            "corresponding_authors": ["Legacy PDF Person"],
        }
        wos = {
            "status": "WOS_MATCHED",
            "wos_ut": "WOS:2",
            "record": {
                "authors": [
                    {"order_index": 0, "au_name": "Xie, XY", "full_name": "Xie, Xiaoyu"},
                    {"order_index": 1, "au_name": "Different, A", "full_name": "Different, Author"},
                    {"order_index": 2, "au_name": "Third, A", "full_name": "Third, Author"},
                ],
                "corresponding_authors": [
                    {"au_name": "Xie, XY", "full_name": "Xie, Xiaoyu"},
                ],
            },
        }
        result = apply_wos_effective_roles(paper, wos)
        self.assertEqual(result["correspondence_resolution"]["mapping_status"], "PARTIAL")
        self.assertIn("CORRESPONDING", result["authors"][0]["roles"])
        self.assertIn("CORRESPONDING", result["authors"][1]["roles"])
        self.assertEqual(result["authors"][0]["corresponding_role_source"], "WOS_RP_PARTIAL_MAP")

    def test_unmatched_wos_keeps_fallback_roles(self) -> None:
        paper = {
            "authors": [{"order_index": 0, "source_name": "A Person", "roles": ["FIRST", "CORRESPONDING"]}],
            "corresponding_authors": ["A Person"],
        }
        result = apply_wos_effective_roles(
            paper, {"status": "WOS_NOT_IN_LOCAL_CORPUS", "wos_ut": None}
        )
        self.assertEqual(result["authors"][0]["roles"], ["FIRST", "CORRESPONDING"])
        self.assertEqual(
            result["correspondence_resolution"]["effective_source"],
            "LOCAL_PDF_OR_EXISTING_PAPERAZZI",
        )


if __name__ == "__main__":
    unittest.main()
