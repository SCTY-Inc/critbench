from __future__ import annotations

import json
from pathlib import Path

import pytest
from critbench.loaders import ScenarioLoader, YAMLLoader
from critbench.models import Scenario
from critbench.score import score


def test_yaml_loader_supports_json_and_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "scenario.yaml"
    yaml_path.write_text(
        """
scenario_id: test_yaml
tier: tier_0
title: YAML Scenario
brand:
  name: TestBrand
  voice: clear
  audience: test audience
turns: []
"""
    )
    json_path = tmp_path / "scenario.json"
    json_path.write_text(
        json.dumps(
            {
                "scenario_id": "test_json",
                "tier": "tier_0",
                "title": "JSON Scenario",
                "brand": {"name": "JsonBrand", "voice": "plain", "audience": "test audience"},
                "turns": [],
            }
        )
    )

    loader = YAMLLoader(tmp_path)

    assert loader.load("scenario.yaml")["scenario_id"] == "test_yaml"
    assert loader.load("scenario.json")["scenario_id"] == "test_json"


def test_yaml_loader_resolves_inheritance(tmp_path: Path) -> None:
    parent_path = tmp_path / "parent.yaml"
    parent_path.write_text(
        """
scenario_id: parent
tier: tier_0
title: Parent
brand:
  name: ParentBrand
  voice: restrained
  audience: decision makers
  constraints:
    - no hype
turns: []
"""
    )
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        """
extends: parent.yaml
scenario_id: child
title: Child
brand:
  voice: warmer
"""
    )

    merged = YAMLLoader(tmp_path).load("child.yaml")

    assert merged["scenario_id"] == "child"
    assert merged["tier"] == "tier_0"
    assert merged["brand"]["name"] == "ParentBrand"
    assert merged["brand"]["voice"] == "warmer"
    assert merged["brand"]["constraints"] == ["no hype"]


def test_scenario_loader_returns_validated_model(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
scenario_id: validated
tier: tier_0
title: Validated
brand:
  name: TestBrand
  voice: direct
  audience: operators
  constraints: []
  banned_phrases: []
turns:
  - turn_number: 1
    stage: brief_intake
    user_message: What do you need to know?
"""
    )

    scenario = ScenarioLoader(tmp_path).load("scenario.yaml")

    assert isinstance(scenario, Scenario)
    assert scenario.scenario_id == "validated"
    assert scenario.turns[0].stage is not None


def test_score_accepts_yaml_scenarios(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
scenario_id: score_yaml
tier: tier_0
title: Score YAML
brand:
  name: TestBrand
  voice: clear and direct
  audience: test audience
  constraints: []
  banned_phrases: []
turns:
  - turn_number: 1
    stage: brief_intake
    user_message: What do you need to know?
    rubric_criteria:
      - criterion_id: brief
        description: engages with the brief
        max_points: 1
        dimension: coherence
        scoring_guide:
          "1": asks a question
          "0": no question
"""
    )
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                json.dumps({"turn": 1, "role": "user", "content": "What do you need to know?"}),
                json.dumps({"turn": 1, "role": "assistant", "content": "Who is the audience?"}),
            ]
        )
        + "\n"
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path=str(scenario_path),
        enable_llm=False,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    assert result["metadata"]["scenario_id"] == "score_yaml"


def test_yaml_loader_rejects_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        YAMLLoader(tmp_path).load("missing.yaml")
