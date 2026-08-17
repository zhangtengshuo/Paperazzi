#!/usr/bin/env python3
"""Authoritative Phase 5 real-DB validator entry point.

Local validation is intentionally gated on the dedicated micromamba environment
named ``Paperazzi``. The implementation lives in ``_validate_phase5_impl.py``;
this wrapper prevents accidental authoritative runs from Anaconda base or another
unrelated Python environment.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.environment_contract import environment_contract  # noqa:E402


def main() -> int:
    contract = environment_contract(REPO_ROOT / "constraints" / "phase5-test.txt")
    if not contract["pass"]:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        print(
            "Refusing authoritative Phase 5 real-database validation outside the "
            "dedicated micromamba environment 'Paperazzi'. Do not modify the user's "
            "existing Anaconda/base environment. Create or repair only 'Paperazzi', "
            "then rerun this command via 'micromamba run -n Paperazzi ...'.",
            file=sys.stderr,
        )
        return 3

    runpy.run_path(
        str(REPO_ROOT / "scripts" / "_validate_phase5_impl.py"),
        run_name="__main__",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
