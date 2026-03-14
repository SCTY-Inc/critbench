"""Tests for ScenarioRunner."""
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from critbench.models import Scenario, Brand, Turn, StageType
from critbench.runner import ScenarioRunner


@pytest.fixture
def simple_scenario():
    """Create a simple scenario for testing."""
    brand = Brand(
        name="TestBrand",
        voice="test voice",
        audience="test audience",
        constraints=["constraint1"],
        banned_phrases=["banned1"],
    )

    turn1 = Turn(
        turn_number=1,
        stage=StageType.BRIEF_INTAKE,
        user_message="First message",
    )

    turn2 = Turn(
        turn_number=2,
        stage=StageType.INSIGHT_GENERATION,
        user_message="Second message",
    )

    return Scenario(
        scenario_id="test_001",
        tier="tier_1",
        title="Test Scenario",
        brand=brand,
        turns=[turn1, turn2],
    )


def test_runner_build_system_prompt(simple_scenario):
    """Test system prompt construction."""
    runner = ScenarioRunner("test_model", simple_scenario)
    prompt = runner._build_system_prompt()

    assert "TestBrand" in prompt
    assert "test voice" in prompt
    assert "test audience" in prompt
    assert "constraint1" in prompt
    assert "banned1" in prompt


def test_runner_run_to_file(simple_scenario):
    """Test writing transcript to file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        mock_api_client = AsyncMock()
        mock_api_client.call_model = AsyncMock(
            side_effect=[
                {"response": "First response"},
                {"response": "Second response"},
            ]
        )

        runner = ScenarioRunner(
            "test_model",
            simple_scenario,
            api_client=mock_api_client,
        )

        output_file = tmpdir_path / "transcript.jsonl"
        result_path = runner.run_to_file(output_file)

        assert result_path.exists()
        assert result_path == output_file

        # Verify JSONL format
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 4

        # Verify each line is valid JSON
        for line in lines:
            data = json.loads(line)
            assert "turn" in data
            assert "role" in data
            assert "content" in data


def test_runner_run_to_file_creates_directory(simple_scenario):
    """Test that run_to_file creates missing directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        mock_api_client = AsyncMock()
        mock_api_client.call_model = AsyncMock(
            side_effect=[
                {"response": "First response"},
                {"response": "Second response"},
            ]
        )

        runner = ScenarioRunner(
            "test_model",
            simple_scenario,
            api_client=mock_api_client,
        )

        # Use nested directory that doesn't exist
        output_file = tmpdir_path / "results" / "scenario" / "model" / "transcript.jsonl"
        result_path = runner.run_to_file(output_file)

        assert result_path.exists()
        assert result_path.parent.exists()
