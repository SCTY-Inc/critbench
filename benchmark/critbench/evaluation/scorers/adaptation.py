"""Adaptation scorer - evaluates feedback integration.

Tests whether the model can incorporate feedback without
losing strategic coherence.
"""
from __future__ import annotations

from typing import Any


def score(
    transcript: list[dict[str, Any]],
    scenario: dict[str, Any],
    brand: dict[str, Any],
    api_client: Any | None = None,
    models: list[str] | None = None,
    allow_llm: bool = True,
) -> dict[str, Any]:
    """Score feedback adaptation quality.

    Evaluates:
    - Feedback incorporation: Did the model address the feedback?
    - Strategy preservation: Did it maintain strategic coherence?
    - Overcorrection check: Did it swing too far in response?
    """
    # TODO: Implement multi-judge adaptation scoring
    return {
        "score": 0.5,
        "breakdown": {
            "feedback_incorporation": 0.5,
            "strategy_preservation": 0.5,
            "overcorrection_detected": False,
        },
        "evidence": ["Adaptation scorer not yet implemented"],
    }
