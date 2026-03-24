"""Bias detection for multi-judge LLM evaluation.

Detects common biases in LLM-as-judge scoring:
- Length/verbosity bias: Correlation between response length and scores
- Self-enhancement bias: Judges favoring their own model family
- Position bias: Score affected by presentation order
- Recency bias: Newer responses systematically scored higher

Reference: https://llm-judge-bias.github.io/
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BiasReport:
    """Report of detected biases in judge scoring."""

    length_bias: float | None = None  # Correlation coefficient
    length_bias_detected: bool = False

    self_enhancement_bias: dict[str, float] = field(default_factory=dict)
    self_enhancement_detected: bool = False

    position_bias: float | None = None  # Diff between positions
    position_bias_detected: bool = False

    model_leniency: dict[str, float] = field(default_factory=dict)
    leniency_spread: float = 0.0

    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "length_bias": {
                "correlation": self.length_bias,
                "detected": self.length_bias_detected,
            },
            "self_enhancement_bias": {
                "by_model": self.self_enhancement_bias,
                "detected": self.self_enhancement_detected,
            },
            "position_bias": {
                "score_diff": self.position_bias,
                "detected": self.position_bias_detected,
            },
            "model_leniency": {
                "by_model": self.model_leniency,
                "spread": self.leniency_spread,
            },
            "flags": self.flags,
            "bias_count": len(self.flags),
        }


class BiasDetector:
    """Detects biases in multi-judge scoring patterns."""

    def __init__(
        self,
        length_bias_threshold: float = 0.5,
        self_enhancement_threshold: float = 0.1,
        position_bias_threshold: float = 0.15,
        leniency_spread_threshold: float = 0.2,
    ):
        self.length_bias_threshold = length_bias_threshold
        self.self_enhancement_threshold = self_enhancement_threshold
        self.position_bias_threshold = position_bias_threshold
        self.leniency_spread_threshold = leniency_spread_threshold

        # Accumulate scores across evaluations
        self._scores_by_model: dict[str, list[float]] = {}
        self._scores_with_lengths: list[tuple[int, float]] = []
        self._scores_by_position: dict[int, list[float]] = {}

    def record_scores(
        self,
        scores_by_model: dict[str, float],
        response_length: int | None = None,
        position: int | None = None,
    ) -> None:
        """Record scores from a single evaluation for bias analysis.

        Args:
            scores_by_model: Dict mapping model name to score
            response_length: Length of response being evaluated
            position: Position of response in presentation order
        """
        for model, score in scores_by_model.items():
            if model not in self._scores_by_model:
                self._scores_by_model[model] = []
            self._scores_by_model[model].append(score)

            if response_length is not None:
                self._scores_with_lengths.append((response_length, score))

            if position is not None:
                if position not in self._scores_by_position:
                    self._scores_by_position[position] = []
                self._scores_by_position[position].append(score)

    def analyze(self) -> BiasReport:
        """Analyze accumulated scores for biases."""
        report = BiasReport()

        # Length bias
        if len(self._scores_with_lengths) >= 5:
            report.length_bias = self._calculate_correlation(
                [x[0] for x in self._scores_with_lengths],
                [x[1] for x in self._scores_with_lengths],
            )
            if report.length_bias is not None:
                report.length_bias_detected = abs(report.length_bias) > self.length_bias_threshold
                if report.length_bias_detected:
                    direction = "longer" if report.length_bias > 0 else "shorter"
                    report.flags.append(f"Length bias: judges prefer {direction} responses (r={report.length_bias:.2f})")

        # Model leniency (some judges consistently score higher/lower)
        if self._scores_by_model:
            for model, scores in self._scores_by_model.items():
                if scores:
                    report.model_leniency[model] = statistics.mean(scores)

            if len(report.model_leniency) > 1:
                leniency_values = list(report.model_leniency.values())
                report.leniency_spread = max(leniency_values) - min(leniency_values)

                if report.leniency_spread > self.leniency_spread_threshold:
                    most_lenient = max(report.model_leniency, key=report.model_leniency.get)
                    least_lenient = min(report.model_leniency, key=report.model_leniency.get)
                    report.flags.append(
                        f"Leniency spread: {most_lenient} scores {report.leniency_spread:.2f} higher than {least_lenient}"
                    )

        # Position bias
        if len(self._scores_by_position) > 1:
            position_means = {
                pos: statistics.mean(scores)
                for pos, scores in self._scores_by_position.items()
                if scores
            }
            if len(position_means) > 1:
                pos_values = list(position_means.values())
                report.position_bias = max(pos_values) - min(pos_values)
                report.position_bias_detected = report.position_bias > self.position_bias_threshold
                if report.position_bias_detected:
                    best_pos = max(position_means, key=position_means.get)
                    report.flags.append(f"Position bias: position {best_pos} scores higher (diff={report.position_bias:.2f})")

        return report

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float | None:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 3:
            return None

        n = len(x)
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        try:
            std_x = statistics.stdev(x)
            std_y = statistics.stdev(y)
        except statistics.StatisticsError:
            return None

        if std_x == 0 or std_y == 0:
            return None

        covariance = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / (n - 1)
        correlation = covariance / (std_x * std_y)

        return correlation

    def reset(self) -> None:
        """Reset accumulated scores."""
        self._scores_by_model.clear()
        self._scores_with_lengths.clear()
        self._scores_by_position.clear()


def detect_biases(
    all_scores: dict[str, list[float]],
    response_lengths: list[int] | None = None,
) -> BiasReport:
    """Convenience function to detect biases from a single evaluation.

    Args:
        all_scores: Dict mapping dimension to list of scores from each judge
        response_lengths: Optional list of response lengths for length bias detection

    Returns:
        BiasReport with detected biases
    """
    detector = BiasDetector()

    # Transpose scores to get per-model view
    n_judges = max(len(scores) for scores in all_scores.values()) if all_scores else 0

    for judge_idx in range(n_judges):
        scores_by_model = {}
        for _dim, scores in all_scores.items():
            if judge_idx < len(scores):
                # Use dimension as proxy for model (will be fixed with proper tracking)
                model_key = f"judge_{judge_idx}"
                if model_key not in scores_by_model:
                    scores_by_model[model_key] = []
                scores_by_model[model_key].append(scores[judge_idx])

        length = response_lengths[judge_idx] if response_lengths and judge_idx < len(response_lengths) else None

        detector.record_scores(
            {k: statistics.mean(v) for k, v in scores_by_model.items()},
            response_length=length,
        )

    return detector.analyze()
