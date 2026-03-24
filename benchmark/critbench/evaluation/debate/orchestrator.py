"""Multi-agent debate orchestrator for resolving judge disagreements.

When judges disagree significantly, this module facilitates a structured debate
where judges share reasoning and potentially revise their scores.

Research shows debate amplifies correctness vs static ensembles.
Reference: https://arxiv.org/html/2412.05579v2
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from critbench.api import ModelAPIClient


@dataclass
class DebateRound:
    """Single round of debate between judges."""

    round_number: int
    initial_scores: dict[str, float]
    arguments: dict[str, str]
    revised_scores: dict[str, float]
    score_changes: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_number,
            "initial_scores": self.initial_scores,
            "arguments": self.arguments,
            "revised_scores": self.revised_scores,
            "score_changes": self.score_changes,
        }


@dataclass
class DebateResult:
    """Result of a multi-agent debate."""

    triggered: bool = False
    trigger_reason: str = ""

    initial_scores: dict[str, float] = field(default_factory=dict)
    initial_mean: float = 0.0
    initial_spread: float = 0.0

    rounds: list[DebateRound] = field(default_factory=list)

    final_scores: dict[str, float] = field(default_factory=dict)
    final_mean: float = 0.0
    final_spread: float = 0.0

    consensus_reached: bool = False
    outcome_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "trigger_reason": self.trigger_reason,
            "initial": {
                "scores": self.initial_scores,
                "mean": self.initial_mean,
                "spread": self.initial_spread,
            },
            "rounds": [r.to_dict() for r in self.rounds],
            "final": {
                "scores": self.final_scores,
                "mean": self.final_mean,
                "spread": self.final_spread,
            },
            "consensus_reached": self.consensus_reached,
            "outcome_changed": self.outcome_changed,
        }


class DebateOrchestrator:
    """Orchestrates multi-agent debate when judges disagree."""

    def __init__(
        self,
        api_client: ModelAPIClient,
        disagreement_threshold: float = 0.3,
        confidence_threshold: float = 0.7,
        max_rounds: int = 2,
        consensus_threshold: float = 0.15,
    ):
        """Initialize debate orchestrator.

        Args:
            api_client: API client for calling judge models
            disagreement_threshold: Score spread that triggers debate
            confidence_threshold: Confidence below this triggers debate
            max_rounds: Maximum debate rounds before stopping
            consensus_threshold: Score spread considered consensus
        """
        self.api_client = api_client
        self.disagreement_threshold = disagreement_threshold
        self.confidence_threshold = confidence_threshold
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold

    def should_trigger_debate(
        self,
        scores: dict[str, float],
        confidence: float | None = None,
    ) -> tuple[bool, str]:
        """Determine if debate should be triggered.

        Args:
            scores: Dict mapping model name to score
            confidence: Optional pre-computed confidence

        Returns:
            Tuple of (should_trigger, reason)
        """
        if len(scores) < 2:
            return False, "Not enough judges"

        values = list(scores.values())
        spread = max(values) - min(values)

        if spread > self.disagreement_threshold:
            return True, f"Score spread ({spread:.2f}) exceeds threshold ({self.disagreement_threshold})"

        if confidence is not None and confidence < self.confidence_threshold:
            return True, f"Confidence ({confidence:.2f}) below threshold ({self.confidence_threshold})"

        return False, "No significant disagreement"

    def run_debate(
        self,
        dimension: str,
        scores: dict[str, float],
        reasoning: dict[str, str],
        context: str,
        models: list[str],
    ) -> DebateResult:
        """Run a multi-agent debate to resolve disagreement.

        Args:
            dimension: Dimension being scored
            scores: Initial scores by model
            reasoning: Initial reasoning by model
            context: Original evaluation context
            models: List of judge models

        Returns:
            DebateResult with final scores and debate transcript
        """
        result = DebateResult(
            initial_scores=scores.copy(),
            initial_mean=statistics.mean(scores.values()),
            initial_spread=max(scores.values()) - min(scores.values()),
        )

        # Check if debate should trigger
        should_trigger, reason = self.should_trigger_debate(scores)
        result.triggered = should_trigger
        result.trigger_reason = reason

        if not should_trigger:
            result.final_scores = scores.copy()
            result.final_mean = result.initial_mean
            result.final_spread = result.initial_spread
            return result

        current_scores = scores.copy()
        current_reasoning = reasoning.copy()

        for round_num in range(1, self.max_rounds + 1):
            round_result = self._run_debate_round(
                round_num=round_num,
                dimension=dimension,
                scores=current_scores,
                reasoning=current_reasoning,
                context=context,
                models=models,
            )

            result.rounds.append(round_result)
            current_scores = round_result.revised_scores.copy()
            current_reasoning = round_result.arguments.copy()

            # Check if consensus reached
            spread = max(current_scores.values()) - min(current_scores.values())
            if spread <= self.consensus_threshold:
                result.consensus_reached = True
                break

        result.final_scores = current_scores
        result.final_mean = statistics.mean(current_scores.values())
        result.final_spread = max(current_scores.values()) - min(current_scores.values())

        # Check if outcome changed significantly
        result.outcome_changed = abs(result.final_mean - result.initial_mean) > 0.1

        return result

    def _run_debate_round(
        self,
        round_num: int,
        dimension: str,
        scores: dict[str, float],
        reasoning: dict[str, str],
        context: str,
        models: list[str],
    ) -> DebateRound:
        """Run a single round of debate."""

        # Anonymize other judges' identities
        judge_labels = {m: f"Judge {chr(ord('A') + i)}" for i, m in enumerate(models)}

        revised_scores = {}
        arguments = {}

        for model in models:
            # Build debate prompt showing other judges' views
            other_views = []
            for other_model, other_reasoning in reasoning.items():
                if other_model != model:
                    label = judge_labels[other_model]
                    score = scores[other_model]
                    other_views.append(f"{label} (score: {score:.2f}):\n{other_reasoning[:500]}")

            prompt = f"""You are participating in a multi-judge debate for the dimension: {dimension}

