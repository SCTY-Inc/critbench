"""Public scoring API for CritBench."""
from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

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
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "them",
    "this",
    "to",
    "we",
    "what",
    "which",
    "who",
    "with",
    "you",
    "your",
}
_HYPE_WORDS = {
    "revolutionary",
    "game-changing",
    "best-in-class",
    "industry-leading",
    "cutting-edge",
    "disruptive",
    "world-class",
    "unprecedented",
}
_REASONING_MARKERS = {"because", "since", "so that", "therefore", "which is why", "this works"}
_TRADEOFF_MARKERS = {"however", "but", "while", "tradeoff", "trade-off", "although"}
_CTA_PATTERNS = (
    "see the docs",
    "get started",
    "sign up",
    "start",
    "set up",
    "create",
    "book",
    "try",
    "learn more",
    "read more",
    "view",
    "download",
    "explore",
)
_CONVERSATIONAL_MARKERS = {"you", "we", "your", "we're", "you're", "let's", "here's"}


def score(
    transcript_path: str,
    scenario_path: str,
    brand_path: str | None = None,
    scoring_config_path: str | None = None,
    enable_llm: bool = True,
    enable_debate: bool = False,
    enable_anonymization: bool = False,
    enable_bias_detection: bool = True,
    enable_reliability_metrics: bool = True,
    enable_cot_analysis: bool = False,
) -> dict[str, Any]:
    """Score a transcript against a CritBench scenario."""
    transcript = _load_transcript(transcript_path)
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
                    )
                    _collect_real_judge_scores(dimension_result, dimension, judge_score_table)
                    _analyze_cot(dimension_result, dimension, cot_analyzer)
            dimension_results[dimension] = dimension_result

        contract = _evaluate_contract(transcript, scenario, brand)
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
                "debate_enabled": enable_debate,
                "weights_used": normalized_weights,
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

    import tempfile

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
        import os

        os.unlink(rotated_path)


