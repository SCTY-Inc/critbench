"""Tests for scenario rotation module."""
import json

import pytest
from critbench.loaders.rotation import (
    RotationConfig,
    RotationResult,
    ScenarioRotator,
    get_rotated_scenario,
)


class TestScenarioRotator:
    """Tests for scenario rotation."""

    @pytest.fixture
    def sample_scenario(self):
        return {
            "scenario_id": "test_scenario_001",
            "tier": "tier_1",
            "title": "Test Campaign",
            "brand": {
                "name": "TestBrand",
                "voice": "Professional and friendly",
                "audience": "senior developers",
                "constraints": ["no hype language", "no jargon"],
            },
            "turns": [
                {
                    "turn_number": 1,
                    "user_message": "Launch TestBrand to 50% of developers",
                }
            ],
        }

    def test_rotator_init_defaults(self):
        rotator = ScenarioRotator()
        assert rotator.config.rotate_company_names is True
        assert rotator.config.max_reuse_per_model == 3

    def test_rotator_with_custom_config(self):
        config = RotationConfig(
            rotate_company_names=False,
            max_reuse_per_model=5,
        )
        rotator = ScenarioRotator(config)

        assert rotator.config.rotate_company_names is False
        assert rotator.config.max_reuse_per_model == 5

    def test_is_fresh_new_scenario(self, sample_scenario):
        rotator = ScenarioRotator()
        assert rotator.is_fresh("test_scenario_001", "model_a") is True

    def test_is_fresh_after_usage(self, sample_scenario):
        config = RotationConfig(max_reuse_per_model=2)
        rotator = ScenarioRotator(config)

        # Record usage
        rotator.record_usage("test_scenario_001", "model_a")
        rotator.record_usage("test_scenario_001", "model_a")

        assert rotator.is_fresh("test_scenario_001", "model_a") is False
        assert rotator.is_fresh("test_scenario_001", "model_b") is True

    def test_rotate_fresh_scenario_no_changes(self, sample_scenario):
        rotator = ScenarioRotator()

        result = rotator.rotate(sample_scenario, model="model_a")

        assert isinstance(result, RotationResult)
        assert result.is_fresh is True
        # Fresh scenarios don't get rotated unless forced
        assert result.scenario["brand"]["name"] == "TestBrand"

    def test_rotate_forced(self, sample_scenario):
        rotator = ScenarioRotator()

        result = rotator.rotate(sample_scenario, model="model_a", force_rotation=True)

        # Should have been rotated
        assert result.rotated_scenario_id != result.original_scenario_id
        # Company name should be changed
        assert result.scenario["brand"]["name"] != "TestBrand"

    def test_rotate_stale_scenario(self, sample_scenario):
        config = RotationConfig(max_reuse_per_model=1)
        rotator = ScenarioRotator(config)

        # Make it stale
        rotator.record_usage("test_scenario_001", "model_a")

        result = rotator.rotate(sample_scenario, model="model_a")

        assert result.is_fresh is False
        assert result.usage_count == 1
        # Should have been rotated
        assert result.scenario["brand"]["name"] != "TestBrand"

    def test_rotate_constraints(self, sample_scenario):
        config = RotationConfig(rotate_constraints=True, max_reuse_per_model=0)
        rotator = ScenarioRotator(config)

        result = rotator.rotate(sample_scenario, model="model_a")

        # Constraints should be different
        new_constraints = set(result.scenario["brand"]["constraints"])
        # At least some change expected (may have overlap)
        assert len(new_constraints) > 0

    def test_rotate_deterministic_with_seed(self, sample_scenario):
        config = RotationConfig(seed=42, max_reuse_per_model=0)
        rotator1 = ScenarioRotator(config)
        rotator2 = ScenarioRotator(config)

        # Same seed should produce same rotation
        result1 = rotator1.rotate(sample_scenario)
        result2 = rotator2.rotate(sample_scenario)

        assert result1.scenario["brand"]["name"] == result2.scenario["brand"]["name"]

    def test_get_fresh_scenarios(self, sample_scenario):
        config = RotationConfig(max_reuse_per_model=1)
        rotator = ScenarioRotator(config)

        scenarios = [
            {"scenario_id": "s1"},
            {"scenario_id": "s2"},
            {"scenario_id": "s3"},
        ]

        # Use s1 and s2 for model_a
        rotator.record_usage("s1", "model_a")
        rotator.record_usage("s2", "model_a")

        fresh = rotator.get_fresh_scenarios(scenarios, "model_a")
        assert len(fresh) == 1
        assert fresh[0]["scenario_id"] == "s3"

    def test_get_rotation_recommendations(self, sample_scenario):
        config = RotationConfig(max_reuse_per_model=2)
        rotator = ScenarioRotator(config)

        # Use scenario multiple times
        for _ in range(3):
            rotator.record_usage("s1", "model_a")

        recommendations = rotator.get_rotation_recommendations("model_a")

        assert "model" in recommendations
        assert len(recommendations["stale_scenarios"]) == 1
        assert recommendations["stale_scenarios"][0]["scenario_id"] == "s1"

    def test_rotation_result_to_dict(self, sample_scenario):
        rotator = ScenarioRotator()
        result = rotator.rotate(sample_scenario, force_rotation=True)

        # Should have proper structure
        assert "original_scenario_id" in result.__dict__
        assert "rotated_scenario_id" in result.__dict__
        assert "substitutions" in result.__dict__

    def test_substitute_text_recursive(self, sample_scenario):
        rotator = ScenarioRotator()

        # Test that substitution works on nested structures
        nested = {"a": {"b": {"c": "TestBrand is great"}}}
        result = rotator._substitute_text(nested, "TestBrand", "NewBrand")

        assert result["a"]["b"]["c"] == "NewBrand is great"

    def test_substitute_text_in_list(self, sample_scenario):
        rotator = ScenarioRotator()

        data = ["TestBrand one", "TestBrand two"]
        result = rotator._substitute_text(data, "TestBrand", "NewBrand")

        assert result == ["NewBrand one", "NewBrand two"]


class TestGetRotatedScenarioConvenience:
    """Tests for get_rotated_scenario convenience function."""

    def test_get_rotated_scenario(self, tmp_path):
        scenario = {
            "scenario_id": "convenience_test",
            "brand": {"name": "ConvBrand"},
        }

        scenario_path = tmp_path / "test_scenario.json"
        with open(scenario_path, "w") as f:
            json.dump(scenario, f)

        rotated, result = get_rotated_scenario(
            str(scenario_path),
            model="test_model",
        )

        assert isinstance(result, RotationResult)
        assert "scenario_id" in rotated
