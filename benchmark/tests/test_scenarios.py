from __future__ import annotations

from pathlib import Path

from critbench.loaders import ScenarioLoader
from critbench.models import TierLevel

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def list_scenarios() -> list[Path]:
    paths = list(SCENARIOS_DIR.rglob("*.json"))
    paths.extend(SCENARIOS_DIR.rglob("*.yaml"))
    return sorted(paths)


def test_all_scenarios_load() -> None:
    loader = ScenarioLoader()

    for scenario_path in list_scenarios():
        scenario = loader.load(scenario_path)
        assert scenario.scenario_id
        assert scenario.title
        assert scenario.brand.name
        assert scenario.turns


def test_new_tier0_yaml_scenarios_exist_and_validate() -> None:
    loader = ScenarioLoader()

    for relative_path in ["tier0/insight_only.yaml", "tier0/revision_only.yaml"]:
        scenario = loader.load(SCENARIOS_DIR / relative_path)
        assert scenario.tier == TierLevel.TIER_0
        assert len(scenario.turns) >= 2