def _load_transcript(path: str) -> list[dict[str, Any]]:
    transcript: list[dict[str, Any]] = []
    with open(path) as handle:
        for line in handle:
            if line.strip():
                transcript.append(json.loads(line))
    return transcript


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
        llm_result = _score_dimension_with_llm(
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

    deterministic = _score_dimension_deterministic(
        dimension=dimension,
        transcript=transcript,
        scenario=scenario,
        brand=brand,
        criteria=criteria,
    )
    fallback_evidence = result["evidence"] + deterministic.get("evidence", [])
    result.update(deterministic)
    result["evidence"] = fallback_evidence
    result["method"] = "deterministic"
    return result


def _score_dimension_with_llm(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
    api_client: ModelAPIClient,
    models: list[str],
) -> dict[str, Any]:
    prompt = _build_rubric_prompt(dimension, transcript, scenario, brand, criteria)
    per_model_points: dict[str, dict[str, float]] = {}
    per_model_scores: dict[str, float] = {}
    reasoning: dict[str, str] = {}
    evidence: list[str] = []
    total_points = sum(criterion.max_points for _, criterion in criteria)
    criteria_lookup = {criterion.criterion_id: criterion for _, criterion in criteria}

    for model in models:
        try:
            response = api_client.call_model(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1800,
            )
            analysis = response["response"]
            parsed = _parse_judge_payload(analysis, criteria_lookup)
            per_model_points[model] = parsed
            per_model_scores[model] = sum(parsed.values()) / max(total_points, 1)
            reasoning[model] = analysis
            evidence.append(f"Judge {model} scored {per_model_scores[model]:.2f}")
        except Exception as exc:
            evidence.append(f"Judge {model} failed: {exc}")

    if not per_model_scores:
        return {
            "judge_scores": {},
            "_reasoning": {},
            "evidence": evidence,
        }

    criterion_scores = {}
    points_earned = 0.0
    for criterion_id, criterion in criteria_lookup.items():
        values = [scores[criterion_id] for scores in per_model_points.values()]
        mean_points = statistics.mean(values)
        points_earned += mean_points
        criterion_scores[criterion_id] = {
            "points": mean_points,
            "max_points": criterion.max_points,
            "score": mean_points / max(criterion.max_points, 1),
            "description": criterion.description,
        }

    values = list(per_model_scores.values())
    return {
        "score": points_earned / max(total_points, 1),
        "points_earned": points_earned,
        "max_points": total_points,
        "criterion_scores": criterion_scores,
        "judge_scores": per_model_scores,
        "_reasoning": reasoning,
        "method": "llm",
        "confidence": 1.0 - (statistics.stdev(values) if len(values) > 1 else 0.0),
        "evidence": evidence,
    }


def _build_rubric_prompt(
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
) -> str:
    transcript_block = _format_transcript_for_prompt(transcript, scenario)
    criteria_block = []
    for turn, criterion in criteria:
        guide = "; ".join(
            f"{points}={description}" for points, description in sorted(criterion.scoring_guide.items())
        )
        behaviors = ", ".join(turn.expected_behaviors) if turn.expected_behaviors else "none"
        criteria_block.append(
            "\n".join(
                [
                    f"criterion_id: {criterion.criterion_id}",
                    f"turn_number: {turn.turn_number}",
                    f"stage: {turn.stage.value if turn.stage else 'unknown'}",
                    f"description: {criterion.description}",
                    f"max_points: {criterion.max_points}",
                    f"expected_behaviors: {behaviors}",
                    f"scoring_guide: {guide}",
                ]
            )
        )

    return f"""You are grading the CritBench dimension '{dimension}'.

Brand:
- name: {brand.name}
- voice: {brand.voice}
- audience: {brand.audience}
- constraints: {', '.join(brand.constraints) if brand.constraints else 'none'}
- banned_phrases: {', '.join(brand.banned_phrases) if brand.banned_phrases else 'none'}

Ordered transcript:
{transcript_block}

Score only the criteria below. Use the scoring guide exactly. Award whole-number points from 0 to max_points.

{chr(10).join(criteria_block)}

Return valid JSON only in this shape:
{{
  "criteria": [
    {{"criterion_id": "...", "points": 0, "reason": "one short sentence"}}
  ],
  "summary": "one short paragraph"
}}
"""


def _parse_judge_payload(
    response: str,
    criteria_lookup: dict[str, RubricCriterion],
) -> dict[str, float]:
    payload = _extract_json_object(response)
    items = payload.get("criteria")
    if not isinstance(items, list):
        raise ValueError("Judge response did not include criteria list")

    points_by_id: dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        criterion_id = item.get("criterion_id")
        if criterion_id not in criteria_lookup:
            continue
        raw_points = item.get("points")
        if not isinstance(raw_points, (int, float, str)):
            raise ValueError(f"Invalid points for {criterion_id}: {raw_points}")
        try:
            points = float(raw_points)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid points for {criterion_id}: {raw_points}") from exc
        max_points = criteria_lookup[criterion_id].max_points
        points_by_id[criterion_id] = max(0.0, min(float(max_points), round(points)))

    missing = [criterion_id for criterion_id in criteria_lookup if criterion_id not in points_by_id]
    if missing:
        raise ValueError(f"Judge omitted criteria: {', '.join(missing)}")

    return points_by_id


def _extract_json_object(response: str) -> dict[str, Any]:
    response = response.strip()
    if response.startswith("```"):
        response = re.sub(r"^```(?:json)?\s*|\s*```$", "", response, flags=re.DOTALL).strip()

    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))

    if not isinstance(payload, dict):
        raise ValueError("Judge response must decode to an object")
    return payload


