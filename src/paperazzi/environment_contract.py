"""Local environment contract for Paperazzi development and real-data validation.

The user's existing Anaconda/base environment is not a Paperazzi dependency target.
Local authoritative work is performed in a dedicated micromamba environment named
``Paperazzi``. GitHub Actions is separately isolated and is not required to use
micromamba.
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path
from typing import Mapping

EXPECTED_ENVIRONMENT_NAME = "Paperazzi"
EXPECTED_PYTHON = (3, 13)


def _basename(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] if normalized else None


def active_environment_identity(
    environ: Mapping[str, str] | None = None,
    *,
    expected_name: str = EXPECTED_ENVIRONMENT_NAME,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    default_name = _basename(env.get("CONDA_DEFAULT_ENV"))
    prefix_name = _basename(env.get("CONDA_PREFIX"))
    active_name = default_name or prefix_name
    return {
        "expected_name": expected_name,
        "active_name": active_name,
        "conda_default_env_name": default_name,
        "conda_prefix_name": prefix_name,
        "name_matches": active_name == expected_name or prefix_name == expected_name,
        "micromamba_context_present": bool(
            env.get("MAMBA_ROOT_PREFIX") or env.get("MAMBA_EXE")
        ),
        "creation_policy": "MUST_BE_CREATED_WITH_MICROMAMBA",
    }


def read_constraints(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        expected[name.strip()] = version.strip()
    return expected


def constraint_status(path: Path) -> dict[str, object]:
    expected = read_constraints(path)
    packages: dict[str, dict[str, object]] = {}
    for distribution, expected_version in expected.items():
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        packages[distribution] = {
            "expected": expected_version,
            "installed": installed,
            "matches": installed == expected_version,
        }
    return {
        "constraints_file": str(path),
        "matches": bool(packages)
        and all(bool(row["matches"]) for row in packages.values()),
        "packages": packages,
    }


def environment_contract(
    constraints_path: Path,
    environ: Mapping[str, str] | None = None,
    *,
    expected_name: str = EXPECTED_ENVIRONMENT_NAME,
    expected_python: tuple[int, int] = EXPECTED_PYTHON,
) -> dict[str, object]:
    identity = active_environment_identity(environ, expected_name=expected_name)
    constraints = constraint_status(constraints_path)
    actual_python = (sys.version_info.major, sys.version_info.minor)
    python_matches = actual_python == expected_python
    passed = bool(identity["name_matches"]) and python_matches and bool(
        constraints["matches"]
    )
    return {
        "pass": passed,
        "environment": identity,
        "python": {
            "expected": f"{expected_python[0]}.{expected_python[1]}",
            "actual": f"{actual_python[0]}.{actual_python[1]}",
            "matches": python_matches,
        },
        "constraints": constraints,
        "policy": {
            "local_authoritative_environment": expected_name,
            "environment_manager": "micromamba",
            "do_not_modify_existing_anaconda_environment": True,
        },
    }
