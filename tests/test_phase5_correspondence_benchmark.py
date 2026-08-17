"""Tests for the real-PDF correspondence benchmark scoring gate."""
from __future__ import annotations
import importlib.util
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('score_correspondence_benchmark',ROOT/'scripts'/'score_correspondence_benchmark.py');mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

class CorrespondenceBenchmarkGateTests(unittest.TestCase):
    def test_zero_false_positive_and_high_recall_pass(self):
        payload={'cases':[{'review_status':'REVIEWED','paper_id':1,'ground_truth_corresponding_authors':['A One','B Two'],'predicted_corresponding_authors':['A One','B Two']},{'review_status':'REVIEWED','paper_id':2,'ground_truth_corresponding_authors':['C Three'],'predicted_corresponding_authors':['C Three']}]}
        r=mod.summarize(payload);self.assertTrue(r['pass']);self.assertEqual(r['fp'],0);self.assertEqual(r['fn'],0)
    def test_any_false_positive_is_hard_failure(self):
        payload={'cases':[{'review_status':'REVIEWED','paper_id':1,'ground_truth_corresponding_authors':['A One'],'predicted_corresponding_authors':['A One','Wrong Person']}]}
        r=mod.summarize(payload);self.assertFalse(r['pass']);self.assertEqual(r['fp'],1)
    def test_low_recall_fails_even_with_perfect_precision(self):
        payload={'cases':[{'review_status':'REVIEWED','paper_id':1,'ground_truth_corresponding_authors':[f'A{i}' for i in range(10)],'predicted_corresponding_authors':[f'A{i}' for i in range(8)]}]}
        r=mod.summarize(payload);self.assertFalse(r['pass']);self.assertEqual(r['fp'],0);self.assertAlmostEqual(r['recall'],.8)
if __name__=='__main__':unittest.main()