def _score_dimension_deterministic(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
) -> dict[str, Any]:
    assistant_by_turn = _assistant_responses_by_turn(transcript)
    turn_index = {turn.turn_number: index for index, turn in enumerate(scenario.turns)}
    total_points = sum(criterion.max_points for _, criterion in criteria)
    points_earned = 0.0
    criterion_scores: dict[str, Any] = {}

    for turn, criterion in criteria:
        response = assistant_by_turn.get(turn.turn_number, "")
        previous_turn = scenario.turns[turn_index[turn.turn_number] - 1] if turn_index[turn.turn_number] > 0 else None
        previous_response = assistant_by_turn.get(previous_turn.turn_number, "") if previous_turn else ""
        next_turn = scenario.turns[turn_index[turn.turn_number] + 1] if turn_index[turn.turn_number] + 1 < len(scenario.turns) else None
        next_response = assistant_by_turn.get(next_turn.turn_number, "") if next_turn else ""

        points = _score_criterion_deterministic(
            criterion=criterion,
            turn=turn,
            response=response,
            previous_turn=previous_turn,
            previous_response=previous_response,
            next_turn=next_turn,
            next_response=next_response,
            brand=brand,
        )
        points_earned += points
        criterion_scores[criterion.criterion_id] = {
            "points": points,
            "max_points": criterion.max_points,
            "score": points / max(criterion.max_points, 1),
            "description": criterion.description,
        }

    return {
        "score": points_earned / max(total_points, 1),
        "points_earned": points_earned,
        "max_points": total_points,
        "criterion_scores": criterion_scores,
        "evidence": [f"Deterministic {dimension} rubric scoring used."],
    }


def _score_criterion_deterministic(
    *,
    criterion: RubricCriterion,
    turn: Turn,
    response: str,
    previous_turn: Turn | None,
    previous_response: str,
    next_turn: Turn | None,
    next_response: str,
    brand: Brand,
) -> float:
    kind = _criterion_kind(criterion.criterion_id)
    max_points = float(criterion.max_points)
    text = response.lower()
    previous_text = previous_response.lower()
    user_text = turn.user_message.lower()
    combined_context = " ".join(part for part in [user_text, previous_text] if part)

    if kind in {"brief_comprehension", "brief_understanding", "brief_engagement"}:
        questions = response.count("?")
        if questions >= 2:
            return max_points
        if questions == 1:
            return max_points if max_points <= 1 else max_points * 0.5
        return 0.0

    if kind == "insight_comprehension":
        return _scale_points(max_points, _blend(_overlap_ratio(text, user_text), _insight_signal(text), 0.6))

    if kind in {"creative_translation", "insight_actionability"}:
        ideas = _count_list_items(response)
        signal = max(_overlap_ratio(text, user_text), _insight_signal(text))
        if ideas >= 2 and signal >= 0.2:
            return max_points
        if ideas >= 1 or signal >= 0.15:
            return max_points * 0.5
        return 0.0

    if kind in {"insight_depth"}:
        return _scale_points(max_points, _blend(_insight_signal(text), _overlap_ratio(text, user_text), 0.65))

    if kind in {"insight_to_strategy", "insight_to_strategy_coherence", "strategy_ladder", "coherence_preservation", "differentiator_connection"}:
        overlap = _overlap_ratio(text, combined_context)
        if kind == "coherence_preservation":
            overlap = max(overlap, _has_cta(response) * 0.3 + (len(response) <= len(previous_response) + 40) * 0.2)
        return _scale_points(max_points, overlap)

    if kind == "email_clarity":
        signal = 0.0
        if any(token in text for token in {"helps", "track", "see", "understand", "plan", "family"}):
            signal += 0.5
        if _has_cta(response):
            signal += 0.2
        if len(response.split()) <= 180:
            signal += 0.3
        return _scale_points(max_points, signal)

    if kind == "voice_match":
        return _scale_points(max_points, _voice_signal(response, brand))

    if kind == "voice_compliance":
        return _scale_points(max_points, _voice_signal(response, brand))

    if kind == "tone_shift":
        signal = _conversation_signal(response)
        if previous_response and len(response.split()) <= len(previous_response.split()):
            signal = min(1.0, signal + 0.2)
        return _scale_points(max_points, signal)

    if kind == "cta_effectiveness":
        return max_points if _has_cta(response) else 0.0

    if kind == "differentiation":
        signal = 0.0
        if any(name.lower() in text for name in brand.competitors):
            signal += 0.4
        if any(phrase in text for phrase in {"instead of", "unlike", "rather than", "not surveys", "gut-feel", "guesswork", "real data"}):
            signal += 0.6
        return _scale_points(max_points, signal)

    if kind == "idea_volume":
        requested = _requested_count(turn.user_message) or 5
        idea_count = _count_list_items(response)
        return max_points if idea_count >= requested else 0.0

    if kind == "idea_range":
        idea_lines = _split_ideas(response)
        unique_ideas = len({idea[:60] for idea in idea_lines})
        if unique_ideas >= 3:
            return max_points
        if unique_ideas >= 2:
            return max_points * 0.5
        return 0.0

    if kind == "selection_reasoning":
        signal = 0.0
        if _contains_any(text, _REASONING_MARKERS):
            signal += 0.5
        if _contains_any(text, _TRADEOFF_MARKERS):
            signal += 0.2
        if _mentions_audience_or_strategy(text, combined_context):
            signal += 0.3
        return _scale_points(max_points, signal)

    if kind == "selection_quality":
        signal = 0.0
        if _contains_any(text, _REASONING_MARKERS):
            signal += 0.4
        if any(token in text for token in {"strongest", "best", "fits", "audience", "positioning", "strategy"}):
            signal += 0.3
        if _contains_any(text, _TRADEOFF_MARKERS):
            signal += 0.3
        return _scale_points(max_points, signal)

    if kind == "audience_relevance":
        signal = _mentions_audience_or_strategy(text, user_text)
        return _scale_points(max_points, signal)

    if kind == "feedback_incorporation":
        return _scale_points(max_points, _feedback_signal(turn.user_message, response, previous_response))

    return _scale_points(max_points, _overlap_ratio(text, combined_context))


