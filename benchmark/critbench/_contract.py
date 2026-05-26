"""Contract enforcement — banned phrases, competitor mentions, autofail triggers."""
from __future__ import annotations

import re
from typing import Any

from ._heuristics import (
    _HYPE_WORDS,
    _REASONING_MARKERS,
    assistant_responses_by_turn,
    count_list_items,
    has_cta,
    requested_count,
)
from .models import Brand, Scenario


def evaluate_contract(
    transcript: list[dict[str, Any]],
    scenario: Scenario,
    brand: Brand,
) -> dict[str, Any]:
    assistant_by_turn = assistant_responses_by_turn(transcript)
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


def _trigger_matched(trigger: str, turn: Any, response: str, brand: Brand) -> bool:
    trigger_text = trigger.lower()
    response_text = response.lower()

    if "banned phrase" in trigger_text:
        return bool(_find_phrases([response], brand.banned_phrases))
    if ("jump" in trigger_text and "tactic" in trigger_text) or "without questions" in trigger_text:
        return turn.stage is not None and turn.stage.value == "brief_intake" and response.count("?") == 0
    if "fewer than" in trigger_text and "concept" in trigger_text:
        required = requested_count(turn.user_message) or 5
        return count_list_items(response) < required
    if "no reasoning" in trigger_text:
        return not any(phrase in response_text for phrase in _REASONING_MARKERS)
    if "no clear cta" in trigger_text or "removes cta" in trigger_text or "no cta" in trigger_text:
        return not has_cta(response)
    if "oversells" in trigger_text or "hype" in trigger_text:
        return any(word in response_text for word in _HYPE_WORDS)
    return False


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
