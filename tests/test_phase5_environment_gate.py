"""Regression test for the authoritative Phase 5 environment gate."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase5EnvironmentGateTests(unittest.TestCase):
    def test_real_db_validator_refuses_non_paperazzi_environment(self) -> None:
        env = dict(os.environ)
        env["CONDA_DEFAULT_ENV"] = "definitely-not-paperazzi"
        env["CONDA_PREFIX"] = "/tmp/definitely-not-paperazzi"
        proc = subprocess.run(
            [sys.executable, "scripts/validate_phase5.py", "--db-path", "/does/not/matter.sqlite3"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("dedicated micromamba environment 'Paperazzi'", proc.stderr)
        self.assertIn('"pass": false', proc.stdout.lower())
        self.assertNotIn("FileNotFoundError", proc.stderr)


if __name__ == "__main__":
    unittest.main()
