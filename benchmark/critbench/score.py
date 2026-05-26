"""Public scoring API for CritBench."""
from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._contract import evaluate_contract
from ._heuristics import assistant_responses_by_turn, score_dimension_deterministic
from ._llm_judge import (
    analyze_cot,
    collect_judge_scores,
    score_dimension_with_llm,
    score_dimension_with_verifier,
)
from .api import ModelAPIClient
from .evaluation.metrics.bias_detection import BiasDetector
from .evaluation.metrics.cot_quality import CoTAnalyzer
from .evaluation.metrics.reliability import compute_reliability
from .evaluation.preprocessing.anonymizer import Anonymizer
from .evaluation.scorers.ethics import score as score_ethics
from .loaders import ScenarioLoader, YAMLLoader, load_serialized_file
from .models import Brand, RubricCriterion, Scenario, Turn, normalize_brand_dict

_PACKAGE_ROOT = Path(__file__).parent.parent
_DEFAULT_SCORING_CONFIG = _PACKAGE_ROOT / "configs" / "scoring.yaml"
_DEFAULT_WEIGHTS = {
    "coherence": 0.25,
    "judgment": 0.20,
    "voice": 0.20,
    "originality": 0.15,
    "ethics": 0.10,
    "adaptation": 0.10,
}
_ALL_DIMENSIONS = tuple(_DEFAULT_WEIGHTS)


def score(
    transcript_path: str,
    scenario_path: str,
    brand_path: str | None = None,
    scoring_config_path: str | None = None,
    enable_llm: bool = True,
    enable_anonymization: bool = False,
    enable_bias_detection: bool = True,
    enable_reliability_metrics: bool = True,
    enable_cot_analysis: bool = False,
    enable_verifier_mode: bool = False,
    verifier_k_repeats: int = 3,
) -> dict[str, Any]:
    """Score a transcript against a CritBench scenario."""
    transcript, bad_lines = _load_transcript(transcript_path)
    scenario = ScenarioLoader().load(scenario_path)
    brand = _load_brand(brand_path, scenario)
    scoring_config = _load_scoring_config(scoring_config_path)

    api_client: ModelAPIClient | None = None
    llm_enabled = enable_llm
    if llm_enabled:
        try:
            api_client = ModelAPIClient()
        except ValueError:
            llm_enabled = False

    try:
        if enable_anonymization and llm_enabled:
            transcript, _ = Anonymizer().anonymize_transcript(transcript)

        bias_detector = BiasDetector() if enable_bias_detection else None
        cot_analyzer = CoTAnalyzer() if enable_cot_analysis else None
        judge_models = list(
            scoring_config.get("judging", {}).get(
                "models",
                ["claude-sonnet-4-20250514", "gpt-4.1", "gemini-2.0-flash"],
            )
        )

        criteria_by_dimension = _criteria_by_dimension(scenario)
        dimension_results: dict[str, dict[str, Any]] = {}
        judge_score_table: dict[str, dict[str, list[float]]] = {}

        for dimension in _ALL_DIMENSIONS:
            if dimension == "ethics":
                dimension_result = score_ethics(
                    transcript,
                    _scenario_dict(scenario),
                    _brand_dict(brand),
                    api_client=api_client,
                    models=judge_models,
                    allow_llm=llm_enabled,
                )
                dimension_result.setdefault("applicable", True)
            else:
                criteria = criteria_by_dimension.get(dimension, [])
                if not criteria:
                    dimension_result = {
                        "score": 0.0,
                        "applicable": False,
                        "status": "skipped",
                        "evidence": [f"No {dimension} rubric criteria in this scenario."],
                        "criterion_scores": {},
                    }
                else:
                    dimension_result = _score_dimension(
                        dimension=dimension,
                        transcript=transcript,
                        scenario=scenario,
                        brand=brand,
                        criteria=criteria,
                        api_client=api_client,
                        models=judge_models,
                        allow_llm=llm_enabled,
                        use_verifier=enable_verifier_mode,
                        verifier_k=verifier_k_repeats,
                    )
                    collect_judge_scores(dimension_result, dimension, judge_score_table)
                    analyze_cot(dimension_result, dimension, cot_analyzer)
            dimension_results[dimension] = dimension_result

        contract = evaluate_contract(transcript, scenario, brand)
        weights = dict(scoring_config.get("weights", _DEFAULT_WEIGHTS))
        overall, normalized_weights = _weighted_score(dimension_results, weights)

        autofail_reasons = list(contract["reasons"])
        if dimension_results["ethics"].get("autofail"):
            autofail_reasons.append("Dark patterns endorsed")

        autofail = bool(autofail_reasons)
        if autofail:
            overall = 0.0

        reliability = None
        if enable_reliability_metrics and judge_score_table:
            reliability = compute_reliability(judge_score_table, judge_models)

        bias_report = None
        if bias_detector and judge_score_table:
            for per_model in judge_score_table.values():
                for model, scores in per_model.items():
                    for value in scores:
                        bias_detector.record_scores({model: value})
            bias_report = bias_detector.analyze()

        cot_report = cot_analyzer.get_report() if cot_analyzer else None

        final_result: dict[str, Any] = {
            "overall_percentage": overall * 100,
            "overall_score": overall,
            "autofail": autofail,
            "autofail_reasons": autofail_reasons,
            "dimension_scores": dimension_results,
            "contract": contract,
            "metadata": {
                "scenario_id": scenario.scenario_id,
                "tier": scenario.tier.value,
                "brand": brand.name,
                "llm_enabled": llm_enabled,
                "anonymization_enabled": enable_anonymization,
                "weights_used": normalized_weights,
                "verifier_mode": enable_verifier_mode,
                **({"transcript_warnings": [f"line {n}: invalid JSON" for n in bad_lines]} if bad_lines else {}),
            },
        }

        if reliability:
            final_result["reliability"] = reliability.to_dict()
        if bias_report:
            final_result["bias_report"] = bias_report.to_dict()
        if cot_report:
            final_result["cot_quality"] = cot_report.to_dict()

        return final_result
    finally:
        if api_client is not None:
            api_client.close()


