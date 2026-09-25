"""One-click test suite: `python script/run_tests.py` (fails when coverage drops below 80%)."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.exit(
        pytest.main(
            [
                str(ROOT / "tests"),
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
                *sys.argv[1:],
            ]
        )
    )
