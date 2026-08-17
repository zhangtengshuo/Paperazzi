"""Focused tests for manual-review-only author name similarity."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from paperazzi.identity.models import AuthorNameVariant  # noqa:E402
from paperazzi.identity.similar_names import _best_review_score  # noqa:E402

def variant(raw,given,family):
    return AuthorNameVariant(author_id='X',raw_name=raw,normalized_name=raw.casefold(),given_name=given,family_name=family,initials=(given[:1]+family[:1]).upper(),search_form=raw.casefold(),variant_type='SOURCE')

class NameSimilarityReviewTests(unittest.TestCase):
    def test_structured_given_family_swap_is_high_review_candidate(self):
        left=variant('Tengshuo Zhang','Tengshuo','Zhang')
        right=variant('Zhang Tengshuo','Zhang','Tengshuo')
        score,components,_=_best_review_score([left],[right])
        self.assertEqual(score,.95);self.assertIn('given_family_order_swapped',components)
    def test_unrelated_same_initial_is_not_promoted_by_swap_rule(self):
        left=variant('Tengshuo Zhang','Tengshuo','Zhang')
        right=variant('Tao Zhang','Tao','Zhang')
        score,components,_=_best_review_score([left],[right])
        self.assertLess(score,.9);self.assertNotIn('given_family_order_swapped',components)
if __name__=='__main__':unittest.main()
