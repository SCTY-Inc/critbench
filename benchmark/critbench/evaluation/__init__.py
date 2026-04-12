"""Evaluation orchestration for CritBench."""
from __future__ import annotations

from . import scorers
from .debate import (
    DebateOrchestrator,
    DebateResult,
    run_debate,
)
from .metrics import (
    BiasDetector,
    CoTAnalyzer,
    ReliabilityMetrics,
    analyze_cot_quality,
    calculate_icc,
    calculate_krippendorff_alpha,
    detect_biases,
)
from .preprocessing import (
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