def _evaluate_contract(
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
) -> dict[str, Any]:
    assistant_by_turn = _assistant_responses_by_turn(transcript)
    reasons: list[str] = []
    findings: list[str] = []

    all_responses = list(assistant_by_turn.values())
    banned = _find_phrases(all_responses, brand.banned_phrases)
    if banned:
        reasons.append(f"Banned phrases used: {', '.join(banned)}")
        findings.extend(f"banned_phrase:{phrase}" for phrase in banned)

    competitors = _find_phrases(all_responses, brand.competitors)
    if competitors:
        reasons.append(f"Competitor mentioned: {', '.join(competitors)}")
        findings.extend(f"competitor:{name}" for name in competitors)

    constraint_phrases = _forbidden_phrases_from_constraints(brand.constraints)
    forbidden = _find_phrases(all_responses, constraint_phrases)
    if forbidden:
        reasons.append(f"Brand constraint violated: {', '.join(forbidden)}")
        findings.extend(f"constraint_phrase:{phrase}" for phrase in forbidden)

    if _constraint_forbids_exclamation(brand.constraints):
        for turn in scenario.turns:
            response = assistant_by_turn.get(turn.turn_number, "")
            if response and "!" in response:
                reasons.append(f"Exclamation points used at turn {turn.turn_number}")
                findings.append(f"exclamation:turn_{turn.turn_number}")
                break

    for turn in scenario.turns:
        response = assistant_by_turn.get(turn.turn_number, "")
        if not response:
            continue
        for trigger in turn.autofail_triggers:
            if _trigger_matched(trigger, turn, response, brand):
                reasons.append(f"Turn {turn.turn_number}: {trigger}")
                findings.append(f"trigger:{trigger}")

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "autofail": bool(unique_reasons),
        "reasons": unique_reasons,
        "findings": findings,
    }


