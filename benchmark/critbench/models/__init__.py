"""
Data models for CritBench scenarios, turns, and brands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TierLevel(Enum):
    """Benchmark tier levels."""
    TIER_0 = "tier_0"  # 1-2 turns, single output
    TIER_1 = "tier_1"  # 3-5 turns, brief refinement
    TIER_2 = "tier_2"  # 8-12 turns, campaign consistency
    TIER_3 = "tier_3"  # 15+ turns, longitudinal with feedback


class StageType(Enum):
    """Creative process stages."""
    BRIEF_INTAKE = "brief_intake"
    INSIGHT_GENERATION = "insight_generation"
    STRATEGY = "strategy"
    IDEA_GENERATION = "idea_generation"
    IDEA_SELECTION = "idea_selection"
    HOOK_DEVELOPMENT = "hook_development"
    EXECUTION = "execution"
    FEEDBACK = "feedback"
    REVISION = "revision"
    PRESSURE_TEST = "pressure_test"


class DimensionType(Enum):
    """Scoring dimensions."""
    COHERENCE = "coherence"              # insight → strategy → creative
    JUDGMENT = "judgment"                # idea selection quality
    VOICE = "voice"                      # brand consistency
    ORIGINALITY = "originality"          # non-obvious creative
    ETHICS = "ethics"                    # no dark patterns
    ADAPTATION = "adaptation"            # feedback integration


@dataclass
class Brand:
    """Brand specification for creative work."""
    name: str
    voice: str
    audience: str
    constraints: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    banned_phrases: list[str] = field(default_factory=list)
    tone_keywords: list[str] = field(default_factory=list)
    examples: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Brand:
        return cls(
            name=data["name"],
            voice=data["voice"],
            audience=data["audience"],
            constraints=data.get("constraints", []),
            competitors=data.get("competitors", []),
            banned_phrases=data.get("banned_phrases", []),
            tone_keywords=data.get("tone_keywords", []),
            examples=data.get("examples", {}),
        )


@dataclass
class RubricCriterion:
    """A single rubric criterion for scoring."""
    criterion_id: str
    description: str
    max_points: int
    dimension: DimensionType
    scoring_guide: dict[str, str]  # score -> description

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricCriterion:
        return cls(
            criterion_id=data["criterion_id"],
            description=data["description"],
            max_points=data["max_points"],
            dimension=DimensionType(data["dimension"]),
            scoring_guide=data["scoring_guide"],
        )


@dataclass
class Turn:
    """A single turn in a creative scenario."""
    turn_number: int
    user_message: str
    stage: StageType | None = None
    expected_behaviors: list[str] = field(default_factory=list)
    autofail_triggers: list[str] = field(default_factory=list)
    rubric_criteria: list[RubricCriterion] = field(default_factory=list)
    context_notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turn:
        turn_number = data.get("turn_number", data.get("t"))
        if turn_number is None:
            raise KeyError("turn_number required")

        stage = None
        if "stage" in data:
            stage = StageType(data["stage"])

        rubric_criteria = []
        for rc in data.get("rubric_criteria", []):
            rubric_criteria.append(RubricCriterion.from_dict(rc))

        return cls(
            turn_number=turn_number,
            user_message=data["user_message"],
            stage=stage,
            expected_behaviors=data.get("expected_behaviors", []),
            autofail_triggers=data.get("autofail_triggers", []),
            rubric_criteria=rubric_criteria,
            context_notes=data.get("context_notes"),
        )


@dataclass
class Scenario:
    """A complete creative test scenario."""
    scenario_id: str
    tier: TierLevel
    title: str
    brand: Brand
    turns: list[Turn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_turns(self) -> int:
        return len(self.turns)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        tier = TierLevel(data["tier"])
        brand = Brand.from_dict(data["brand"])
        turns = [Turn.from_dict(t) for t in data.get("turns", [])]

        return cls(
            scenario_id=data["scenario_id"],
            tier=tier,
            title=data["title"],
            brand=brand,
            turns=turns,
            metadata=data.get("metadata", {}),
        )
