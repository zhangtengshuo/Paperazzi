#!/usr/bin/env python3
"""Check the mandatory local Paperazzi micromamba environment contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paperazzi.environment_contract import environment_contract  # noqa:E402


def main() -> int:
    result = environment_contract(REPO_ROOT / "constraints" / "phase5-test.txt")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["pass"]:
        return 0
    print(
        "Paperazzi local environment contract failed. Do not install or downgrade "
        "packages in the user's existing Anaconda/base environment. Create or repair "
        "the dedicated micromamba environment named 'Paperazzi' and rerun this check.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
