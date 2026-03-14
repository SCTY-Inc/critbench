"""Tests that all scenarios load and validate correctly."""
from pathlib import Path

import pytest

from critbench.loaders.scenario_loader import ScenarioLoader
from critbench.models import Scenario, TierLevel


def get_scenario_files():
    """Find all scenario files."""
    # Test file is in benchmark/tests, so go up to benchmark then down to scenarios
    test_dir = Path(__file__).parent
    scenarios_dir = test_dir.parent / "scenarios"

    scenario_files = []
    for yaml_file in scenarios_dir.glob("**/*.yaml"):
        scenario_files.append(yaml_file)

    # Also include JSON files if they exist
    for json_file in scenarios_dir.glob("**/*.json"):
        scenario_files.append(json_file)

    return sorted(scenario_files)


@pytest.mark.parametrize("scenario_file", get_scenario_files())
def test_scenario_loads_and_validates(scenario_file):
    """Test that each scenario file loads and validates."""
    loader = ScenarioLoader()
    scenario = loader.load(scenario_file)

    # Basic structure checks
    assert isinstance(scenario, Scenario)
    assert scenario.scenario_id
    assert scenario.tier in [TierLevel.TIER_0, TierLevel.TIER_1, TierLevel.TIER_2, TierLevel.TIER_3]
    assert scenario.title
    assert scenario.brand
    assert scenario.brand.name
    assert scenario.brand.voice
    assert scenario.brand.audience

    # Turns checks
    if scenario.tier.value in ["tier_1", "tier_2", "tier_3"]:
        assert len(scenario.turns) >= 3, f"{scenario.scenario_id}: tier {scenario.tier} should have 3+ turns"
    else:
        assert len(scenario.turns) >= 1, f"{scenario.scenario_id}: tier 0 should have at least 1 turn"

    # Check each turn
    for turn in scenario.turns:
        assert turn.turn_number >= 1
        assert turn.user_message
        # stage may be None but typically should be present
        if turn.stage:
            from critbench.models import StageType
            assert turn.stage in [
                StageType.BRIEF_INTAKE,
                StageType.INSIGHT_GENERATION,
                StageType.STRATEGY,
                StageType.IDEA_GENERATION,
                StageType.IDEA_SELECTION,
                StageType.HOOK_DEVELOPMENT,
                StageType.EXECUTION,
                StageType.FEEDBACK,
                StageType.REVISION,
                StageType.PRESSURE_TEST,
            ]


def test_scenarios_exist():
    """Test that we have the required scenarios."""
    loader = ScenarioLoader()
    test_dir = Path(__file__).parent
    scenarios_dir = test_dir.parent / "scenarios"

    # Required tier1 scenarios
    required_tier1_scenarios = [
        "tier1/campaign/saas_launch.yaml",
        "tier1/campaign/consumer_app_launch.yaml",
        "tier1/campaign/nonprofit_rebrand.yaml",
        "tier1/campaign/b2b_enterprise_launch.yaml",
    ]

    # Required tier0 scenarios
    required_tier0_scenarios = [
        "tier0/insight_only.yaml",
        "tier0/revision_only.yaml",
    ]

    for rel_path in required_tier1_scenarios:
        path = scenarios_dir / rel_path
        assert path.exists(), f"Required scenario not found: {rel_path}"
        scenario = loader.load(path)
        assert scenario.tier == TierLevel.TIER_1

    for rel_path in required_tier0_scenarios:
        path = scenarios_dir / rel_path
        assert path.exists(), f"Required scenario not found: {rel_path}"
        scenario = loader.load(path)
        assert scenario.tier == TierLevel.TIER_0


def test_scenario_has_rubric_criteria():
    """Test that all tier1+ scenarios have rubric criteria on turns."""
    loader = ScenarioLoader()
    test_dir = Path(__file__).parent
    scenarios_dir = test_dir.parent / "scenarios"

    tier1_scenarios = [
        "tier1/campaign/saas_launch.yaml",
        "tier1/campaign/consumer_app_launch.yaml",
        "tier1/campaign/nonprofit_rebrand.yaml",
        "tier1/campaign/b2b_enterprise_launch.yaml",
    ]

    for rel_path in tier1_scenarios:
        path = scenarios_dir / rel_path
        scenario = loader.load(path)

        # At least most turns should have rubric criteria
        turns_with_criteria = [t for t in scenario.turns if t.rubric_criteria]
        assert len(turns_with_criteria) > 0, f"{rel_path}: no turns have rubric criteria"


def test_scenario_saas_launch_backward_compat():
    """Test that saas_launch YAML matches JSON original."""
    loader = ScenarioLoader()
    test_dir = Path(__file__).parent
    scenarios_dir = test_dir.parent / "scenarios"

    yaml_path = scenarios_dir / "tier1/campaign/saas_launch.yaml"
    json_path = scenarios_dir / "tier1/campaign/saas_launch.json"

    yaml_scenario = loader.load(yaml_path)
    json_scenario = loader.load(json_path)

    # Both should load identically
    assert yaml_scenario.scenario_id == json_scenario.scenario_id
    assert yaml_scenario.title == json_scenario.title
    assert yaml_scenario.tier == json_scenario.tier
    assert len(yaml_scenario.turns) == len(json_scenario.turns)
    assert yaml_scenario.brand.name == json_scenario.brand.name
