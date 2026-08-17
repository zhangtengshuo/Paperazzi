"""Tests for the Paperazzi local micromamba environment contract."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.environment_contract import (  # noqa:E402
    active_environment_identity,
    constraint_status,
    environment_contract,
)


class PaperazziEnvironmentContractTests(unittest.TestCase):
    def test_paperazzi_environment_name_is_required(self) -> None:
        good = active_environment_identity(
            {
                "CONDA_DEFAULT_ENV": "Paperazzi",
                "CONDA_PREFIX": "/tmp/mamba/envs/Paperazzi",
                "MAMBA_ROOT_PREFIX": "/tmp/mamba",
            }
        )
        bad = active_environment_identity(
            {
                "CONDA_DEFAULT_ENV": "base",
                "CONDA_PREFIX": "/opt/anaconda3",
            }
        )
        self.assertTrue(good["name_matches"])
        self.assertTrue(good["micromamba_context_present"])
        self.assertFalse(bad["name_matches"])

    def test_environment_identity_never_exposes_mamba_paths(self) -> None:
        secret_root = "/private/user/path/micromamba-root"
        result = active_environment_identity(
            {
                "CONDA_DEFAULT_ENV": "/private/user/path/envs/Paperazzi",
                "CONDA_PREFIX": "/private/user/path/envs/Paperazzi",
                "MAMBA_ROOT_PREFIX": secret_root,
            }
        )
        rendered = repr(result)
        self.assertEqual(result["active_name"], "Paperazzi")
        self.assertNotIn(secret_root, rendered)

    def test_constraint_mismatch_blocks_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "constraints.txt"
            path.write_text("httpx==0.0.0\n", encoding="utf-8")
            constraints = constraint_status(path)
            self.assertFalse(constraints["matches"])
            contract = environment_contract(
                path,
                {
                    "CONDA_DEFAULT_ENV": "Paperazzi",
                    "CONDA_PREFIX": "/tmp/envs/Paperazzi",
                },
                expected_python=(sys.version_info.major, sys.version_info.minor),
            )
            self.assertFalse(contract["pass"])


if __name__ == "__main__":
    unittest.main()
