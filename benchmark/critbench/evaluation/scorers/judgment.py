"""Judgment scorer - evaluates idea selection quality.

This tests whether the model can JUDGE creative work, not just generate it.
The ability to select the best ideas from a set is a key creative skill
that existing benchmarks don't measure.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from critbench.api import ModelAPIClient
from critbench.utils.llm_mode import llm_enabled


def score(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[ModelAPIClient] = None,
    models: Optional[List[str]] = None,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Score idea selection and judgment quality.

    Evaluates:
    - Selection reasoning: Is the rationale clear and strategic?
    - Strategy alignment: Do selections support the positioning?
    - Feasibility awareness: Does reasoning consider practical constraints?
    - Selection quality: Are the selected ideas actually the strongest?
    """
    result = {
        "score": 1.0,
        "breakdown": {},
        "evidence": [],
    }

    # Extract idea generation and selection turns
    ideas_generated = _extract_ideas(transcript, scenario)
    selection_response = _extract_selection(transcript, scenario)

    if not ideas_generated or not selection_response:
        result["score"] = 0.0
        result["evidence"].append("Missing idea generation or selection turns")
        return result

    if not llm_enabled(allow_llm):
        result["evidence"].append("LLM judgment evaluation skipped (offline mode)")
        _evaluate_judgment_deterministic(ideas_generated, selection_response, result)
        return result

    if api_client is None:
        try:
            api_client = ModelAPIClient()
        except ValueError as e:
            result["evidence"].append(f"ERROR: Cannot initialize API - {e}")
            _evaluate_judgment_deterministic(ideas_generated, selection_response, result)
            return result

    # Multi-judge scoring
    judge_models = models or [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ]

    all_scores = {
        "selection_reasoning": [],
        "strategy_alignment": [],
        "feasibility_awareness": [],
        "selection_quality": [],
    }

    positioning = _extract_positioning(transcript, scenario)

    for model in judge_models:
        try:
            model_scores = _evaluate_with_model(
                ideas_generated,
                selection_response,
                positioning,
                brand,
                api_client,
                model,
                result["evidence"],
            )
            for key, value in model_scores.items():
                all_scores[key].append(value)
        except Exception as e:
            result["evidence"].append(f"Judge {model} failed: {e}")

    # Aggregate
    final_scores = {}
    for key, scores in all_scores.items():
        if scores:
            final_scores[key] = statistics.mean(scores)
        else:
            final_scores[key] = 0.5

    # Weighted overall
    weights = {
        "selection_reasoning": 0.40,
        "strategy_alignment": 0.30,
        "feasibility_awareness": 0.20,
        "selection_quality": 0.10,
    }

    overall = sum(final_scores[k] * weights[k] for k in weights)

    # Penalty for poor reasoning
    if final_scores["selection_reasoning"] < 0.4:
        overall = max(0, overall - 0.25)
        result["evidence"].append("PENALTY: Poor selection reasoning")

    result["score"] = overall
    result["breakdown"] = final_scores

    return result


def _extract_ideas(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any]
) -> Optional[str]:
    """Extract idea generation response."""
    for turn in scenario.get("turns", []):
        if turn.get("stage") == "idea_generation":
            turn_num = turn.get("turn_number", turn.get("t"))
            for msg in transcript:
                if msg["role"] == "assistant" and msg["turn"] == turn_num:
                    return msg["content"]
    return None


def _extract_selection(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any]
) -> Optional[str]:
    """Extract idea selection response."""
    for turn in scenario.get("turns", []):
        if turn.get("stage") == "idea_selection":
            turn_num = turn.get("turn_number", turn.get("t"))
            for msg in transcript:
                if msg["role"] == "assistant" and msg["turn"] == turn_num:
                    return msg["content"]
    return None


def _extract_positioning(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any]
) -> Optional[str]:
    """Extract positioning/strategy response."""
    for turn in scenario.get("turns", []):
        if turn.get("stage") == "strategy":
            turn_num = turn.get("turn_number", turn.get("t"))
            for msg in transcript:
                if msg["role"] == "assistant" and msg["turn"] == turn_num:
                    return msg["content"]
    return None


