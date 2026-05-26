"""Deterministic rubric-scoring heuristics for CritBench."""
from __future__ import annotations

import re
from typing import Any

from .models import Brand, RubricCriterion, Turn

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "how", "i", "if", "in", "into", "is", "it", "its",
    "of", "on", "or", "our", "that", "the", "their", "them", "this",
    "to", "we", "what", "which", "who", "with", "you", "your",
}
_HYPE_WORDS = {
    "revolutionary", "game-changing", "best-in-class", "industry-leading",
    "cutting-edge", "disruptive", "world-class", "unprecedented",
}
_REASONING_MARKERS = {"because", "since", "so that", "therefore", "which is why", "this works"}
_TRADEOFF_MARKERS = {"however", "but", "while", "tradeoff", "trade-off", "although"}
_CTA_PATTERNS = (
    "see the docs", "get started", "sign up", "start", "set up", "create",
    "book", "try", "learn more", "read more", "view", "download", "explore",
)
_CONVERSATIONAL_MARKERS = {"you", "we", "your", "we're", "you're", "let's", "here's"}


def score_dimension_deterministic(
    *,
    dimension: str,
    transcript: list[dict[str, Any]],
    scenario_turns: list[Turn],
    brand: Brand,
    criteria: list[tuple[Turn, RubricCriterion]],
) -> dict[str, Any]:
    assistant_by_turn = assistant_responses_by_turn(transcript)
    turn_index = {turn.turn_number: idx for idx, turn in enumerate(scenario_turns)}
    total_points = sum(criterion.max_points for _, criterion in criteria)
    points_earned = 0.0
    criterion_scores: dict[str, Any] = {}

    for turn, criterion in criteria:
        response = assistant_by_turn.get(turn.turn_number, "")
        idx = turn_index[turn.turn_number]
        previous_turn = scenario_turns[idx - 1] if idx > 0 else None
        previous_response = assistant_by_turn.get(previous_turn.turn_number, "") if previous_turn else ""
        next_turn = scenario_turns[idx + 1] if idx + 1 < len(scenario_turns) else None
        next_response = assistant_by_turn.get(next_turn.turn_number, "") if next_turn else ""

        points = score_criterion_deterministic(
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


def score_criterion_deterministic(
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
    kind = criterion_kind(criterion.criterion_id)
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
        return scale_points(max_points, blend(overlap_ratio(text, user_text), insight_signal(text), 0.6))

    if kind in {"creative_translation", "insight_actionability"}:
        ideas = count_list_items(response)
        signal = max(overlap_ratio(text, user_text), insight_signal(text))
        if ideas >= 2 and signal >= 0.2:
            return max_points
        if ideas >= 1 or signal >= 0.15:
            return max_points * 0.5
        return 0.0

    if kind == "insight_depth":
        return scale_points(max_points, blend(insight_signal(text), overlap_ratio(text, user_text), 0.65))

    if kind in {
        "insight_to_strategy", "insight_to_strategy_coherence",
        "strategy_ladder", "coherence_preservation", "differentiator_connection",
    }:
        overlap = overlap_ratio(text, combined_context)
        if kind == "coherence_preservation":
            overlap = max(overlap, has_cta(response) * 0.3 + (len(response) <= len(previous_response) + 40) * 0.2)
        return scale_points(max_points, overlap)

    if kind == "email_clarity":
        signal = 0.0
        if any(token in text for token in {"helps", "track", "see", "understand", "plan", "family"}):
            signal += 0.5
        if has_cta(response):
            signal += 0.2
        if len(response.split()) <= 180:
            signal += 0.3
        return scale_points(max_points, signal)

    if kind in {"voice_match", "voice_compliance"}:
        return scale_points(max_points, voice_signal(response, brand))

    if kind == "tone_shift":
        signal = conversation_signal(response)
        if previous_response and len(response.split()) <= len(previous_response.split()):
            signal = min(1.0, signal + 0.2)
        return scale_points(max_points, signal)

    if kind == "cta_effectiveness":
        return max_points if has_cta(response) else 0.0

    if kind == "differentiation":
        signal = 0.0
        if any(name.lower() in text for name in brand.competitors):
            signal += 0.4
        if any(phrase in text for phrase in {"instead of", "unlike", "rather than", "not surveys", "gut-feel", "guesswork", "real data"}):
            signal += 0.6
        return scale_points(max_points, signal)

    if kind == "idea_volume":
        requested = requested_count(turn.user_message) or 5
        return max_points if count_list_items(response) >= requested else 0.0

    if kind == "idea_range":
        idea_lines = split_ideas(response)
        unique_ideas = len({idea[:60] for idea in idea_lines})
        if unique_ideas >= 3:
            return max_points
        if unique_ideas >= 2:
            return max_points * 0.5
        return 0.0

    if kind == "selection_reasoning":
        signal = 0.0
        if contains_any(text, _REASONING_MARKERS):
            signal += 0.5
        if contains_any(text, _TRADEOFF_MARKERS):
            signal += 0.2
        if mentions_audience_or_strategy(text, combined_context):
            signal += 0.3
        return scale_points(max_points, signal)

    if kind == "selection_quality":
        signal = 0.0
        if contains_any(text, _REASONING_MARKERS):
            signal += 0.4
        if any(token in text for token in {"strongest", "best", "fits", "audience", "positioning", "strategy"}):
            signal += 0.3
        if contains_any(text, _TRADEOFF_MARKERS):
            signal += 0.3
        return scale_points(max_points, signal)

    if kind == "audience_relevance":
        return scale_points(max_points, mentions_audience_or_strategy(text, user_text))

    if kind == "feedback_incorporation":
        return scale_points(max_points, feedback_signal(turn.user_message, response, previous_response))

    return scale_points(max_points, overlap_ratio(text, combined_context))


def assistant_responses_by_turn(transcript: list[dict[str, Any]]) -> dict[int, str]:
    responses: dict[int, str] = {}
    for message in transcript:
        if message.get("role") == "assistant":
            turn = message.get("turn")
            if turn is not None:
                responses[int(turn)] = str(message.get("content", ""))
    return responses


def criterion_kind(criterion_id: str) -> str:
    for suffix in (
        "brief_comprehension", "brief_understanding", "brief_engagement",
        "insight_comprehension", "creative_translation", "insight_actionability",
        "insight_depth", "insight_to_strategy_coherence", "insight_to_strategy",
        "differentiator_connection", "coherence_preservation", "email_clarity",
        "voice_match", "voice_compliance", "tone_shift", "cta_effectiveness",
        "differentiation", "idea_volume", "idea_range", "strategy_ladder",
        "selection_reasoning", "selection_quality", "audience_relevance",
        "feedback_incorporation",
    ):
        if criterion_id.endswith(suffix):
            return suffix
    return criterion_id


def requested_count(text: str) -> int | None:
    match = re.search(r"\b(\d+)\b(?=\s+(?:campaign\s+)?(?:concepts?|ideas?|options?))", text.lower())
    return int(match.group(1)) if match else None


def count_list_items(text: str) -> int:
    return len(split_ideas(text))


def split_ideas(text: str) -> list[str]:
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    numbered = [line for line in lines if re.match(r"^(?:\d+[.):]|[-•])\s*", line) or re.match(r"^\d+[.):]", line)]
    if numbered:
        return [re.sub(r"^(?:\d+[.):]|[-•])\s*", "", line).strip() for line in numbered]
    if len(lines) > 1:
        return lines
    parts = [part.strip() for part in re.split(r"(?:;|\n)", text) if part.strip()]
    return parts if len(parts) > 1 else ([text.strip()] if text.strip() else [])


def tokenize(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9']+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def overlap_ratio(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(right_tokens))


def insight_signal(text: str) -> float:
    markers = {
        "tension", "pressure", "frustrated", "skeptical", "guilt", "permission",
        "trust", "burnout", "guesswork", "evidence", "data", "because", "but", "between",
    }
    hits = sum(1 for marker in markers if marker in text)
    return min(1.0, hits / 4)


def voice_signal(text: str, brand: Brand) -> float:
    lowered = text.lower()
    signal = 0.6
    if any(phrase.lower() in lowered for phrase in brand.banned_phrases):
        signal -= 0.6
    if any(word in lowered for word in _HYPE_WORDS):
        signal -= 0.3
    if any("exclamation" in constraint.lower() for constraint in brand.constraints) and "!" in text:
        signal -= 0.2
    if brand.tone_keywords:
        signal += min(
            0.4,
            sum(1 for kw in brand.tone_keywords if kw.lower() in lowered) / max(1, len(brand.tone_keywords)),
        )
    return max(0.0, min(1.0, signal))


def conversation_signal(text: str) -> float:
    lowered = text.lower()
    signal = min(1.0, sum(1 for marker in _CONVERSATIONAL_MARKERS if marker in lowered) / 3)
    if "!" in text:
        signal = max(0.0, signal - 0.2)
    return signal


def mentions_audience_or_strategy(text: str, context: str) -> float:
    audience_terms = tokenize(context)
    if not audience_terms:
        return 0.0
    overlap = len(tokenize(text) & audience_terms)
    return min(1.0, overlap / 4)


def has_cta(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _CTA_PATTERNS)


def feedback_signal(feedback: str, response: str, previous_response: str) -> float:
    feedback_text = feedback.lower()
    response_text = response.lower()
    signal = 0.0
    if previous_response and len(response.split()) <= len(previous_response.split()):
        signal += 0.3
    if (
        any(word in feedback_text for word in {"friend", "conversational", "less corporate"})
        and conversation_signal(response) >= 0.5
    ):
        signal += 0.3
    if any(word in feedback_text for word in {"short", "long"}) and previous_response and len(response) < len(previous_response):
        signal += 0.2
    if overlap_ratio(response_text, feedback_text) >= 0.15:
        signal += 0.2
    return min(1.0, signal)


def contains_any(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def blend(primary: float, secondary: float, weight: float) -> float:
    return max(0.0, min(1.0, primary * weight + secondary * (1 - weight)))


def scale_points(max_points: float, score: float) -> float:
    return round(max_points * max(0.0, min(1.0, score)))
