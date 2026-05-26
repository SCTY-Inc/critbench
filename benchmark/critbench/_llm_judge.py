"""LLM-based rubric scoring — prompt building, judge calls, JSON parsing."""
from __future__ import annotations

import json
import re
import statistics
from typing import Any

from ._heuristics import assistant_responses_by_turn
from .models import Brand, RubricCriterion, Scenario, Turn


def score_dimension_with_llm(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
    api_client: Any,
    models: list[str],
) -> dict[str, Any]:
    prompt = build_rubric_prompt(dimension, transcript, scenario, brand, criteria)
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
            parsed = parse_judge_payload(analysis, criteria_lookup)
            per_model_points[model] = parsed
            per_model_scores[model] = sum(parsed.values()) / max(total_points, 1)
            reasoning[model] = analysis
            evidence.append(f"Judge {model} scored {per_model_scores[model]:.2f}")
        except Exception as exc:
            evidence.append(f"Judge {model} failed: {exc}")

    if not per_model_scores:
        return {"judge_scores": {}, "_reasoning": {}, "evidence": evidence}

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
        "confidence": max(0.0, 1.0 - (statistics.stdev(values) if len(values) > 1 else 0.0)),
        "evidence": evidence,
    }


def build_rubric_prompt(
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
) -> str:
    transcript_block = format_transcript_for_prompt(transcript, scenario)
    criteria_block = []
    for turn, criterion in criteria:
        guide = "; ".join(
            f"{points}={description}"
            for points, description in sorted(criterion.scoring_guide.items())
        )
        behaviors = ", ".join(turn.expected_behaviors) if turn.expected_behaviors else "none"
        criteria_block.append(
            "\n".join([
                f"criterion_id: {criterion.criterion_id}",
                f"turn_number: {turn.turn_number}",
                f"stage: {turn.stage.value if turn.stage else 'unknown'}",
                f"description: {criterion.description}",
                f"max_points: {criterion.max_points}",
                f"expected_behaviors: {behaviors}",
                f"scoring_guide: {guide}",
            ])
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


def parse_judge_payload(
    response: str,
    criteria_lookup: dict[str, RubricCriterion],
) -> dict[str, float]:
    payload = extract_json_object(response)
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

    missing = [cid for cid in criteria_lookup if cid not in points_by_id]
    if missing:
        raise ValueError(f"Judge omitted criteria: {', '.join(missing)}")
    return points_by_id


def extract_json_object(response: str) -> dict[str, Any]:
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


def format_transcript_for_prompt(transcript: list[dict[str, Any]], scenario: Scenario) -> str:
    assistant_by_turn = assistant_responses_by_turn(transcript)
    lines = []
    for turn in scenario.turns:
        stage = turn.stage.value if turn.stage else "unknown"
        lines.append(f"Turn {turn.turn_number} [{stage}] USER: {turn.user_message}")
        lines.append(f"Turn {turn.turn_number} [{stage}] ASSISTANT: {assistant_by_turn.get(turn.turn_number, '')}")
    return "\n".join(lines)


def collect_judge_scores(
    dim_result: dict[str, Any],
    dimension: str,
    all_scores: dict[str, dict[str, list[float]]],
) -> None:
    """Accumulate per-criterion scores per judge for reliability metrics."""
    judge_scores = dim_result.get("judge_scores") or {}
    criterion_scores = dim_result.get("criterion_scores") or {}
    if not judge_scores or not criterion_scores:
        return

    # Store per-criterion scores so reliability.py gets multiple items per rater
    per_judge: dict[str, list[float]] = {}
    for criterion_id, criterion_data in criterion_scores.items():
        for model in judge_scores:
            per_judge.setdefault(model, []).append(
                float(criterion_data.get("score", 0.0))
            )

    all_scores[dimension] = per_judge


def score_dimension_with_verifier(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
    api_client: Any,
    models: list[str],
    k_repeats: int = 3,
) -> dict[str, Any]:
    """LLM-as-a-Verifier: granularity scaling + K-repeated verification.

    For each criterion, runs K independent yes/no verification calls per score
    level defined in the criterion's scoring_guide, then aggregates into a
    continuous expected-value score. This gives K*len(score_levels) independent
    readings per criterion — enough items for Krippendorff's alpha.
    """
    transcript_block = format_transcript_for_prompt(transcript, scenario)
    criteria_lookup = {criterion.criterion_id: criterion for _, criterion in criteria}
    total_points = sum(criterion.max_points for _, criterion in criteria)

    # per_judge_criterion_scores[model][criterion_id] = list of K point estimates
    per_judge_criterion_scores: dict[str, dict[str, list[float]]] = {m: {} for m in models}
    evidence: list[str] = []

    for turn, criterion in criteria:
        score_levels = sorted(criterion.scoring_guide.keys(), key=lambda x: int(x))
        for model in models:
            level_scores: list[float] = []
            for _k in range(k_repeats):
                try:
                    prompt = _build_verification_prompt(
                        dimension=dimension,
                        transcript_block=transcript_block,
                        turn=turn,
                        criterion=criterion,
                        brand=brand,
                    )
                    response = api_client.call_model(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=400,
                    )
                    raw_points = _parse_verification_response(response["response"], criterion)
                    level_scores.append(raw_points)
                except Exception as exc:
                    evidence.append(f"Verifier {model}/{criterion.criterion_id} run {_k+1} failed: {exc}")

            if level_scores:
                per_judge_criterion_scores[model].setdefault(criterion.criterion_id, [])
                per_judge_criterion_scores[model][criterion.criterion_id].extend(level_scores)

    # Aggregate: mean across K runs per (judge, criterion), then mean across judges
    criterion_scores: dict[str, Any] = {}
    points_earned = 0.0
    per_model_overall: dict[str, float] = {}

    for criterion_id, criterion in criteria_lookup.items():
        judge_means: list[float] = []
        judge_distributions: dict[str, float] = {}
        for model in models:
            runs = per_judge_criterion_scores[model].get(criterion_id, [])
            if runs:
                mean = statistics.mean(runs)
                judge_means.append(mean)
                judge_distributions[model] = mean

        if judge_means:
            mean_points = statistics.mean(judge_means)
        else:
            mean_points = 0.0

        points_earned += mean_points
        criterion_scores[criterion_id] = {
            "points": mean_points,
            "max_points": criterion.max_points,
            "score": mean_points / max(criterion.max_points, 1),
            "description": criterion.description,
            "verifier_distributions": judge_distributions,
            "k_repeats": k_repeats,
        }

    for model in models:
        model_points = sum(
            statistics.mean(per_judge_criterion_scores[model].get(cid, [0.0]))
            for cid in criteria_lookup
        )
        per_model_overall[model] = model_points / max(total_points, 1)

    if not any(per_judge_criterion_scores[m] for m in models):
        return {"judge_scores": {}, "_reasoning": {}, "evidence": evidence}

    values = list(per_model_overall.values())
    return {
        "score": points_earned / max(total_points, 1),
        "points_earned": points_earned,
        "max_points": total_points,
        "criterion_scores": criterion_scores,
        "judge_scores": per_model_overall,
        "_reasoning": {},
        "method": "verifier",
        "confidence": max(0.0, 1.0 - (statistics.stdev(values) if len(values) > 1 else 0.0)),
        "evidence": evidence or [f"Verifier mode: {k_repeats} runs per criterion per judge"],
    }


def _build_verification_prompt(
    *,
    dimension: str,
    transcript_block: str,
    turn: Turn,
    criterion: RubricCriterion,
    brand: Brand,
) -> str:
    guide_lines = "\n".join(
        f"  {pts} points: {desc}"
        for pts, desc in sorted(criterion.scoring_guide.items(), key=lambda x: int(x[0]))
    )
    return f"""You are verifying CritBench dimension '{dimension}'.

Brand: {brand.name} | Voice: {brand.voice} | Audience: {brand.audience}
Constraints: {', '.join(brand.constraints) if brand.constraints else 'none'}

Transcript:
{transcript_block}

Criterion: {criterion.criterion_id}
Description: {criterion.description}
Max points: {criterion.max_points}

Scoring guide:
{guide_lines}

How many points (0 to {criterion.max_points}) does the turn {turn.turn_number} assistant response deserve for this criterion?
Return JSON only: {{"points": <integer 0-{criterion.max_points}>, "reason": "<one sentence>"}}"""


def _parse_verification_response(response: str, criterion: RubricCriterion) -> float:
    payload = extract_json_object(response)
    raw = payload.get("points")
    if raw is None:
        raise ValueError("Missing 'points' in verifier response")
    points = float(raw)
    return max(0.0, min(float(criterion.max_points), round(points)))


def analyze_cot(
    dim_result: dict[str, Any],
    dimension: str,
    analyzer: Any | None,
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
