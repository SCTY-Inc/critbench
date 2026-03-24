"""Chain-of-Thought quality analysis for judge responses.

Evaluates the quality of reasoning in judge explanations:
- Reasoning depth and completeness
- Logical coherence
- Evidence grounding
- Hallucination detection

Reference: https://www.ibm.com/think/topics/chain-of-thoughts
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoTAnalysis:
    """Analysis of a single chain-of-thought response."""

    reasoning_depth: float = 0.0  # 0-1: How detailed is the reasoning?
    logical_coherence: float = 0.0  # 0-1: Is reasoning internally consistent?
    evidence_grounding: float = 0.0  # 0-1: Does reasoning cite specific evidence?
    score_justification: float = 0.0  # 0-1: Does reasoning justify the score given?

    reasoning_steps: int = 0
    has_contradictions: bool = False
    uses_hedging: bool = False

    flags: list[str] = field(default_factory=list)

    @property
    def overall_quality(self) -> float:
        """Weighted average of quality dimensions."""
        weights = {
            "reasoning_depth": 0.25,
            "logical_coherence": 0.30,
            "evidence_grounding": 0.25,
            "score_justification": 0.20,
        }
        return (
            self.reasoning_depth * weights["reasoning_depth"] +
            self.logical_coherence * weights["logical_coherence"] +
            self.evidence_grounding * weights["evidence_grounding"] +
            self.score_justification * weights["score_justification"]
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "reasoning_depth": self.reasoning_depth,
            "logical_coherence": self.logical_coherence,
            "evidence_grounding": self.evidence_grounding,
            "score_justification": self.score_justification,
            "overall_quality": self.overall_quality,
            "reasoning_steps": self.reasoning_steps,
            "has_contradictions": self.has_contradictions,
            "uses_hedging": self.uses_hedging,
            "flags": self.flags,
        }


@dataclass
class CoTQualityReport:
    """Aggregate CoT quality report across all judge responses."""

    mean_quality: float = 0.0
    quality_by_model: dict[str, float] = field(default_factory=dict)
    quality_by_dimension: dict[str, float] = field(default_factory=dict)

    low_quality_responses: int = 0
    high_quality_responses: int = 0
    total_responses: int = 0

    common_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mean_quality": self.mean_quality,
            "quality_by_model": self.quality_by_model,
            "quality_by_dimension": self.quality_by_dimension,
            "low_quality_responses": self.low_quality_responses,
            "high_quality_responses": self.high_quality_responses,
            "total_responses": self.total_responses,
            "common_issues": self.common_issues,
        }


class CoTAnalyzer:
    """Analyzes chain-of-thought quality in judge responses."""

    # Patterns for analysis
    REASONING_MARKERS = [
        r'\bbecause\b', r'\bsince\b', r'\btherefore\b', r'\bthus\b',
        r'\bhowever\b', r'\balthough\b', r'\bwhile\b', r'\bconsidering\b',
        r'\bfirst\b.*\bsecond\b', r'\bfirstly\b', r'\bsecondly\b',
        r'\bfor example\b', r'\bspecifically\b', r'\bin particular\b',
    ]

    EVIDENCE_MARKERS = [
        r'\bquote\b', r'"[^"]{10,}"', r"'[^']{10,}'",
        r'\bthe response\b', r'\bthe output\b', r'\bin the text\b',
        r'\bmentions\b', r'\bstates\b', r'\bdescribes\b',
        r'\bshows\b', r'\bdemonstrates\b', r'\bindicates\b',
    ]

    HEDGING_MARKERS = [
        r'\bperhaps\b', r'\bmaybe\b', r'\bpossibly\b', r'\bmight\b',
        r'\bcould be\b', r'\bseems\b', r'\bappears\b', r'\bsomewhat\b',
    ]

    CONTRADICTION_MARKERS = [
        (r'\bhigh quality\b', r'\bpoor quality\b'),
        (r'\bexcellent\b', r'\bweak\b'),
        (r'\bconsistent\b', r'\binconsistent\b'),
        (r'\bclear\b', r'\bconfusing\b'),
    ]

    JUSTIFICATION_PATTERNS = [
        r'\bscore[sd]?\s*:?\s*\d', r'\b\d\.\d\b.*because',
        r'\bgave\s+a?\s*\d', r'\brated\s+\d', r'\bwarranting\s+a?\s*\d',
    ]

    def __init__(self, low_quality_threshold: float = 0.4, high_quality_threshold: float = 0.7):
        self.low_quality_threshold = low_quality_threshold
        self.high_quality_threshold = high_quality_threshold
        self._analyses: list[tuple] = []  # (model, dimension, analysis)

    def analyze_response(
        self,
        response: str,
        model: str | None = None,
        dimension: str | None = None,
        score_given: float | None = None,
    ) -> CoTAnalysis:
        """Analyze a single judge response for CoT quality.

        Args:
            response: Full text of judge response
            model: Judge model name
            dimension: Dimension being scored
            score_given: Score the judge assigned

        Returns:
            CoTAnalysis with quality metrics
        """
        analysis = CoTAnalysis()
        text = response.lower()

        # Reasoning depth: count reasoning markers and response length
        reasoning_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in self.REASONING_MARKERS
        )
        analysis.reasoning_steps = reasoning_count

        # Normalize by response length (expect ~1 marker per 100 chars)
        expected_markers = max(1, len(text) / 100)
        analysis.reasoning_depth = min(1.0, reasoning_count / expected_markers)

        # Evidence grounding: count evidence citations
        evidence_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in self.EVIDENCE_MARKERS
        )
        expected_evidence = max(1, len(text) / 200)
        analysis.evidence_grounding = min(1.0, evidence_count / expected_evidence)

        # Hedging detection
        hedging_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in self.HEDGING_MARKERS
        )
        analysis.uses_hedging = hedging_count > 3
        if analysis.uses_hedging:
            analysis.flags.append("Excessive hedging may indicate uncertainty")

        # Contradiction detection
        for pos_pattern, neg_pattern in self.CONTRADICTION_MARKERS:
            has_pos = bool(re.search(pos_pattern, text, re.IGNORECASE))
            has_neg = bool(re.search(neg_pattern, text, re.IGNORECASE))
            if has_pos and has_neg:
                analysis.has_contradictions = True
                analysis.flags.append(f"Potential contradiction: uses both '{pos_pattern}' and '{neg_pattern}'")
                break

        # Logical coherence (penalize contradictions and excessive hedging)
        analysis.logical_coherence = 1.0
        if analysis.has_contradictions:
            analysis.logical_coherence -= 0.4
        if analysis.uses_hedging:
            analysis.logical_coherence -= 0.2
        analysis.logical_coherence = max(0.0, analysis.logical_coherence)

        # Score justification: does the reasoning justify the numeric score?
        justification_count = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in self.JUSTIFICATION_PATTERNS
        )
        analysis.score_justification = min(1.0, justification_count / 2)

        # Additional checks
        if len(response) < 100:
            analysis.flags.append("Response too short for thorough analysis")
            analysis.reasoning_depth = min(analysis.reasoning_depth, 0.3)

        if analysis.overall_quality < self.low_quality_threshold:
            analysis.flags.append("Low quality reasoning - may need human review")

        # Store for aggregate analysis
        self._analyses.append((model, dimension, analysis))

        return analysis

    def get_report(self) -> CoTQualityReport:
        """Generate aggregate quality report."""
        report = CoTQualityReport()
        report.total_responses = len(self._analyses)

        if not self._analyses:
            return report

        # Calculate mean quality
        qualities = [a.overall_quality for _, _, a in self._analyses]
        report.mean_quality = sum(qualities) / len(qualities)

        # Count high/low quality
        report.low_quality_responses = sum(1 for q in qualities if q < self.low_quality_threshold)
        report.high_quality_responses = sum(1 for q in qualities if q >= self.high_quality_threshold)

        # Quality by model
        model_qualities: dict[str, list[float]] = {}
        for model, _, analysis in self._analyses:
            if model:
                if model not in model_qualities:
                    model_qualities[model] = []
                model_qualities[model].append(analysis.overall_quality)

        for model, quals in model_qualities.items():
            report.quality_by_model[model] = sum(quals) / len(quals)

        # Quality by dimension
        dim_qualities: dict[str, list[float]] = {}
        for _, dim, analysis in self._analyses:
            if dim:
                if dim not in dim_qualities:
                    dim_qualities[dim] = []
                dim_qualities[dim].append(analysis.overall_quality)

        for dim, quals in dim_qualities.items():
            report.quality_by_dimension[dim] = sum(quals) / len(quals)

        # Common issues
        issue_counts: dict[str, int] = {}
        for _, _, analysis in self._analyses:
            for flag in analysis.flags:
                # Normalize flag to category
                if "hedging" in flag.lower():
                    key = "Excessive hedging"
                elif "contradiction" in flag.lower():
                    key = "Contradictory statements"
                elif "short" in flag.lower():
                    key = "Insufficient reasoning"
                elif "low quality" in flag.lower():
                    key = "Low quality reasoning"
                else:
                    key = flag
                issue_counts[key] = issue_counts.get(key, 0) + 1

        # Top 5 issues
        report.common_issues = sorted(issue_counts.keys(), key=lambda k: -issue_counts[k])[:5]

        return report

    def reset(self) -> None:
        """Reset accumulated analyses."""
        self._analyses.clear()


def analyze_cot_quality(
    responses: list[dict[str, Any]],
) -> CoTQualityReport:
    """Convenience function to analyze a list of judge responses.

    Args:
        responses: List of dicts with "response", "model", "dimension" keys

    Returns:
        CoTQualityReport with aggregate quality metrics
    """
    analyzer = CoTAnalyzer()

    for resp in responses:
        analyzer.analyze_response(
            response=resp.get("response", ""),
            model=resp.get("model"),
            dimension=resp.get("dimension"),
            score_given=resp.get("score"),
        )

    return analyzer.get_report()