ORIGINAL CONTEXT:
{context[:1000]}

YOUR INITIAL ASSESSMENT:
Score: {scores[model]:.2f}
Reasoning: {reasoning[model][:500]}

OTHER JUDGES' VIEWS:
{chr(10).join(other_views)}

---

DEBATE ROUND {round_num}:
Consider the other judges' perspectives. You may:
1. Maintain your score if you believe it's correct
2. Revise your score if you find their arguments compelling
3. Provide additional reasoning to support your position

Respond with:
REVISED_SCORE: [0.0-1.0]
ARGUMENT: [Your response to other judges and justification for your score]
"""

            try:
                response = self.api_client.call_model(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=1000,
                )

                # Parse response
                text = response["response"]
                new_score = self._parse_score(text, scores[model])
                argument = self._parse_argument(text)

                revised_scores[model] = new_score
                arguments[model] = argument

            except Exception as e:
                # Keep original score on error
                revised_scores[model] = scores[model]
                arguments[model] = f"Error in debate round: {e}"

        score_changes = {
            model: revised_scores[model] - scores[model]
            for model in models
        }

        return DebateRound(
            round_number=round_num,
            initial_scores=scores.copy(),
            arguments=arguments,
            revised_scores=revised_scores,
            score_changes=score_changes,
        )

    def _parse_score(self, text: str, default: float) -> float:
        """Parse revised score from debate response."""
        import re

        patterns = [
            r'REVISED_SCORE:\s*(\d+\.?\d*)',
            r'revised\s+score[:\s]+(\d+\.?\d*)',
            r'score[:\s]+(\d+\.?\d*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    return max(0.0, min(1.0, score))
                except ValueError:
                    pass

        return default

    def _parse_argument(self, text: str) -> str:
        """Parse argument from debate response."""
        import re

        match = re.search(r'ARGUMENT:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:1000]

        # Return everything after REVISED_SCORE line
        match = re.search(r'REVISED_SCORE:[^\n]*\n(.+)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:1000]

        return text[:1000]


def run_debate(
    api_client: ModelAPIClient,
    dimension: str,
    scores: dict[str, float],
    reasoning: dict[str, str],
    context: str,
    models: list[str],
    **kwargs,
) -> DebateResult:
    """Convenience function to run a debate.

    Args:
        api_client: API client for judge calls
        dimension: Dimension being scored
        scores: Initial scores by model
        reasoning: Initial reasoning by model
        context: Evaluation context
        models: List of judge models
        **kwargs: Additional DebateOrchestrator options

    Returns:
        DebateResult
    """
    orchestrator = DebateOrchestrator(api_client, **kwargs)
    return orchestrator.run_debate(dimension, scores, reasoning, context, models)
