from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from critbench.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_run_dry_run_supports_yaml_scenarios() -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "test/model",
            "--scenario",
            "benchmark/scenarios/tier0/insight_only.yaml",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Insight Generation Only - Quick Validation" in result.stdout
    assert "Turn 1" in result.stdout


def test_leaderboard_reads_saved_scores(tmp_path: Path) -> None:
    score_path = tmp_path / "tier0_insight_only" / "test-model" / "2026-03-24T00-00-00Z" / "score.json"
    score_path.parent.mkdir(parents=True)
    score_path.write_text(
        json.dumps(
            {
                "overall_percentage": 82.5,
                "dimension_scores": {
                    "coherence": {"score": 0.8},
                    "voice": {"score": 0.9},
                },
            }
        )
    )

    result = runner.invoke(app, ["leaderboard", "--results", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    assert "82.5%" in result.stdout


def test_repo_local_module_execution_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "benchmark.critbench.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CritBench creative benchmark" in result.stdout
