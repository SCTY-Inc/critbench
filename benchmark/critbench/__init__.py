"""
CritBench - Creative process benchmark for large language models.

Tests judgment, not just generation. Evaluates:
- Campaign coherence (insight → strategy → creative)
- Idea selection quality
- Voice consistency
- Originality
- Ethical boundaries
- Feedback adaptation

Public API:
    from critbench import score, score_with_rewards

    result = score("transcript.jsonl", "scenario.json")
    rewards = score_with_rewards("transcript.jsonl", "scenario.json")
"""

__version__ = "0.1.0"

from critbench.score import score, score_with_rewards

__all__ = ["score", "score_with_rewards", "__version__"]
