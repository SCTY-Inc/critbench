"""Evaluation orchestration for CritBench."""
from __future__ import annotations

from critbench.evaluation import scorers
from critbench.evaluation.debate import (
    DebateOrchestrator,
    DebateResult,
    run_debate,
)
from critbench.evaluation.metrics import (
    BiasDetector,
    CoTAnalyzer,
    ReliabilityMetrics,
    analyze_cot_quality,
    calculate_icc,
    calculate_krippendorff_alpha,
    detect_biases,
)
from critbench.evaluation.preprocessing import (
    Anonymizer,
    anonymize_content,
    anonymize_transcript,
)

__all__ = [
    "scorers",
    # Metrics
    "BiasDetector",
    "detect_biases",
    "calculate_krippendorff_alpha",
    "calculate_icc",
    "ReliabilityMetrics",
    "CoTAnalyzer",
    "analyze_cot_quality",
    # Preprocessing
    "Anonymizer",
    "anonymize_content",
    "anonymize_transcript",
    # Debate
    "DebateOrchestrator",
    "DebateResult",
    "run_debate",
]
