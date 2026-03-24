"""Inter-rater reliability metrics for multi-judge evaluation.

Implements:
- Krippendorff's alpha: Reliability coefficient for ordinal/continuous data
- Intra-class correlation (ICC): Agreement among raters
- Fleiss' kappa: Multi-rater agreement for categorical data

Reference: https://arxiv.org/html/2506.13639v1
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any


@dataclass
class ReliabilityMetrics:
    """Collection of inter-rater reliability metrics."""

    krippendorff_alpha: float | None = None
    icc: float | None = None
    mean_pairwise_agreement: float | None = None

    # Per-dimension reliability
    dimension_reliability: dict[str, float] = field(default_factory=dict)

    # Flags for low reliability
    low_reliability_dimensions: list[str] = field(default_factory=list)

    # Interpretation
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "krippendorff_alpha": self.krippendorff_alpha,
            "icc": self.icc,
            "mean_pairwise_agreement": self.mean_pairwise_agreement,
            "dimension_reliability": self.dimension_reliability,
            "low_reliability_dimensions": self.low_reliability_dimensions,
            "interpretation": self.interpretation,
        }


def calculate_krippendorff_alpha(
    ratings: list[list[float | None]],
    level: str = "interval",
) -> float | None:
    """Calculate Krippendorff's alpha for reliability measurement.

    Alpha interpretation:
    - α >= 0.80: Good reliability
    - 0.67 <= α < 0.80: Acceptable for tentative conclusions
    - α < 0.67: Unreliable

    Args:
        ratings: List of rater scores, each rater is a list of scores for items.
                 None values indicate missing ratings.
        level: Measurement level - "nominal", "ordinal", or "interval"

    Returns:
        Krippendorff's alpha coefficient, or None if calculation not possible
    """
    if not ratings or len(ratings) < 2:
        return None

    n_raters = len(ratings)
    n_items = max(len(r) for r in ratings) if ratings else 0

    if n_items < 2:
        return None

    # Collect all valid ratings per item
    item_ratings: list[list[float]] = []
    for i in range(n_items):
        item_values = []
        for r in range(n_raters):
            if i < len(ratings[r]) and ratings[r][i] is not None:
                item_values.append(ratings[r][i])
        item_ratings.append(item_values)

    # Filter items with at least 2 raters
    valid_items = [vals for vals in item_ratings if len(vals) >= 2]
    if len(valid_items) < 2:
        return None

    # Calculate observed disagreement (Do)
    all_values = [v for vals in valid_items for v in vals]
    n_pairs = sum(len(vals) * (len(vals) - 1) for vals in valid_items)

    if n_pairs == 0:
        return None

    observed_disagreement = 0.0
    for vals in valid_items:
        for i, v1 in enumerate(vals):
            for j, v2 in enumerate(vals):
                if i != j:
                    if level == "nominal":
                        observed_disagreement += 0 if v1 == v2 else 1
                    elif level == "ordinal":
                        # Ordinal distance
                        all_sorted = sorted(all_values)
                        rank1 = all_sorted.index(v1)
                        rank2 = all_sorted.index(v2)
                        observed_disagreement += abs(rank1 - rank2)
                    else:  # interval
                        observed_disagreement += (v1 - v2) ** 2

    observed_disagreement /= n_pairs

    # Calculate expected disagreement (De)
    n_total = len(all_values)
    expected_disagreement = 0.0

    for v1 in all_values:
        for v2 in all_values:
            if level == "nominal":
                expected_disagreement += 0 if v1 == v2 else 1
            elif level == "ordinal":
                all_sorted = sorted(all_values)
                rank1 = all_sorted.index(v1)
                rank2 = all_sorted.index(v2)
                expected_disagreement += abs(rank1 - rank2)
            else:  # interval
                expected_disagreement += (v1 - v2) ** 2

    expected_disagreement /= (n_total * (n_total - 1))

    if expected_disagreement == 0:
        return 1.0  # Perfect agreement

    alpha = 1 - (observed_disagreement / expected_disagreement)
    return alpha


def calculate_icc(
    ratings: list[list[float]],
    icc_type: str = "ICC(2,1)",
) -> float | None:
    """Calculate Intra-class Correlation Coefficient.

    Implements ICC(2,1) - two-way random effects, single rater, absolute agreement.

    ICC interpretation:
    - ICC >= 0.90: Excellent
    - 0.75 <= ICC < 0.90: Good
    - 0.50 <= ICC < 0.75: Moderate
    - ICC < 0.50: Poor

    Args:
        ratings: List of rater scores (each rater is a list of scores)
        icc_type: Type of ICC to calculate (currently only ICC(2,1))

    Returns:
        ICC coefficient, or None if calculation not possible
    """
    if not ratings or len(ratings) < 2:
        return None

    n_raters = len(ratings)
    n_items = min(len(r) for r in ratings)

    if n_items < 2:
        return None

    # Trim to equal length
    matrix = [r[:n_items] for r in ratings]

    # Calculate means
    grand_mean = statistics.mean([v for row in matrix for v in row])
    item_means = [statistics.mean([matrix[r][i] for r in range(n_raters)]) for i in range(n_items)]
    rater_means = [statistics.mean(row) for row in matrix]

    # Calculate sum of squares
    ss_total = sum((matrix[r][i] - grand_mean) ** 2 for r in range(n_raters) for i in range(n_items))
    ss_rows = n_raters * sum((m - grand_mean) ** 2 for m in item_means)
    ss_cols = n_items * sum((m - grand_mean) ** 2 for m in rater_means)
    ss_error = ss_total - ss_rows - ss_cols

    # Mean squares
    ms_rows = ss_rows / (n_items - 1) if n_items > 1 else 0
    ms_error = ss_error / ((n_items - 1) * (n_raters - 1)) if n_items > 1 and n_raters > 1 else 0
    ms_cols = ss_cols / (n_raters - 1) if n_raters > 1 else 0

    # ICC(2,1) formula
    denominator = ms_rows + (n_raters - 1) * ms_error + (n_raters / n_items) * (ms_cols - ms_error)

    if denominator == 0:
        return None

    icc = (ms_rows - ms_error) / denominator
    return max(-1.0, min(1.0, icc))


def calculate_pairwise_agreement(
    scores_by_judge: dict[str, list[float]],
    threshold: float = 0.2,
) -> tuple[float, dict[tuple[str, str], float]]:
    """Calculate pairwise agreement between judges.

    Args:
        scores_by_judge: Dict mapping judge name to list of scores
        threshold: Maximum difference to count as agreement

    Returns:
        Tuple of (mean agreement rate, dict of pairwise agreements)
    """
    judges = list(scores_by_judge.keys())
    if len(judges) < 2:
        return 1.0, {}

    pairwise = {}
    n_items = min(len(scores_by_judge[j]) for j in judges)

    for j1, j2 in combinations(judges, 2):
        agreements = 0
        for i in range(n_items):
            if abs(scores_by_judge[j1][i] - scores_by_judge[j2][i]) <= threshold:
                agreements += 1
        pairwise[(j1, j2)] = agreements / n_items if n_items > 0 else 0

    mean_agreement = statistics.mean(pairwise.values()) if pairwise else 1.0
    return mean_agreement, pairwise


def compute_reliability(
    all_scores: dict[str, dict[str, list[float]]],
    models: list[str],
) -> ReliabilityMetrics:
    """Compute comprehensive reliability metrics for multi-judge evaluation.

    Args:
        all_scores: Dict mapping dimension to dict of {model: [scores]}
        models: List of judge model names

    Returns:
        ReliabilityMetrics with all computed metrics
    """
    metrics = ReliabilityMetrics()

    # Aggregate all scores for overall metrics
    all_ratings: list[list[float]] = []
    for model in models:
        model_scores = []
        for _dim, dim_scores in all_scores.items():
            if model in dim_scores:
                model_scores.extend(dim_scores[model])
        if model_scores:
            all_ratings.append(model_scores)

    # Calculate overall Krippendorff's alpha
    if len(all_ratings) >= 2:
        metrics.krippendorff_alpha = calculate_krippendorff_alpha(all_ratings, level="interval")

    # Calculate overall ICC
    if len(all_ratings) >= 2:
        metrics.icc = calculate_icc(all_ratings)

    # Calculate per-dimension reliability
    for dim, dim_scores in all_scores.items():
        dim_ratings = []
        for model in models:
            if model in dim_scores and dim_scores[model]:
                dim_ratings.append(dim_scores[model])

        if len(dim_ratings) >= 2:
            dim_alpha = calculate_krippendorff_alpha(dim_ratings, level="interval")
            if dim_alpha is not None:
                metrics.dimension_reliability[dim] = dim_alpha
                if dim_alpha < 0.67:
                    metrics.low_reliability_dimensions.append(dim)

    # Mean pairwise agreement
    flat_by_judge: dict[str, list[float]] = {m: [] for m in models}
    for _dim, dim_scores in all_scores.items():
        for model, scores in dim_scores.items():
            if model in flat_by_judge:
                flat_by_judge[model].extend(scores)

    if any(flat_by_judge.values()):
        metrics.mean_pairwise_agreement, _ = calculate_pairwise_agreement(flat_by_judge)

    # Interpretation
    if metrics.krippendorff_alpha is not None:
        if metrics.krippendorff_alpha >= 0.80:
            metrics.interpretation = "Good reliability - judges show strong agreement"
        elif metrics.krippendorff_alpha >= 0.67:
            metrics.interpretation = "Acceptable reliability - tentative conclusions supported"
        else:
            metrics.interpretation = "Low reliability - consider human review for disagreements"

    return metrics