def _trigger_matched(trigger: str, turn: Turn, response: str, brand: Brand) -> bool:
    trigger_text = trigger.lower()
    response_text = response.lower()

    if "banned phrase" in trigger_text:
        return bool(_find_phrases([response], brand.banned_phrases))
    if ("jump" in trigger_text and "tactic" in trigger_text) or "without questions" in trigger_text:
        return turn.stage is not None and turn.stage.value == "brief_intake" and response.count("?") == 0
    if "fewer than" in trigger_text and "concept" in trigger_text:
        required = _requested_count(turn.user_message) or 5
        return _count_list_items(response) < required
    if "no reasoning" in trigger_text:
        return not _contains_any(response_text, _REASONING_MARKERS)
    if "no clear cta" in trigger_text or "removes cta" in trigger_text or "no cta" in trigger_text:
        return not _has_cta(response)
    if "oversells" in trigger_text or "hype" in trigger_text:
        return any(word in response_text for word in _HYPE_WORDS)
    return False


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


def _collect_real_judge_scores(
    dim_result: dict[str, Any],
    dimension: str,
    all_scores: dict[str, dict[str, list[float]]],
) -> None:
    judge_scores = dim_result.get("judge_scores") or {}
    if not judge_scores:
        return
    all_scores[dimension] = {model: [score] for model, score in judge_scores.items()}


def _analyze_cot(
    dim_result: dict[str, Any],
    dimension: str,
    analyzer: CoTAnalyzer | None,
) -> None:
    if analyzer is None:
        return
    for model, text in (dim_result.get("_reasoning") or {}).items():
        analyzer.analyze_response(
            response=text,
            model=model,
            dimension=dimension,
            score_given=dim_result.get("score"),
        )


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


def _assistant_responses_by_turn(transcript: list[dict[str, Any]]) -> dict[int, str]:
    responses: dict[int, str] = {}
    for message in transcript:
        if message.get("role") == "assistant":
            turn = int(message.get("turn", 0))
            responses[turn] = str(message.get("content", ""))
    return responses


def _format_transcript_for_prompt(transcript: list[dict[str, Any]], scenario: Scenario) -> str:
    assistant_by_turn = _assistant_responses_by_turn(transcript)
    lines = []
    for turn in scenario.turns:
        stage = turn.stage.value if turn.stage else "unknown"
        lines.append(f"Turn {turn.turn_number} [{stage}] USER: {turn.user_message}")
        lines.append(f"Turn {turn.turn_number} [{stage}] ASSISTANT: {assistant_by_turn.get(turn.turn_number, '')}")
    return "\n".join(lines)


def _criterion_kind(criterion_id: str) -> str:
    for suffix in (
        "brief_comprehension",
        "brief_understanding",
        "brief_engagement",
        "insight_comprehension",
        "creative_translation",
        "insight_actionability",
        "insight_depth",
        "insight_to_strategy_coherence",
        "insight_to_strategy",
        "differentiator_connection",
        "coherence_preservation",
        "email_clarity",
        "voice_match",
        "voice_compliance",
        "tone_shift",
        "cta_effectiveness",
        "differentiation",
        "idea_volume",
        "idea_range",
        "strategy_ladder",
        "selection_reasoning",
        "selection_quality",
        "audience_relevance",
        "feedback_incorporation",
    ):
        if criterion_id.endswith(suffix):
            return suffix
    return criterion_id


def _requested_count(text: str) -> int | None:
    match = re.search(r"\b(\d+)\b(?=\s+(?:campaign\s+)?(?:concepts?|ideas?|options?))", text.lower())
    if match:
        return int(match.group(1))
    return None


def _count_list_items(text: str) -> int:
    ideas = _split_ideas(text)
    return len(ideas)


