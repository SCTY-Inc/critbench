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
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from critbench.api import ModelAPIClient
from critbench.evaluation.scorers import (
    coherence,
    judgment,
    voice,
    originality,
    ethics,
    adaptation,
)

# Default paths
_PACKAGE_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_SCORING_CONFIG = _PACKAGE_ROOT / "configs" / "scoring.yaml"


def score(
    transcript_path: str,
    scenario_path: str,
    brand_path: Optional[str] = None,
    scoring_config_path: Optional[str] = None,
    enable_llm: bool = True,
) -> Dict[str, Any]:
    """Score a transcript against a creative scenario.

    Args:
        transcript_path: Path to JSONL transcript file.
            Format: {"turn": int, "role": "user"|"assistant", "content": str}
        scenario_path: Path to scenario JSON file.
        brand_path: Path to brand YAML file. If None, uses brand from scenario.
        scoring_config_path: Path to scoring weights YAML.
        enable_llm: Enable multi-judge LLM scoring.

    Returns:
        Dict containing:
            - overall_percentage: float (0-100)
            - overall_score: float (0-1)
            - autofail: bool
            - autofail_reasons: List[str]
            - dimension_scores: Dict with per-dimension results
            - metadata: scenario info
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

    # Initialize API client if LLM enabled
    api_client = None
    if enable_llm:
        try:
            api_client = ModelAPIClient()
        except ValueError:
            enable_llm = False

    # Score each dimension
    dimension_results = {}
    autofail_reasons = []

    # Get judge models from config
    judge_models = scoring_config.get("judging", {}).get("models", [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ])

    # Coherence
    dimension_results["coherence"] = coherence.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )

    # Judgment
    dimension_results["judgment"] = judgment.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )

    # Voice
    dimension_results["voice"] = voice.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )

    # Originality
    dimension_results["originality"] = originality.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )

    # Ethics (autofail dimension)
    dimension_results["ethics"] = ethics.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )
    if dimension_results["ethics"].get("autofail"):
        autofail_reasons.append("Dark patterns detected")

    # Adaptation
    dimension_results["adaptation"] = adaptation.score(
        transcript, scenario, brand,
        api_client=api_client,
        models=judge_models,
        allow_llm=enable_llm,
    )

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

    # Close API client
    if api_client:
        api_client.close()

    return {
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
        },
    }


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
