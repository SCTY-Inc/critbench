"""Coherence scorer - evaluates insight → strategy → creative laddering.

This is the core differentiator of CritBench: testing whether the creative
process maintains logical coherence across stages, not just output quality.
"""
from __future__ import annotations

import asyncio
import statistics
from typing import Any, Dict, List, Optional

from critbench.api import AsyncModelAPIClient, ModelAPIClient, resolve_scorer_model
from critbench.utils.llm_mode import llm_enabled


def score(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[ModelAPIClient] = None,
    models: Optional[List[str]] = None,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Score coherence across creative process stages.

    Evaluates:
    - Brief understanding: Did the model grasp the core brief?
    - Insight → Strategy: Does positioning flow from insights?
    - Strategy → Creative: Do ideas ladder to positioning?
    - Internal consistency: No contradictions across turns

    Uses multi-judge ensemble scoring for reliability.
    """
    result = {
        "score": 1.0,
        "breakdown": {},
        "evidence": [],
    }

    # Extract stages from transcript
    stages = _extract_stages(transcript, scenario)

    if not llm_enabled(allow_llm):
        result["evidence"].append("LLM coherence evaluation skipped (offline mode)")
        _evaluate_coherence_deterministic(stages, brand, result)
        return result

    # Initialize API client
    if api_client is None:
        try:
            api_client = ModelAPIClient()
        except ValueError as e:
            result["evidence"].append(f"ERROR: Cannot initialize API - {e}")
            _evaluate_coherence_deterministic(stages, brand, result)
            return result

    # Multi-judge ensemble scoring
    judge_models = models or [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ]

    all_scores = {
        "brief_understanding": [],
        "insight_to_strategy": [],
        "strategy_to_creative": [],
        "internal_consistency": [],
    }

    for model in judge_models:
        try:
            model_scores = _evaluate_with_model(
                stages, brand, scenario, api_client, model, result["evidence"]
            )
            for key, value in model_scores.items():
                all_scores[key].append(value)
        except Exception as e:
            result["evidence"].append(f"Judge {model} failed: {e}")

    # Aggregate scores across judges
    final_scores = {}
    confidences = {}

    for key, scores in all_scores.items():
        if scores:
            final_scores[key] = statistics.mean(scores)
            confidences[key] = 1.0 - (statistics.stdev(scores) if len(scores) > 1 else 0.0)
        else:
            final_scores[key] = 0.5
            confidences[key] = 0.0

    # Calculate weighted overall score
    weights = {
        "brief_understanding": 0.20,
        "insight_to_strategy": 0.35,
        "strategy_to_creative": 0.35,
        "internal_consistency": 0.10,
    }

    overall = sum(final_scores[k] * weights[k] for k in weights)

    # Check for contradictions (hard penalty)
    if final_scores["internal_consistency"] < 0.5:
        overall = max(0, overall - 0.30)
        result["evidence"].append("PENALTY: Internal contradictions detected")

    result["score"] = overall
    result["breakdown"] = {
        "brief_understanding": final_scores["brief_understanding"],
        "insight_to_strategy": final_scores["insight_to_strategy"],
        "strategy_to_creative": final_scores["strategy_to_creative"],
        "internal_consistency": final_scores["internal_consistency"],
        "confidences": confidences,
        "n_judges": len(judge_models),
        "judges_succeeded": sum(1 for s in all_scores["brief_understanding"] if s is not None),
    }

    return result


async def score_async(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[AsyncModelAPIClient] = None,
    models: Optional[List[str]] = None,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Async score coherence across creative process stages."""
    result = {
        "score": 1.0,
        "breakdown": {},
        "evidence": [],
    }

    stages = _extract_stages(transcript, scenario)

    if not llm_enabled(allow_llm):
        result["evidence"].append("LLM coherence evaluation skipped (offline mode)")
        _evaluate_coherence_deterministic(stages, brand, result)
        return result

    if api_client is None:
        try:
            api_client = AsyncModelAPIClient()
        except ValueError as e:
            result["evidence"].append(f"ERROR: Cannot initialize API - {e}")
            _evaluate_coherence_deterministic(stages, brand, result)
            return result

    judge_models = models or [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ]

    all_scores = {
        "brief_understanding": [],
        "insight_to_strategy": [],
        "strategy_to_creative": [],
        "internal_consistency": [],
    }

    tasks = [
        _evaluate_with_model_async(
            stages, brand, scenario, api_client, model
        )
        for model in judge_models
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for model, outcome in zip(judge_models, results):
        if isinstance(outcome, Exception):
            result["evidence"].append(f"Judge {model} error: {outcome}")
            result["evidence"].append(f"Judge {model} failed: {outcome}")
            continue
        model_scores, evidence_entry = outcome
        result["evidence"].append(evidence_entry)
        for key, value in model_scores.items():
            all_scores[key].append(value)

    final_scores = {}
    confidences = {}

    for key, scores in all_scores.items():
        if scores:
            final_scores[key] = statistics.mean(scores)
            confidences[key] = 1.0 - (statistics.stdev(scores) if len(scores) > 1 else 0.0)
        else:
            final_scores[key] = 0.5
            confidences[key] = 0.0

    weights = {
        "brief_understanding": 0.20,
        "insight_to_strategy": 0.35,
        "strategy_to_creative": 0.35,
        "internal_consistency": 0.10,
    }

    overall = sum(final_scores[k] * weights[k] for k in weights)

    if final_scores["internal_consistency"] < 0.5:
        overall = max(0, overall - 0.30)
        result["evidence"].append("PENALTY: Internal contradictions detected")

    result["score"] = overall
    result["breakdown"] = {
        "brief_understanding": final_scores["brief_understanding"],
        "insight_to_strategy": final_scores["insight_to_strategy"],
        "strategy_to_creative": final_scores["strategy_to_creative"],
        "internal_consistency": final_scores["internal_consistency"],
        "confidences": confidences,
        "n_judges": len(judge_models),
        "judges_succeeded": sum(1 for s in all_scores["brief_understanding"] if s is not None),
    }

    return result


def _extract_stages(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any]
) -> Dict[str, str]:
    """Extract content by creative stage from transcript."""
    stages = {}

    # Map turn numbers to stages from scenario
    turn_to_stage = {}
    for turn in scenario.get("turns", []):
        t = turn.get("turn_number", turn.get("t"))
        stage = turn.get("stage")
        if t and stage:
            turn_to_stage[t] = stage

    # Extract assistant responses by stage
    for msg in transcript:
        if msg["role"] == "assistant":
            turn = msg["turn"]
            stage = turn_to_stage.get(turn)
            if stage:
                stages[stage] = msg["content"]

    return stages


def _evaluate_with_model(
    stages: Dict[str, str],
    brand: Dict[str, Any],
    scenario: Dict[str, Any],
    api_client: ModelAPIClient,
    model: str,
    evidence: List[str],
) -> Dict[str, float]:
    """Evaluate coherence using a single judge model."""

    prompt = f"""You are evaluating the COHERENCE of a creative process.

**BRAND CONTEXT:**
- Name: {brand.get('name', 'Unknown')}
- Voice: {brand.get('voice', 'Not specified')}
- Audience: {brand.get('audience', 'Not specified')}

**CREATIVE PROCESS OUTPUTS:**

Brief Understanding (Turn 1):
{stages.get('brief_intake', 'Not provided')}

Insights Generated (Turn 2):
{stages.get('insight_generation', 'Not provided')}

Strategy/Positioning (Turn 3):
{stages.get('strategy', 'Not provided')}

Campaign Ideas (Turn 4):
{stages.get('idea_generation', 'Not provided')}

Idea Selection (Turn 5):
{stages.get('idea_selection', 'Not provided')}

**EVALUATE COHERENCE:**

1. **BRIEF_UNDERSTANDING (0.0-1.0):**
   Did the model demonstrate understanding of the brief before proceeding?
   - 1.0 = Asked clarifying questions, showed comprehension
   - 0.5 = Adequate understanding but missed nuances
   - 0.0 = Jumped to tactics without understanding

2. **INSIGHT_TO_STRATEGY (0.0-1.0):**
   Does the positioning/strategy logically flow from the insights?
   - 1.0 = Strategy directly addresses tensions identified in insights
   - 0.5 = Related but connection is loose
   - 0.0 = Strategy ignores or contradicts insights

3. **STRATEGY_TO_CREATIVE (0.0-1.0):**
   Do the campaign ideas ladder to the positioning?
   - 1.0 = All ideas clearly express the positioning
   - 0.5 = Most ideas connect, some feel disconnected
   - 0.0 = Ideas don't support the positioning

4. **INTERNAL_CONSISTENCY (0.0-1.0):**
   Are there contradictions across the process?
   - 1.0 = Fully consistent, no contradictions
   - 0.5 = Minor inconsistencies
   - 0.0 = Major contradictions

**Respond in this exact format:**

BRIEF_UNDERSTANDING: [0.0-1.0]
INSIGHT_TO_STRATEGY: [0.0-1.0]
STRATEGY_TO_CREATIVE: [0.0-1.0]
INTERNAL_CONSISTENCY: [0.0-1.0]

EVIDENCE:
- Brief: [How well was the brief understood?]
- Insight→Strategy: [Does positioning flow from insights?]
- Strategy→Creative: [Do ideas ladder to positioning?]
- Contradictions: [Any contradictions found, or "none"]"""

    try:
        response = api_client.call_model(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        analysis = response["response"]
        evidence.append(f"Judge {model}:\n{analysis[:500]}...")

        return _parse_coherence_evaluation(analysis)
    except Exception as e:
        evidence.append(f"Judge {model} error: {e}")
        raise


async def _evaluate_with_model_async(
    stages: Dict[str, str],
    brand: Dict[str, Any],
    scenario: Dict[str, Any],
    api_client: AsyncModelAPIClient,
    model: str,
) -> tuple[Dict[str, float], str]:
    """Evaluate coherence using a single judge model (async)."""

    prompt = f"""You are evaluating the COHERENCE of a creative process.

**BRAND CONTEXT:**
- Name: {brand.get('name', 'Unknown')}
- Voice: {brand.get('voice', 'Not specified')}
- Audience: {brand.get('audience', 'Not specified')}

**CREATIVE PROCESS OUTPUTS:**

Brief Understanding (Turn 1):
{stages.get('brief_intake', 'Not provided')}

Insights Generated (Turn 2):
{stages.get('insight_generation', 'Not provided')}

Strategy/Positioning (Turn 3):
{stages.get('strategy', 'Not provided')}

Campaign Ideas (Turn 4):
{stages.get('idea_generation', 'Not provided')}

Idea Selection (Turn 5):
{stages.get('idea_selection', 'Not provided')}

**EVALUATE COHERENCE:**

1. **BRIEF_UNDERSTANDING (0.0-1.0):**
   Did the model demonstrate understanding of the brief before proceeding?
   - 1.0 = Asked clarifying questions, showed comprehension
   - 0.5 = Adequate understanding but missed nuances
   - 0.0 = Jumped to tactics without understanding

2. **INSIGHT_TO_STRATEGY (0.0-1.0):**
   Does the positioning/strategy logically flow from the insights?
   - 1.0 = Strategy directly addresses tensions identified in insights
   - 0.5 = Related but connection is loose
   - 0.0 = Strategy ignores or contradicts insights

3. **STRATEGY_TO_CREATIVE (0.0-1.0):**
   Do the campaign ideas ladder to the positioning?
   - 1.0 = All ideas clearly express the positioning
   - 0.5 = Most ideas connect, some feel disconnected
   - 0.0 = Ideas don't support the positioning

4. **INTERNAL_CONSISTENCY (0.0-1.0):**
   Are there contradictions across the process?
   - 1.0 = Fully consistent, no contradictions
   - 0.5 = Minor inconsistencies
   - 0.0 = Major contradictions

**Respond in this exact format:**

BRIEF_UNDERSTANDING: [0.0-1.0]
INSIGHT_TO_STRATEGY: [0.0-1.0]
STRATEGY_TO_CREATIVE: [0.0-1.0]
INTERNAL_CONSISTENCY: [0.0-1.0]

EVIDENCE:
- Brief: [How well was the brief understood?]
- Insight→Strategy: [Does positioning flow from insights?]
- Strategy→Creative: [Do ideas ladder to positioning?]
- Contradictions: [Any contradictions found, or "none"]"""

    response = await api_client.call_model(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500,
    )
    analysis = response["response"]
    evidence_entry = f"Judge {model}:\n{analysis[:500]}..."

    return _parse_coherence_evaluation(analysis), evidence_entry


def _parse_coherence_evaluation(analysis: str) -> Dict[str, float]:
    """Parse LLM coherence evaluation response."""
    scores = {
        "brief_understanding": 0.5,
        "insight_to_strategy": 0.5,
        "strategy_to_creative": 0.5,
        "internal_consistency": 0.5,
    }

    for line in analysis.split("\n"):
        line = line.strip()
        for key in scores:
            label = key.upper().replace("_", "_")
            if line.upper().startswith(label.replace("_", "_") + ":"):
                try:
                    value = float(line.split(":")[1].strip())
                    scores[key] = max(0.0, min(1.0, value))
                except (ValueError, IndexError):
                    pass

    return scores


def _evaluate_coherence_deterministic(
    stages: Dict[str, str],
    brand: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Fallback deterministic coherence check."""

    # Simple heuristics
    brief_response = stages.get("brief_intake", "").lower()
    has_questions = "?" in brief_response

    insight_response = stages.get("insight_generation", "").lower()
    strategy_response = stages.get("strategy", "").lower()

    # Check if key terms flow through
    insight_terms = set(insight_response.split())
    strategy_terms = set(strategy_response.split())
    overlap = len(insight_terms & strategy_terms) / max(len(insight_terms), 1)

    result["score"] = 0.5 + (0.2 if has_questions else 0) + (overlap * 0.3)
    result["breakdown"] = {
        "brief_understanding": 0.7 if has_questions else 0.3,
        "insight_to_strategy": min(1.0, overlap * 2),
        "strategy_to_creative": 0.5,  # Cannot evaluate deterministically
        "internal_consistency": 0.7,
        "method": "deterministic",
    }
    result["evidence"].append("Deterministic fallback used")
