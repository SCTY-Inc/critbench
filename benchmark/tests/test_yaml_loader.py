"""Tests for YAML scenario loader with inheritance support."""
import json
import tempfile
from pathlib import Path

import pytest

from critbench.loaders.yaml_loader import YAMLLoader
from critbench.loaders.scenario_loader import ScenarioLoader
from critbench.models import Scenario


def test_yaml_loader_load_yaml():
    """Test loading a basic YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a simple scenario YAML
        scenario_file = tmpdir_path / "test_scenario.yaml"
        scenario_file.write_text("""
scenario_id: test_001
tier: tier_1
title: Test Scenario
brand:
  name: TestBrand
  voice: test voice
  audience: test audience
turns: []
""")

        loader = YAMLLoader(tmpdir_path)
        data = loader.load("test_scenario.yaml")

        assert data["scenario_id"] == "test_001"
        assert data["tier"] == "tier_1"
        assert data["title"] == "Test Scenario"


def test_yaml_loader_load_json():
    """Test loading a JSON file for backward compatibility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a scenario JSON
        scenario_file = tmpdir_path / "test_scenario.json"
        scenario_data = {
            "scenario_id": "test_001",
            "tier": "tier_1",
            "title": "Test Scenario",
            "brand": {
                "name": "TestBrand",
                "voice": "test voice",
                "audience": "test audience",
            },
            "turns": [],
        }
        scenario_file.write_text(json.dumps(scenario_data))

        loader = YAMLLoader(tmpdir_path)
        data = loader.load("test_scenario.json")

        assert data["scenario_id"] == "test_001"
        assert data["tier"] == "tier_1"


def test_yaml_loader_inheritance():
    """Test YAML inheritance via extends: field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create parent scenario
        parent_file = tmpdir_path / "parent.yaml"
        parent_file.write_text("""
scenario_id: parent_001
tier: tier_1
title: Parent Scenario
brand:
  name: ParentBrand
  voice: parent voice
  audience: parent audience
  constraints:
    - constraint1
    - constraint2
""")

        # Create child scenario
        child_file = tmpdir_path / "child.yaml"
        child_file.write_text("""
extends: parent.yaml
scenario_id: child_001
title: Child Scenario
brand:
  voice: child voice
""")

        loader = YAMLLoader(tmpdir_path)
        data = loader.load("child.yaml")

        # Child should override scenario_id and title
        assert data["scenario_id"] == "child_001"
        assert data["title"] == "Child Scenario"

        # Child inherits parent tier
        assert data["tier"] == "tier_1"

        # Child overrides voice but inherits other brand fields
        assert data["brand"]["voice"] == "child voice"
        assert data["brand"]["name"] == "ParentBrand"
        assert data["brand"]["audience"] == "parent audience"
        assert data["brand"]["constraints"] == ["constraint1", "constraint2"]


def test_yaml_loader_file_not_found():
    """Test error when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        loader = YAMLLoader(tmpdir_path)

        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.yaml")


def test_yaml_loader_invalid_format():
    """Test error on unsupported file format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create an unsupported file
        bad_file = tmpdir_path / "test.txt"
        bad_file.write_text("some content")

        loader = YAMLLoader(tmpdir_path)

        with pytest.raises(ValueError, match="Unsupported file format"):
            loader.load("test.txt")


def test_scenario_loader_load_valid():
    """Test loading and validating a scenario."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a valid scenario YAML
        scenario_file = tmpdir_path / "valid.yaml"
        scenario_file.write_text("""
scenario_id: test_001
tier: tier_1
title: Test Scenario
brand:
  name: TestBrand
  voice: test voice
  audience: test audience
  constraints: []
  banned_phrases: []
turns:
  - turn_number: 1
    user_message: Test message
    stage: brief_intake
    expected_behaviors: []
    autofail_triggers: []
    rubric_criteria: []
""")

        loader = ScenarioLoader(tmpdir_path)
        scenario = loader.load("valid.yaml")

        assert isinstance(scenario, Scenario)
        assert scenario.scenario_id == "test_001"
        assert scenario.tier.value == "tier_1"
        assert len(scenario.turns) == 1


def test_scenario_loader_invalid_scenario():
    """Test error on invalid scenario data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create an invalid scenario (missing required fields)
        bad_file = tmpdir_path / "invalid.yaml"
        bad_file.write_text("""
scenario_id: test_001
# Missing tier and title
brand:
  name: TestBrand
""")

        loader = ScenarioLoader(tmpdir_path)

        with pytest.raises(ValueError):
            loader.load("invalid.yaml")


def test_scenario_loader_load_many():
    """Test loading multiple scenarios."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create multiple scenarios
        for i in range(2):
            scenario_file = tmpdir_path / f"scenario_{i}.yaml"
            scenario_file.write_text(f"""
scenario_id: test_{i:03d}
tier: tier_1
title: Test Scenario {i}
brand:
  name: TestBrand
  voice: test voice
  audience: test audience
  constraints: []
  banned_phrases: []
turns: []
""")

        loader = ScenarioLoader(tmpdir_path)
        scenarios = loader.load_many(
            [tmpdir_path / "scenario_0.yaml", tmpdir_path / "scenario_1.yaml"]
        )

        assert len(scenarios) == 2
        assert scenarios[0].scenario_id == "test_000"
        assert scenarios[1].scenario_id == "test_001"
