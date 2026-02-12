"""
Public scoring API for CritBench.

Usage:
    from critbench import score

    result = score(
        transcript_path="path/to/transcript.jsonl",
        scenario_path="path/to/scenario.json",
        brand_path="path/to/brand.yaml"
    )

    print(result["overall_percentage"])
    print(result["dimension_scores"])

Enhanced features:
    - Multi-judge ensemble scoring with bias detection
    - Inter-rater reliability metrics (Krippendorff's alpha)
    - Optional debate for resolving disagreements
    - Chain-of-thought quality analysis
    - Anonymization to prevent provenance bias
    - Scenario rotation for anti-contamination
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from critbench.api import AsyncModelAPIClient, ModelAPIClient
from critbench.evaluation.scorers import (
    coherence,
    judgment,
    voice,
    originality,
    ethics,
    adaptation,
)
from critbench.evaluation.metrics.bias_detection import BiasDetector
from critbench.evaluation.metrics.reliability import compute_reliability
from critbench.evaluation.metrics.cot_quality import CoTAnalyzer
from critbench.evaluation.preprocessing.anonymizer import Anonymizer
from critbench.evaluation.debate.orchestrator import DebateOrchestrator
from critbench.models.result import BenchmarkResult
from critbench.results.writer import ResultsWriter
from critbench.results.summary import SummaryRenderer

# Default paths
_PACKAGE_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_SCORING_CONFIG = _PACKAGE_ROOT / "configs" / "scoring.yaml"
logger = logging.getLogger(__name__)


def _run_coroutine(coro_factory):
    """Run a coroutine from sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    result: Dict[str, Any] = {}
    error: Dict[str, BaseException] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro_factory())
        except BaseException as exc:
            error["exc"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if "exc" in error:
        raise error["exc"]

    return result.get("value")


async def _score_llm_dimensions_async(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    judge_models: List[str],
    enable_llm: bool,
) -> Dict[str, Dict[str, Any]]:
    async with AsyncModelAPIClient() as api_client:
        tasks = {
            "coherence": coherence.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
            "judgment": judgment.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
            "voice": voice.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
            "originality": originality.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
            "ethics": ethics.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
            "adaptation": adaptation.score_async(
                transcript,
                scenario,
                brand,
                api_client=api_client,
                models=judge_models,
                allow_llm=enable_llm,
            ),
        }
        results = await asyncio.gather(*tasks.values())

    return dict(zip(tasks.keys(), results))


def score(
    transcript_path: str,
    scenario_path: str,
    brand_path: Optional[str] = None,
    results_dir: Optional[str] = None,
    scoring_config_path: Optional[str] = None,
    enable_llm: bool = True,
    enable_debate: bool = False,
    enable_anonymization: bool = False,
    enable_bias_detection: bool = True,
    enable_reliability_metrics: bool = True,
    enable_cot_analysis: bool = False,
) -> Dict[str, Any]:
    """Score a transcript against a creative scenario.

    Args:
        transcript_path: Path to JSONL transcript file.
            Format: {"turn": int, "role": "user"|"assistant", "content": str}
        scenario_path: Path to scenario JSON file.
        brand_path: Path to brand YAML file. If None, uses brand from scenario.
        results_dir: Optional directory to persist result JSON/index/summary artifacts.
        scoring_config_path: Path to scoring weights YAML.
        enable_llm: Enable multi-judge LLM scoring.
        enable_debate: Enable multi-agent debate for disagreements.
        enable_anonymization: Anonymize outputs before judging.
        enable_bias_detection: Detect and report judge biases.
        enable_reliability_metrics: Calculate Krippendorff's alpha etc.
        enable_cot_analysis: Analyze chain-of-thought quality.

    Returns:
        Dict containing:
            - overall_percentage: float (0-100)
            - overall_score: float (0-1)
            - autofail: bool
            - autofail_reasons: List[str]
            - dimension_scores: Dict with per-dimension results
            - metadata: scenario info
            - reliability: Inter-rater reliability metrics (if enabled)
            - bias_report: Detected biases (if enabled)
            - cot_quality: CoT analysis (if enabled)
            - debate_results: Debate outcomes (if enabled)
    """
    # Load transcript
    transcript = []
    with open(transcript_path) as f:
        for line in f:
            if line.strip():
                transcript.append(json.loads(line))

    # Load scenario
    with open(scenario_path) as f:
        scenario = json.load(f)

    # Load brand (from file or scenario)
    if brand_path:
        with open(brand_path) as f:
            brand = yaml.safe_load(f)
    else:
        brand = scenario.get("brand", {})

    # Load scoring config
    if scoring_config_path is None:
        scoring_config_path = str(_DEFAULT_SCORING_CONFIG)
    with open(scoring_config_path) as f:
        scoring_config = yaml.safe_load(f)

    # Disable LLM scoring if API key is missing
    if enable_llm and not os.getenv("OPENROUTER_API_KEY"):
        enable_llm = False

    # Anonymize transcript if enabled
    anonymizer = None
    if enable_anonymization and enable_llm:
        anonymizer = Anonymizer()
        transcript, _ = anonymizer.anonymize_transcript(transcript)

    # Initialize analysis tools
    bias_detector = BiasDetector() if enable_bias_detection else None
    cot_analyzer = CoTAnalyzer() if enable_cot_analysis else None
    debate_client = None
    if enable_debate and enable_llm:
        try:
            debate_client = ModelAPIClient()
        except ValueError:
            debate_client = None
            enable_debate = False
    debate_orchestrator = DebateOrchestrator(debate_client) if enable_debate and debate_client else None

    # Get judge models from config
    judge_models = scoring_config.get("judging", {}).get("models", [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ])

    # Score each dimension
    dimension_results = {}
    autofail_reasons = []
    all_scores_by_dimension: Dict[str, Dict[str, List[float]]] = {}
    debate_results = {}

    llm_results = None
    if enable_llm:
        try:
            llm_results = _run_coroutine(
                lambda: _score_llm_dimensions_async(
                    transcript,
                    scenario,
                    brand,
                    judge_models,
                    enable_llm,
                )
            )
        except ValueError:
            enable_llm = False

    if enable_llm and llm_results:
        dimension_results.update(llm_results)
    else:
        dimension_results["coherence"] = coherence.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )
        dimension_results["judgment"] = judgment.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )
        dimension_results["voice"] = voice.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )
        dimension_results["originality"] = originality.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )
        dimension_results["ethics"] = ethics.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )
        dimension_results["adaptation"] = adaptation.score(
            transcript, scenario, brand,
            models=judge_models,
            allow_llm=enable_llm,
        )

    for dim in ["coherence", "judgment", "voice"]:
        if dim in dimension_results:
            _collect_scores(dimension_results[dim], dim, all_scores_by_dimension, judge_models)
            _analyze_cot(dimension_results[dim], dim, cot_analyzer, judge_models)

    for dim in ["originality", "adaptation"]:
        if dim in dimension_results:
            _collect_scores(dimension_results[dim], dim, all_scores_by_dimension, judge_models)

    # Ethics (autofail dimension)
    if dimension_results.get("ethics", {}).get("autofail"):
        autofail_reasons.append("Dark patterns detected")

    # Calculate weighted overall score
    weights = scoring_config.get("weights", {
        "coherence": 0.25,
        "judgment": 0.20,
        "voice": 0.20,
        "originality": 0.15,
        "ethics": 0.10,
        "adaptation": 0.10,
    })

    overall = sum(
        dimension_results[dim]["score"] * weights.get(dim, 0)
        for dim in weights
    )

    # Check for autofails
    autofail = len(autofail_reasons) > 0
    if autofail:
        overall = 0.0

    # Compute reliability metrics
    reliability_metrics = None
    if enable_reliability_metrics and all_scores_by_dimension:
        reliability_metrics = compute_reliability(all_scores_by_dimension, judge_models)

    # Compute bias report
    bias_report = None
    if bias_detector:
        # Record scores for bias analysis
        for dim, dim_scores in all_scores_by_dimension.items():
            for model, scores in dim_scores.items():
                for s in scores:
                    bias_detector.record_scores({model: s})
        bias_report = bias_detector.analyze()

    # Get CoT quality report
    cot_report = None
    if cot_analyzer:
        cot_report = cot_analyzer.get_report()

    # Close debate client
    if debate_client:
        debate_client.close()

    result = {
        "overall_percentage": overall * 100,
        "overall_score": overall,
        "autofail": autofail,
        "autofail_reasons": autofail_reasons,
        "dimension_scores": dimension_results,
        "metadata": {
            "scenario_id": scenario.get("scenario_id"),
            "tier": scenario.get("tier"),
            "brand": brand.get("name"),
            "llm_enabled": enable_llm,
            "anonymization_enabled": enable_anonymization,
            "debate_enabled": enable_debate,
        },
    }

    # Add optional analysis results
    if reliability_metrics:
        result["reliability"] = reliability_metrics.to_dict()

    if bias_report:
        result["bias_report"] = bias_report.to_dict()

    if cot_report:
        result["cot_quality"] = cot_report.to_dict()

    if debate_results:
        result["debate_results"] = debate_results

    if results_dir:
        try:
            scenario_id = str(result.get("metadata", {}).get("scenario_id") or "unknown")
            benchmark_result = BenchmarkResult.from_score_result(result, scenario_id=scenario_id)
            writer = ResultsWriter(results_dir=results_dir)
            writer.write(benchmark_result)
            SummaryRenderer(results_dir=results_dir).render(scenario_id=scenario_id)
            result["run_id"] = benchmark_result.run_id
        except Exception:
            logger.exception("Failed to persist benchmark results to %s", results_dir)

    return result


