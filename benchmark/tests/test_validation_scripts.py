from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_script(relative_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, relative_path, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_minimal_exits_zero_and_prints_average():
    result = run_script("benchmark/scripts/validation/run_minimal.py", "-y")

    assert result.returncode == 0, result.stderr
    assert re.search(r"average[:\s]+([0-9.]+)", result.stdout.splitlines()[-1])


def test_run_full_exits_zero_and_prints_average():
    result = run_script("benchmark/scripts/validation/run_full.py", "-y")

    assert result.returncode == 0, result.stderr
    assert re.search(r"average[:\s]+([0-9.]+)", result.stdout.splitlines()[-1])


def test_run_minimal_dry_run_lists_scenarios():
    result = run_script("benchmark/scripts/validation/run_minimal.py", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "validation: minimal" in result.stdout
    assert "benchmark/scenarios/tier0/single_output.json" in result.stdout