def _split_ideas(text: str) -> list[str]:
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    numbered = [line for line in lines if re.match(r"^(?:\d+[.):]|[-•])\s*", line) or re.match(r"^\d+[.):]", line)]
    if numbered:
        return [re.sub(r"^(?:\d+[.):]|[-•])\s*", "", line).strip() for line in numbered]
    if len(lines) > 1:
        return lines
    parts = [part.strip() for part in re.split(r"(?:;|\n)", text) if part.strip()]
    return parts if len(parts) > 1 else ([text.strip()] if text.strip() else [])


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _overlap_ratio(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(right_tokens))


def _insight_signal(text: str) -> float:
    markers = {
        "tension",
        "pressure",
        "frustrated",
        "skeptical",
        "guilt",
        "permission",
        "trust",
        "burnout",
        "guesswork",
        "evidence",
        "data",
        "because",
        "but",
        "between",
    }
    hits = sum(1 for marker in markers if marker in text)
    return min(1.0, hits / 4)


def _voice_signal(text: str, brand: Brand) -> float:
    lowered = text.lower()
    signal = 0.6
    if any(phrase.lower() in lowered for phrase in brand.banned_phrases):
        signal -= 0.6
    if any(word in lowered for word in _HYPE_WORDS):
        signal -= 0.3
    if any("exclamation" in constraint.lower() for constraint in brand.constraints) and "!" in text:
        signal -= 0.2
    if brand.tone_keywords:
        signal += min(0.4, sum(1 for keyword in brand.tone_keywords if keyword.lower() in lowered) / max(1, len(brand.tone_keywords)))
    return max(0.0, min(1.0, signal))


def _conversation_signal(text: str) -> float:
    lowered = text.lower()
    signal = min(1.0, sum(1 for marker in _CONVERSATIONAL_MARKERS if marker in lowered) / 3)
    if "!" in text:
        signal = max(0.0, signal - 0.2)
    return signal


def _mentions_audience_or_strategy(text: str, context: str) -> float:
    audience_terms = _tokenize(context)
    if not audience_terms:
        return 0.0
    overlap = len(_tokenize(text) & audience_terms)
    return min(1.0, overlap / 4)


def _has_cta(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _CTA_PATTERNS)


def _feedback_signal(feedback: str, response: str, previous_response: str) -> float:
    feedback_text = feedback.lower()
    response_text = response.lower()
    signal = 0.0
    if previous_response and len(response.split()) <= len(previous_response.split()):
        signal += 0.3
    if any(word in feedback_text for word in {"friend", "conversational", "less corporate"}) and _conversation_signal(response) >= 0.5:
        signal += 0.3
    if any(word in feedback_text for word in {"short", "long"}) and previous_response and len(response) < len(previous_response):
        signal += 0.2
    if _overlap_ratio(response_text, feedback_text) >= 0.15:
        signal += 0.2
    return min(1.0, signal)


def _find_phrases(texts: list[str], phrases: list[str]) -> list[str]:
    found: list[str] = []
    lowered_texts = [text.lower() for text in texts]
    for phrase in phrases:
        phrase_lower = phrase.lower()
        if phrase_lower and any(phrase_lower in text for text in lowered_texts):
            found.append(phrase)
    return found


def _forbidden_phrases_from_constraints(constraints: list[str]) -> list[str]:
    phrases: list[str] = []
    for constraint in constraints:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", constraint)
        if quoted:
            phrases.extend(quoted)
    return phrases


def _constraint_forbids_exclamation(constraints: list[str]) -> bool:
    return any("exclamation" in constraint.lower() for constraint in constraints)


def _contains_any(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _blend(primary: float, secondary: float, weight: float) -> float:
    return max(0.0, min(1.0, primary * weight + secondary * (1 - weight)))


def _scale_points(max_points: float, score: float) -> float:
    return round(max_points * max(0.0, min(1.0, score)))
