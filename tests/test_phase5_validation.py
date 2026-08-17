"""Regression tests for Phase 5 validation infrastructure."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.web.validation import atomic_write_json, compare_constraints, environment_snapshot  # noqa:E402


class Phase5ValidationInfrastructureTests(unittest.TestCase):
    def test_atomic_report_write_replaces_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            atomic_write_json(path, {"stage": "A", "status": "RUNNING"})
            atomic_write_json(path, {"stage": "A", "status": "PASS"})
            self.assertEqual(json.loads(path.read_text())["status"], "PASS")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_environment_snapshot_records_proxy_presence_not_values(self) -> None:
        secret = "http://user:secret-token@proxy.invalid:8080"
        with mock.patch.dict(os.environ, {"HTTP_PROXY": secret}, clear=False):
            snapshot = environment_snapshot()
        rendered = json.dumps(snapshot)
        self.assertTrue(snapshot["proxy_env_present"]["HTTP_PROXY"])
        self.assertNotIn(secret, rendered)
        self.assertIn("python_executable", snapshot)
        self.assertIn("packages", snapshot)

    def test_compare_constraints_reports_version_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "constraints.txt"
            path.write_text("httpx==0.0.0\n", encoding="utf-8")
            result = compare_constraints(path)
            self.assertFalse(result["matches"])
            self.assertEqual(result["packages"]["httpx"]["expected"], "0.0.0")
            self.assertIsNotNone(result["packages"]["httpx"]["installed"])


if __name__ == "__main__":
    unittest.main()
