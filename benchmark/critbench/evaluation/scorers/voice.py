"""Voice scorer - evaluates brand consistency across outputs.

Tests whether the model maintains consistent brand voice across
multiple outputs, formats, and turns.

Implements multi-judge ensemble scoring with:
- Tone consistency analysis
- Vocabulary appropriateness for audience
- Cross-format consistency (email vs social vs landing page)
- Banned phrase detection
- Voice drift detection across turns
"""
from __future__ import annotations

import asyncio
import re
import statistics
from typing import Any, Dict, List, Optional, Set

from critbench.api import AsyncModelAPIClient, ModelAPIClient
from critbench.utils.llm_mode import llm_enabled


def score(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[ModelAPIClient] = None,
    models: Optional[List[str]] = None,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Score brand voice consistency.

    Evaluates:
    - Tone consistency: Does tone match brand spec across outputs?
    - Vocabulary match: Uses appropriate language for audience?
    - Format adaptation: Adapts to format while maintaining voice?
    - Cross-output consistency: Consistent voice across all turns?
    - Banned phrase detection: Uses prohibited language?

    Uses multi-judge ensemble scoring for reliability.
    """
    result = {
        "score": 0.5,
        "breakdown": {},
        "evidence": [],
    }

    # Extract assistant responses
    responses = _extract_responses(transcript)
    if not responses:
        result["evidence"].append("No assistant responses found")
        return result

    # Check banned phrases first (deterministic)
    banned_phrases = brand.get("banned_phrases", [])
    banned_found = _check_banned_phrases(responses, banned_phrases)

    if banned_found:
        result["evidence"].append(f"BANNED PHRASES FOUND: {banned_found}")
        # Apply penalty but continue evaluation
        result["breakdown"]["banned_phrases_found"] = banned_found

    if not llm_enabled(allow_llm):
        result["evidence"].append("LLM voice evaluation skipped (offline mode)")
        _evaluate_voice_deterministic(responses, brand, banned_found, result)
        return result

    # Initialize API client
    if api_client is None:
        try:
            api_client = ModelAPIClient()
        except ValueError as e:
            result["evidence"].append(f"ERROR: Cannot initialize API - {e}")
            _evaluate_voice_deterministic(responses, brand, banned_found, result)
            return result

    # Multi-judge ensemble scoring
    judge_models = models or [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ]

    all_scores = {
        "tone_consistency": [],
        "vocabulary_match": [],
        "format_adaptation": [],
        "cross_output_consistency": [],
    }

    all_reasoning = {}

    for model in judge_models:
        try:
            model_scores, reasoning = _evaluate_with_model(
                responses, brand, scenario, api_client, model, result["evidence"]
            )
            for key, value in model_scores.items():
                all_scores[key].append(value)
            all_reasoning[model] = reasoning
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
        "tone_consistency": 0.35,
        "vocabulary_match": 0.25,
        "format_adaptation": 0.20,
        "cross_output_consistency": 0.20,
    }

    overall = sum(final_scores[k] * weights[k] for k in weights)

    # Apply banned phrase penalty
    if banned_found:
        penalty = min(0.50, len(banned_found) * 0.10)
        overall = max(0, overall - penalty)
        result["evidence"].append(f"PENALTY: -{penalty:.2f} for banned phrases")

    # Check for voice violations (significant tone inconsistency)
    if final_scores["tone_consistency"] < 0.4:
        overall = max(0, overall - 0.30)
        result["evidence"].append("PENALTY: Significant voice inconsistency detected")

    result["score"] = overall
    result["breakdown"] = {
        "tone_consistency": final_scores["tone_consistency"],
        "vocabulary_match": final_scores["vocabulary_match"],
        "format_adaptation": final_scores["format_adaptation"],
        "cross_output_consistency": final_scores["cross_output_consistency"],
        "banned_phrases_found": banned_found,
        "confidences": confidences,
        "n_judges": len(judge_models),
        "judges_succeeded": sum(1 for s in all_scores["tone_consistency"] if s is not None),
    }

    # Store reasoning for CoT analysis
    result["_reasoning"] = all_reasoning

    return result


async def score_async(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[AsyncModelAPIClient] = None,
    models: Optional[List[str]] = None,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Async score brand voice consistency."""
    result = {
        "score": 0.5,
        "breakdown": {},
        "evidence": [],
    }

    responses = _extract_responses(transcript)
    if not responses:
        result["evidence"].append("No assistant responses found")
        return result

    banned_phrases = brand.get("banned_phrases", [])
    banned_found = _check_banned_phrases(responses, banned_phrases)

    if banned_found:
        result["evidence"].append(f"BANNED PHRASES FOUND: {banned_found}")
        result["breakdown"]["banned_phrases_found"] = banned_found

    if not llm_enabled(allow_llm):
        result["evidence"].append("LLM voice evaluation skipped (offline mode)")
        _evaluate_voice_deterministic(responses, brand, banned_found, result)
        return result

    if api_client is None:
        try:
            api_client = AsyncModelAPIClient()
        except ValueError as e:
            result["evidence"].append(f"ERROR: Cannot initialize API - {e}")
            _evaluate_voice_deterministic(responses, brand, banned_found, result)
            return result

    judge_models = models or [
        "claude-sonnet-4-20250514",
        "gpt-4.1",
        "gemini-2.0-flash",
    ]

    all_scores = {
        "tone_consistency": [],
        "vocabulary_match": [],
        "format_adaptation": [],
        "cross_output_consistency": [],
    }

    all_reasoning = {}

    tasks = [
        _evaluate_with_model_async(
            responses, brand, scenario, api_client, model
        )
        for model in judge_models
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for model, outcome in zip(judge_models, results):
        if isinstance(outcome, Exception):
            result["evidence"].append(f"Judge {model} error: {outcome}")
            result["evidence"].append(f"Judge {model} failed: {outcome}")
            continue
        model_scores, evidence_entry, reasoning = outcome
        result["evidence"].append(evidence_entry)
        for key, value in model_scores.items():
            all_scores[key].append(value)
        all_reasoning[model] = reasoning

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
        "tone_consistency": 0.35,
        "vocabulary_match": 0.25,
        "format_adaptation": 0.20,
        "cross_output_consistency": 0.20,
    }

    overall = sum(final_scores[k] * weights[k] for k in weights)

    if banned_found:
        penalty = min(0.50, len(banned_found) * 0.10)
        overall = max(0, overall - penalty)
        result["evidence"].append(f"PENALTY: -{penalty:.2f} for banned phrases")

    if final_scores["tone_consistency"] < 0.4:
        overall = max(0, overall - 0.30)
        result["evidence"].append("PENALTY: Significant voice inconsistency detected")

    result["score"] = overall
    result["breakdown"] = {
        "tone_consistency": final_scores["tone_consistency"],
        "vocabulary_match": final_scores["vocabulary_match"],
        "format_adaptation": final_scores["format_adaptation"],
        "cross_output_consistency": final_scores["cross_output_consistency"],
        "banned_phrases_found": banned_found,
        "confidences": confidences,
        "n_judges": len(judge_models),
        "judges_succeeded": sum(1 for s in all_scores["tone_consistency"] if s is not None),
    }

    result["_reasoning"] = all_reasoning

    return result


def _extract_responses(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract assistant responses with turn context."""
    responses = []
    for msg in transcript:
        if msg.get("role") == "assistant":
            responses.append({
                "turn": msg.get("turn", 0),
                "content": msg.get("content", ""),
            })
    return responses


def _check_banned_phrases(
    responses: List[Dict[str, Any]],
    banned_phrases: List[str],
) -> List[str]:
    """Check for banned phrases in responses."""
    found = []

    for phrase in banned_phrases:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        for resp in responses:
            if pattern.search(resp["content"]):
                if phrase not in found:
                    found.append(phrase)

    return found


def _evaluate_with_model(
    responses: List[Dict[str, Any]],
    brand: Dict[str, Any],
    scenario: Dict[str, Any],
    api_client: ModelAPIClient,
    model: str,
    evidence: List[str],
) -> tuple:
    """Evaluate voice using a single judge model."""

    # Build response summary
    response_texts = []
    for i, resp in enumerate(responses[:5]):  # Limit to first 5 turns
        response_texts.append(f"Turn {resp['turn']}:\n{resp['content'][:800]}")

    responses_block = "\n\n---\n\n".join(response_texts)

    # Get brand tone keywords
    tone_keywords = brand.get("tone_keywords", [])
    tone_desc = brand.get("voice", "Not specified")
    audience = brand.get("audience", "Not specified")
    constraints = brand.get("constraints", [])

    prompt = f"""You are evaluating BRAND VOICE CONSISTENCY across multiple outputs.

**BRAND SPECIFICATIONS:**
- Brand Voice: {tone_desc}
- Target Audience: {audience}
- Tone Keywords: {', '.join(tone_keywords) if tone_keywords else 'Not specified'}
- Constraints: {', '.join(constraints) if constraints else 'None specified'}

**OUTPUTS TO EVALUATE:**

{responses_block}

**EVALUATE VOICE CONSISTENCY:**

1. **TONE_CONSISTENCY (0.0-1.0):**
   Does the tone match the brand specification across ALL outputs?
   - 1.0 = Perfectly matches brand voice throughout
   - 0.5 = Generally appropriate but inconsistent
   - 0.0 = Completely off-brand or wildly inconsistent

2. **VOCABULARY_MATCH (0.0-1.0):**
   Is the vocabulary appropriate for the target audience?
   - 1.0 = Perfect register for audience, appropriate jargon level
   - 0.5 = Mostly appropriate, some misfits
   - 0.0 = Wrong register (too technical, too casual, etc.)

3. **FORMAT_ADAPTATION (0.0-1.0):**
   Does the voice adapt to different contexts while staying on-brand?
   - 1.0 = Naturally adapts format while maintaining voice
   - 0.5 = Some adaptation, but voice wavers
   - 0.0 = Either rigid or loses brand identity when adapting

4. **CROSS_OUTPUT_CONSISTENCY (0.0-1.0):**
   Is the voice consistent from turn to turn?
   - 1.0 = Could be from the same person/brand throughout
   - 0.5 = Some drift but recognizable
   - 0.0 = Feels like different writers/personalities

**Respond in this exact format:**

TONE_CONSISTENCY: [0.0-1.0]
VOCABULARY_MATCH: [0.0-1.0]
FORMAT_ADAPTATION: [0.0-1.0]
CROSS_OUTPUT_CONSISTENCY: [0.0-1.0]

EVIDENCE:
- Tone: [How well does tone match brand?]
- Vocabulary: [Is language appropriate for audience?]
- Adaptation: [How does voice adapt across outputs?]
- Consistency: [Is voice stable across turns?]"""

    try:
        response = api_client.call_model(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        analysis = response["response"]
        evidence.append(f"Judge {model}:\n{analysis[:500]}...")

        scores = _parse_voice_evaluation(analysis)
        return scores, analysis
    except Exception as e:
        evidence.append(f"Judge {model} error: {e}")
        raise


async def _evaluate_with_model_async(
    responses: List[Dict[str, Any]],
    brand: Dict[str, Any],
    scenario: Dict[str, Any],
    api_client: AsyncModelAPIClient,
    model: str,
) -> tuple[Dict[str, float], str, str]:
    """Evaluate voice using a single judge model (async)."""

    response_texts = []
    for i, resp in enumerate(responses[:5]):  # Limit to first 5 turns
        response_texts.append(f"Turn {resp['turn']}:\n{resp['content'][:800]}")

    responses_block = "\n\n---\n\n".join(response_texts)

    tone_keywords = brand.get("tone_keywords", [])
    tone_desc = brand.get("voice", "Not specified")
    audience = brand.get("audience", "Not specified")
    constraints = brand.get("constraints", [])

    prompt = f"""You are evaluating BRAND VOICE CONSISTENCY across multiple outputs.

**BRAND SPECIFICATIONS:**
- Brand Voice: {tone_desc}
- Target Audience: {audience}
- Tone Keywords: {', '.join(tone_keywords) if tone_keywords else 'Not specified'}
- Constraints: {', '.join(constraints) if constraints else 'None specified'}

**OUTPUTS TO EVALUATE:**

{responses_block}

**EVALUATE VOICE CONSISTENCY:**

1. **TONE_CONSISTENCY (0.0-1.0):**
   Does the tone match the brand specification across ALL outputs?
   - 1.0 = Perfectly matches brand voice throughout
   - 0.5 = Generally appropriate but inconsistent
   - 0.0 = Completely off-brand or wildly inconsistent

2. **VOCABULARY_MATCH (0.0-1.0):**
   Is the vocabulary appropriate for the target audience?
   - 1.0 = Perfect register for audience, appropriate jargon level
   - 0.5 = Mostly appropriate, some misfits
   - 0.0 = Wrong register (too technical, too casual, etc.)

3. **FORMAT_ADAPTATION (0.0-1.0):**
   Does the voice adapt to different contexts while staying on-brand?
   - 1.0 = Naturally adapts format while maintaining voice
   - 0.5 = Some adaptation, but voice wavers
   - 0.0 = Either rigid or loses brand identity when adapting

4. **CROSS_OUTPUT_CONSISTENCY (0.0-1.0):**
   Is the voice consistent from turn to turn?
   - 1.0 = Could be from the same person/brand throughout
   - 0.5 = Some drift but recognizable
   - 0.0 = Feels like different writers/personalities

**Respond in this exact format:**

TONE_CONSISTENCY: [0.0-1.0]
VOCABULARY_MATCH: [0.0-1.0]
FORMAT_ADAPTATION: [0.0-1.0]
CROSS_OUTPUT_CONSISTENCY: [0.0-1.0]

EVIDENCE:
- Tone: [How well does tone match brand?]
- Vocabulary: [Is language appropriate for audience?]
- Adaptation: [How does voice adapt across outputs?]
- Consistency: [Is voice stable across turns?]"""

    response = await api_client.call_model(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500,
    )
    analysis = response["response"]
    evidence_entry = f"Judge {model}:\n{analysis[:500]}..."

    scores = _parse_voice_evaluation(analysis)
    return scores, evidence_entry, analysis


def _parse_voice_evaluation(analysis: str) -> Dict[str, float]:
    """Parse LLM voice evaluation response."""
    scores = {
        "tone_consistency": 0.5,
        "vocabulary_match": 0.5,
        "format_adaptation": 0.5,
        "cross_output_consistency": 0.5,
    }

    for line in analysis.split("\n"):
        line = line.strip()
        for key in scores:
            label = key.upper()
            if line.upper().startswith(label + ":"):
                try:
                    # Extract number from line
                    value_part = line.split(":", 1)[1].strip()
                    # Handle formats like "0.8" or "0.8 - good" etc
                    value = float(value_part.split()[0])
                    scores[key] = max(0.0, min(1.0, value))
                except (ValueError, IndexError):
                    pass

    return scores


def _evaluate_voice_deterministic(
    responses: List[Dict[str, Any]],
    brand: Dict[str, Any],
    banned_found: List[str],
    result: Dict[str, Any],
) -> None:
    """Fallback deterministic voice check."""

    tone_keywords = set(kw.lower() for kw in brand.get("tone_keywords", []))
    constraints = brand.get("constraints", [])

    # Simple heuristics
    all_text = " ".join(r["content"].lower() for r in responses)
    words = set(all_text.split())

    # Tone keyword presence
    keyword_matches = len(tone_keywords & words)
    tone_score = min(1.0, keyword_matches / max(1, len(tone_keywords)))

    # Vocabulary consistency (word overlap between turns)
    if len(responses) > 1:
        turn_words = [set(r["content"].lower().split()) for r in responses]
        overlaps = []
        for i in range(len(turn_words) - 1):
            intersection = len(turn_words[i] & turn_words[i + 1])
            union = len(turn_words[i] | turn_words[i + 1])
            overlaps.append(intersection / max(1, union))
        consistency_score = statistics.mean(overlaps) if overlaps else 0.5
    else:
        consistency_score = 0.5

    # Penalty for banned phrases
    banned_penalty = min(0.5, len(banned_found) * 0.1)

    overall = (tone_score * 0.4 + 0.5 * 0.3 + consistency_score * 0.3) - banned_penalty

    result["score"] = max(0, overall)
    result["breakdown"] = {
        "tone_consistency": tone_score,
        "vocabulary_match": 0.5,  # Cannot evaluate without LLM
        "format_adaptation": 0.5,  # Cannot evaluate without LLM
        "cross_output_consistency": consistency_score,
        "banned_phrases_found": banned_found,
        "method": "deterministic",
    }
    result["evidence"].append("Deterministic fallback used")
