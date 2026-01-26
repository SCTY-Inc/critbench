"""Voice scorer - evaluates brand consistency across outputs.

Tests whether the model maintains consistent brand voice across
multiple outputs, formats, and turns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def score(
    transcript: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    brand: Dict[str, Any],
    api_client: Optional[Any] = None,
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
    """
    # TODO: Implement multi-judge voice scoring
    return {
        "score": 0.5,
        "breakdown": {
            "tone_consistency": 0.5,
            "vocabulary_match": 0.5,
            "format_adaptation": 0.5,
            "cross_output_consistency": 0.5,
            "banned_phrases_found": [],
        },
        "evidence": ["Voice scorer not yet implemented"],
    }