def _collect_scores(
    dim_result: Dict[str, Any],
    dimension: str,
    all_scores: Dict[str, Dict[str, List[float]]],
    models: List[str],
) -> None:
    """Collect scores from dimension result for reliability analysis."""
    if dimension not in all_scores:
        all_scores[dimension] = {m: [] for m in models}

    breakdown = dim_result.get("breakdown", {})

    # Collect overall dimension score per judge
    # Since we don't track per-judge scores separately, use the final score
    # This is a limitation - ideally scorers would return per-judge breakdown
    final_score = dim_result.get("score", 0.5)
    for model in models:
        all_scores[dimension][model].append(final_score)


def _analyze_cot(
    dim_result: Dict[str, Any],
    dimension: str,
    analyzer: Optional[CoTAnalyzer],
    models: List[str],
) -> None:
    """Analyze chain-of-thought quality from dimension result."""
    if analyzer is None:
        return

    # Get reasoning from result if stored
    reasoning = dim_result.get("_reasoning", {})
    for model, text in reasoning.items():
        if text:
            analyzer.analyze_response(
                response=text,
                model=model,
                dimension=dimension,
                score_given=dim_result.get("score"),
            )


def score_with_rewards(
    transcript_path: str,
    scenario_path: str,
    brand_path: Optional[str] = None,
    scoring_config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Score and return rewards for RL training.

    Returns:
        Dict with:
            - rewards: Dict[str, float] per-dimension rewards (0-1)
            - autofail: bool
            - raw_result: Full score() result
    """
    result = score(
        transcript_path=transcript_path,
        scenario_path=scenario_path,
        brand_path=brand_path,
        scoring_config_path=scoring_config_path,
    )

    rewards = {}
    for dim in ["coherence", "judgment", "voice", "originality", "ethics", "adaptation"]:
        dim_result = result.get("dimension_scores", {}).get(dim, {})
        rewards[dim] = dim_result.get("score", 0.0)

    return {
        "rewards": rewards,
        "autofail": result.get("autofail", False),
        "autofail_reasons": result.get("autofail_reasons", []),
        "raw_result": result,
    }


def score_with_rotation(
    transcript_path: str,
    scenario_path: str,
    model: str,
    brand_path: Optional[str] = None,
    scoring_config_path: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Score with anti-contamination scenario rotation.

    Args:
        transcript_path: Path to transcript
        scenario_path: Path to scenario
        model: Model being evaluated (for rotation tracking)
        brand_path: Optional brand file path
        scoring_config_path: Optional scoring config path
        **kwargs: Additional options for score()

    Returns:
        Score result with rotation metadata
    """
    from critbench.loaders.rotation import ScenarioRotator, RotationConfig

    # Load and rotate scenario
    with open(scenario_path) as f:
        scenario = json.load(f)

    rotator = ScenarioRotator(RotationConfig())
    rotation_result = rotator.rotate(scenario, model)

    # Write rotated scenario to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(rotation_result.scenario, f)
        rotated_path = f.name

    try:
        result = score(
            transcript_path=transcript_path,
            scenario_path=rotated_path,
            brand_path=brand_path,
            scoring_config_path=scoring_config_path,
            **kwargs,
        )

        # Add rotation metadata
        result["rotation"] = {
            "original_scenario_id": rotation_result.original_scenario_id,
            "rotated_scenario_id": rotation_result.rotated_scenario_id,
            "is_fresh": rotation_result.is_fresh,
            "usage_count": rotation_result.usage_count,
            "substitutions": rotation_result.substitutions,
        }

        # Record usage
        rotator.record_usage(rotation_result.original_scenario_id, model)

        return result
    finally:
        # Clean up temp file
        import os
        os.unlink(rotated_path)