def _evaluate_with_model(
    ideas: str,
    selection: str,
    positioning: Optional[str],
    brand: Dict[str, Any],
    api_client: ModelAPIClient,
    model: str,
    evidence: List[str],
) -> Dict[str, float]:
    """Evaluate judgment using a single judge model."""

    prompt = f"""You are evaluating CREATIVE JUDGMENT - the ability to select the best ideas.

**BRAND:**
- Name: {brand.get('name', 'Unknown')}
- Audience: {brand.get('audience', 'Not specified')}

**POSITIONING:**
{positioning or 'Not provided'}

**IDEAS GENERATED:**
{ideas}

**SELECTION & REASONING:**
{selection}

**EVALUATE JUDGMENT:**

1. **SELECTION_REASONING (0.0-1.0):**
   Is the rationale for selections clear and strategic?
   - 1.0 = Clear reasoning that connects to audience and positioning
   - 0.5 = Generic reasoning or just states preference
   - 0.0 = No reasoning or contradictory reasoning

2. **STRATEGY_ALIGNMENT (0.0-1.0):**
   Do the selected ideas support the positioning?
   - 1.0 = Selections clearly ladder to positioning
   - 0.5 = Selections are related but connection is loose
   - 0.0 = Selections contradict or ignore positioning

3. **FEASIBILITY_AWARENESS (0.0-1.0):**
   Does reasoning consider practical constraints?
   - 1.0 = Acknowledges budget, timeline, resources
   - 0.5 = Some awareness of constraints
   - 0.0 = Ignores practical considerations

4. **SELECTION_QUALITY (0.0-1.0):**
   Are the selected ideas actually the strongest from the set?
   - 1.0 = Defensibly the best options
   - 0.5 = Reasonable but not obviously best
   - 0.0 = Clearly not the strongest concepts

**Respond in this exact format:**

SELECTION_REASONING: [0.0-1.0]
STRATEGY_ALIGNMENT: [0.0-1.0]
FEASIBILITY_AWARENESS: [0.0-1.0]
SELECTION_QUALITY: [0.0-1.0]

EVIDENCE:
- Reasoning: [Quality of rationale]
- Alignment: [Connection to positioning]
- Feasibility: [Awareness of constraints]
- Quality: [Are these the best picks?]"""

    response = api_client.call_model(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500,
    )

    return _parse_judgment_evaluation(response["response"])


def _parse_judgment_evaluation(analysis: str) -> Dict[str, float]:
    """Parse LLM judgment evaluation response."""
    scores = {
        "selection_reasoning": 0.5,
        "strategy_alignment": 0.5,
        "feasibility_awareness": 0.5,
        "selection_quality": 0.5,
    }

    for line in analysis.split("\n"):
        line = line.strip().upper()
        for key in scores:
            label = key.upper()
            if line.startswith(label + ":"):
                try:
                    value = float(line.split(":")[1].strip())
                    scores[key] = max(0.0, min(1.0, value))
                except (ValueError, IndexError):
                    pass

    return scores


def _evaluate_judgment_deterministic(
    ideas: str,
    selection: str,
    result: Dict[str, Any],
) -> None:
    """Fallback deterministic judgment check."""

    # Simple heuristics
    has_reasoning = any(word in selection.lower() for word in [
        "because", "since", "therefore", "this works", "reason"
    ])
    has_tradeoffs = any(word in selection.lower() for word in [
        "however", "although", "tradeoff", "consider", "but"
    ])

    result["score"] = 0.4 + (0.3 if has_reasoning else 0) + (0.2 if has_tradeoffs else 0)
    result["breakdown"] = {
        "selection_reasoning": 0.7 if has_reasoning else 0.3,
        "strategy_alignment": 0.5,
        "feasibility_awareness": 0.6 if has_tradeoffs else 0.4,
        "selection_quality": 0.5,
        "method": "deterministic",
    }