def score_with_rewards(
    transcript_path: str,
    scenario_path: str,
    brand_path: str | None = None,
    scoring_config_path: str | None = None,
) -> dict[str, Any]:
    """Score and return per-dimension rewards."""
    result = score(
        transcript_path=transcript_path,
        scenario_path=scenario_path,
        brand_path=brand_path,
        scoring_config_path=scoring_config_path,
    )

    rewards: dict[str, float] = {}
    for dimension in _ALL_DIMENSIONS:
        payload = result.get("dimension_scores", {}).get(dimension, {})
        score_value = payload.get("score")
        rewards[dimension] = float(score_value) if isinstance(score_value, (int, float)) else 0.0

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
    brand_path: str | None = None,
    scoring_config_path: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Score with anti-contamination scenario rotation."""
    from .loaders.rotation import RotationConfig, ScenarioRotator

    scenario = load_serialized_file(scenario_path)
    if not isinstance(scenario, dict):
        raise ValueError(f"Scenario file must contain an object: {scenario_path}")

    rotator = ScenarioRotator(RotationConfig())
    rotation_result = rotator.rotate(scenario, model)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(rotation_result.scenario, handle)
        rotated_path = handle.name

    try:
        result = score(
            transcript_path=transcript_path,
            scenario_path=rotated_path,
            brand_path=brand_path,
            scoring_config_path=scoring_config_path,
            **kwargs,
        )
        result["rotation"] = {
            "original_scenario_id": rotation_result.original_scenario_id,
            "rotated_scenario_id": rotation_result.rotated_scenario_id,
            "is_fresh": rotation_result.is_fresh,
            "usage_count": rotation_result.usage_count,
            "substitutions": rotation_result.substitutions,
        }
        rotator.record_usage(rotation_result.original_scenario_id, model)
        return result
    finally:
        os.unlink(rotated_path)


# ── internal helpers ──────────────────────────────────────────────────────────

def _load_transcript(path: str) -> tuple[list[dict[str, Any]], list[int]]:
    transcript: list[dict[str, Any]] = []
    bad_lines: list[int] = []
    with open(path) as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                transcript.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines.append(lineno)
    return transcript, bad_lines


def _load_brand(brand_path: str | None, scenario: Scenario) -> Brand:
    if not brand_path:
        return scenario.brand
    data = YAMLLoader().load(brand_path)
    return Brand.from_dict(normalize_brand_dict(data))


def _load_scoring_config(path: str | None) -> dict[str, Any]:
    config_path = path or str(_DEFAULT_SCORING_CONFIG)
    config = YAMLLoader().load(config_path)
    if not isinstance(config, dict):
        raise ValueError(f"Scoring config must contain an object: {config_path}")
    return config


def _criteria_by_dimension(scenario: Scenario) -> dict[str, list[tuple[Turn, RubricCriterion]]]:
    grouped: dict[str, list[tuple[Turn, RubricCriterion]]] = defaultdict(list)
    for turn in scenario.turns:
        for criterion in turn.rubric_criteria:
            grouped[criterion.dimension.value].append((turn, criterion))
    return grouped


def _score_dimension(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
    api_client: ModelAPIClient | None,
    models: list[str],
    allow_llm: bool,
    use_verifier: bool = False,
    verifier_k: int = 3,
) -> dict[str, Any]:
    total_points = sum(criterion.max_points for _, criterion in criteria)
    result: dict[str, Any] = {
        "score": 0.0,
        "applicable": True,
        "status": "scored",
        "criterion_scores": {},
        "evidence": [],
        "points_earned": 0.0,
        "max_points": total_points,
    }

    llm_result: dict[str, Any] | None = None
    if allow_llm and api_client is not None:
        if use_verifier:
            llm_result = score_dimension_with_verifier(
                dimension=dimension,
                transcript=transcript,
                scenario=scenario,
                brand=brand,
                criteria=criteria,
                api_client=api_client,
                models=models,
                k_repeats=verifier_k,
            )
        else:
            llm_result = score_dimension_with_llm(
                dimension=dimension,
                transcript=transcript,
                scenario=scenario,
                brand=brand,
                criteria=criteria,
                api_client=api_client,
                models=models,
            )

    if llm_result and llm_result["judge_scores"]:
        result.update(llm_result)
        return result

    if allow_llm and api_client is not None:
        result["evidence"].append("All judge calls failed; using deterministic fallback.")

    deterministic = score_dimension_deterministic(
        dimension=dimension,
        transcript=transcript,
        scenario_turns=scenario.turns,
        brand=brand,
        criteria=criteria,
    )
    fallback_evidence = result["evidence"] + deterministic.get("evidence", [])
    result.update(deterministic)
    result["evidence"] = fallback_evidence
    result["method"] = "deterministic"
    return result


def _weighted_score(
    dimension_results: dict[str, dict[str, Any]],
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    applicable = {
        dimension: float(weights.get(dimension, 0.0))
        for dimension, payload in dimension_results.items()
        if payload.get("applicable")
    }
    total_weight = sum(applicable.values())
    if total_weight <= 0:
        return 0.0, {}

    normalized = {dimension: weight / total_weight for dimension, weight in applicable.items()}
    overall = sum(
        float(dimension_results[dimension].get("score") or 0.0) * normalized[dimension]
        for dimension in normalized
    )
    return overall, normalized


def _scenario_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "tier": scenario.tier.value,
        "title": scenario.title,
        "brand": _brand_dict(scenario.brand),
        "turns": [
            {
                "turn_number": turn.turn_number,
                "stage": turn.stage.value if turn.stage else None,
                "user_message": turn.user_message,
                "expected_behaviors": turn.expected_behaviors,
                "autofail_triggers": turn.autofail_triggers,
            }
            for turn in scenario.turns
        ],
    }


def _brand_dict(brand: Brand) -> dict[str, Any]:
    return {
        "name": brand.name,
        "voice": brand.voice,
        "audience": brand.audience,
        "constraints": brand.constraints,
        "competitors": brand.competitors,
        "banned_phrases": brand.banned_phrases,
        "tone_keywords": brand.tone_keywords,
        "examples": brand.examples,
    }
