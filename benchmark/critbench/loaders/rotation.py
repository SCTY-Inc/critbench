"""Anti-contamination scenario rotation.

Prevents benchmark gaming/memorization by:
- Rotating scenario details (names, industries, constraints)
- Tracking which scenarios have been used with which models
- Generating parameterized scenario variants

Reference: LiveBench monthly refresh approach.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from critbench.loaders import load_serialized_file


@dataclass
class RotationConfig:
    """Configuration for scenario rotation."""

    # What to rotate
    rotate_company_names: bool = True
    rotate_industries: bool = True
    rotate_audience_details: bool = True
    rotate_constraints: bool = True
    rotate_numeric_targets: bool = True

    # Tracking
    track_usage: bool = True
    max_reuse_per_model: int = 3

    # Randomization
    seed: int | None = None


@dataclass
class RotationResult:
    """Result of scenario rotation."""

    original_scenario_id: str
    rotated_scenario_id: str
    scenario: dict[str, Any]

    substitutions: dict[str, str] = field(default_factory=dict)
    rotation_seed: int = 0

    is_fresh: bool = True  # Not seen by this model before
    usage_count: int = 0


class ScenarioRotator:
    """Rotates scenario parameters to prevent contamination."""

    # Substitution pools
    COMPANY_NAMES = [
        "Nimbus", "Vertex", "Cascade", "Quantum", "Meridian",
        "Pulse", "Apex", "Nova", "Zenith", "Flux",
        "Ember", "Prism", "Orbit", "Wave", "Core",
    ]

    INDUSTRIES = [
        ("B2B SaaS", "developers"),
        ("FinTech", "finance professionals"),
        ("HealthTech", "healthcare providers"),
        ("EdTech", "educators"),
        ("E-commerce", "online shoppers"),
        ("Cybersecurity", "IT security teams"),
        ("MarTech", "marketers"),
        ("HR Tech", "HR professionals"),
        ("LegalTech", "legal professionals"),
        ("PropTech", "real estate professionals"),
    ]

    CONSTRAINTS = [
        "no hype language",
        "no superlatives",
        "no competitor mentions",
        "no price anchoring",
        "no fear-based messaging",
        "no vague claims",
        "no jargon",
        "no acronyms without explanation",
        "no passive voice",
        "no assumptions about user expertise",
    ]

    AUDIENCE_MODIFIERS = [
        ("senior", "experienced"),
        ("junior", "early-career"),
        ("enterprise", "corporate"),
        ("startup", "agile"),
        ("technical", "hands-on"),
        ("executive", "strategic"),
    ]

    def __init__(
        self,
        config: RotationConfig | None = None,
        usage_db_path: Path | None = None,
    ):
        self.config = config or RotationConfig()
        self.rng = random.Random(self.config.seed)

        # Usage tracking
        self.usage_db_path = usage_db_path
        self._usage: dict[str, dict[str, int]] = {}  # {scenario_id: {model: count}}

        if usage_db_path and usage_db_path.exists():
            self._load_usage()

    def _load_usage(self) -> None:
        """Load usage tracking from disk."""
        try:
            with open(self.usage_db_path) as f:
                self._usage = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._usage = {}

    def _save_usage(self) -> None:
        """Save usage tracking to disk."""
        if self.usage_db_path:
            self.usage_db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_db_path, "w") as f:
                json.dump(self._usage, f, indent=2)

    def record_usage(self, scenario_id: str, model: str) -> None:
        """Record that a model was evaluated on a scenario."""
        if not self.config.track_usage:
            return

        if scenario_id not in self._usage:
            self._usage[scenario_id] = {}

        self._usage[scenario_id][model] = self._usage[scenario_id].get(model, 0) + 1
        self._save_usage()

    def get_usage_count(self, scenario_id: str, model: str) -> int:
        """Get how many times a model has seen a scenario."""
        return self._usage.get(scenario_id, {}).get(model, 0)

    def is_fresh(self, scenario_id: str, model: str) -> bool:
        """Check if scenario is fresh for this model."""
        count = self.get_usage_count(scenario_id, model)
        return count < self.config.max_reuse_per_model

    def rotate(
        self,
        scenario: dict[str, Any],
        model: str | None = None,
        force_rotation: bool = False,
    ) -> RotationResult:
        """Rotate scenario parameters to create a fresh variant.

        Args:
            scenario: Original scenario dict
            model: Model being evaluated (for tracking)
            force_rotation: Force rotation even if fresh

        Returns:
            RotationResult with rotated scenario
        """
        scenario_id = scenario.get("scenario_id", "unknown")
        usage_count = self.get_usage_count(scenario_id, model) if model else 0
        is_fresh = usage_count < self.config.max_reuse_per_model

        # Generate deterministic seed from scenario + usage count
        seed_input = f"{scenario_id}:{usage_count}"
        rotation_seed = int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16)
        local_rng = random.Random(rotation_seed)

        # Deep copy scenario
        rotated = json.loads(json.dumps(scenario))
        substitutions = {}

        # Skip rotation if fresh and not forced
        if is_fresh and not force_rotation:
            return RotationResult(
                original_scenario_id=scenario_id,
                rotated_scenario_id=f"{scenario_id}_v{usage_count}",
                scenario=rotated,
                substitutions={},
                rotation_seed=rotation_seed,
                is_fresh=is_fresh,
                usage_count=usage_count,
            )

        # Rotate company name
        if self.config.rotate_company_names:
            original_name = rotated.get("brand", {}).get("name", "")
            if original_name:
                new_name = local_rng.choice(self.COMPANY_NAMES)
                rotated = self._substitute_text(rotated, original_name, new_name)
                substitutions[original_name] = new_name

        # Rotate industry
        if self.config.rotate_industries:
            new_industry, new_audience_base = local_rng.choice(self.INDUSTRIES)
            if "brand" in rotated:
                # Try to find and replace industry mentions
                current_audience = rotated["brand"].get("audience", "")
                if current_audience:
                    # Keep audience structure, change the base
                    rotated["brand"]["audience"] = self._rotate_audience(
                        current_audience, new_audience_base, local_rng
                    )

        # Rotate constraints
        if self.config.rotate_constraints and "brand" in rotated and "constraints" in rotated["brand"]:
            n_constraints = len(rotated["brand"]["constraints"])
            new_constraints = local_rng.sample(
                self.CONSTRAINTS,
                min(n_constraints, len(self.CONSTRAINTS))
            )
            rotated["brand"]["constraints"] = new_constraints

        # Rotate numeric targets
        if self.config.rotate_numeric_targets:
            rotated = self._rotate_numbers(rotated, local_rng)

        new_id = f"{scenario_id}_v{usage_count}_r{rotation_seed % 1000}"
        rotated["scenario_id"] = new_id

        return RotationResult(
            original_scenario_id=scenario_id,
            rotated_scenario_id=new_id,
            scenario=rotated,
            substitutions=substitutions,
            rotation_seed=rotation_seed,
            is_fresh=is_fresh,
            usage_count=usage_count,
        )

    def _substitute_text(
        self,
        obj: Any,
        old: str,
        new: str,
    ) -> Any:
        """Recursively substitute text in a nested structure."""
        if isinstance(obj, str):
            return obj.replace(old, new)
        elif isinstance(obj, dict):
            return {k: self._substitute_text(v, old, new) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_text(item, old, new) for item in obj]
        return obj

    def _rotate_audience(
        self,
        current: str,
        new_base: str,
        rng: random.Random,
    ) -> str:
        """Rotate audience description while keeping structure."""
        modifier, _ = rng.choice(self.AUDIENCE_MODIFIERS)
        return f"{modifier} {new_base}"

    def _rotate_numbers(
        self,
        obj: Any,
        rng: random.Random,
        variance: float = 0.2,
    ) -> Any:
        """Rotate numeric values with controlled variance."""
        if isinstance(obj, str):
            # Find and rotate percentages and numbers
            def rotate_match(m):
                try:
                    num = float(m.group(1))
                    # Apply variance
                    factor = 1 + rng.uniform(-variance, variance)
                    new_num = num * factor
                    # Format appropriately
                    if "%" in m.group(0):
                        return f"{new_num:.0f}%"
                    elif "." in m.group(1):
                        return f"{new_num:.1f}"
                    else:
                        return f"{int(new_num)}"
                except ValueError:
                    return m.group(0)

            return re.sub(r'(\d+\.?\d*)(%)?', rotate_match, obj)
        elif isinstance(obj, dict):
            return {k: self._rotate_numbers(v, rng, variance) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._rotate_numbers(item, rng, variance) for item in obj]
        return obj

    def get_fresh_scenarios(
        self,
        scenarios: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        """Filter scenarios to only those fresh for a model."""
        return [
            s for s in scenarios
            if self.is_fresh(s.get("scenario_id", ""), model)
        ]

    def get_rotation_recommendations(
        self,
        model: str,
    ) -> dict[str, Any]:
        """Get recommendations for scenario rotation for a model."""
        stale = []
        fresh = []

        for scenario_id, usage in self._usage.items():
            count = usage.get(model, 0)
            if count >= self.config.max_reuse_per_model:
                stale.append({"scenario_id": scenario_id, "usage_count": count})
            else:
                fresh.append({"scenario_id": scenario_id, "usage_count": count})

        return {
            "model": model,
            "stale_scenarios": stale,
            "fresh_scenarios": fresh,
            "recommendation": "rotate" if len(stale) > len(fresh) else "proceed",
        }


def get_rotated_scenario(
    scenario_path: str,
    model: str | None = None,
    **config_kwargs,
) -> tuple[dict[str, Any], RotationResult]:
    """Convenience function to load and rotate a scenario.

    Args:
        scenario_path: Path to scenario JSON or YAML
        model: Model being evaluated
        **config_kwargs: RotationConfig options

    Returns:
        Tuple of (rotated scenario, rotation result)
    """
    scenario = load_serialized_file(scenario_path)
    if not isinstance(scenario, dict):
        raise ValueError(f"Scenario file must contain an object: {scenario_path}")

    config = RotationConfig(**config_kwargs)
    rotator = ScenarioRotator(config)

    result = rotator.rotate(scenario, model)

    if model:
        rotator.record_usage(scenario.get("scenario_id", ""), model)

    return result.scenario, result
