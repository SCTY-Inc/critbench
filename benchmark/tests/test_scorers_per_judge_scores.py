"""Tests for per-judge score preservation in scorer outputs."""

from __future__ import annotations

import asyncio

import pytest

from critbench.evaluation.scorers import coherence, judgment, voice


TRANSCRIPT = [
    {"turn": 1, "role": "assistant", "content": "Brief understanding response."},
    {"turn": 2, "role": "assistant", "content": "Generated insights."},
    {"turn": 3, "role": "assistant", "content": "Strategy response."},
    {"turn": 4, "role": "assistant", "content": "Idea generation response."},
    {"turn": 5, "role": "assistant", "content": "Idea selection response."},
]

SCENARIO = {
    "turns": [
        {"turn_number": 1, "stage": "brief_intake"},
        {"turn_number": 2, "stage": "insight_generation"},
        {"turn_number": 3, "stage": "strategy"},
        {"turn_number": 4, "stage": "idea_generation"},
        {"turn_number": 5, "stage": "idea_selection"},
    ]
}

BRAND = {
    "name": "Brand",
    "voice": "clear",
    "audience": "testers",
    "tone_keywords": ["clear"],
    "constraints": [],
    "banned_phrases": [],
}

MODELS = ["judge_a", "judge_b"]


def test_coherence_score_includes_per_judge_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    score_map = {
        "judge_a": {
            "brief_understanding": 0.9,
            "insight_to_strategy": 0.8,
            "strategy_to_creative": 0.7,
            "internal_consistency": 0.6,
        },
        "judge_b": {
            "brief_understanding": 0.5,
            "insight_to_strategy": 0.6,
            "strategy_to_creative": 0.7,
            "internal_consistency": 0.8,
        },
    }

    def _fake_eval(stages, brand, scenario, api_client, model, evidence):
        return score_map[model]

    monkeypatch.setattr(coherence, "_evaluate_with_model", _fake_eval)

    result = coherence.score(
        TRANSCRIPT,
        SCENARIO,
        BRAND,
        api_client=object(),
        models=MODELS,
        allow_llm=True,
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.765)
    assert per_judge["judge_b"] == pytest.approx(0.635)


def test_coherence_score_async_includes_per_judge_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    score_map = {
        "judge_a": {
            "brief_understanding": 0.9,
            "insight_to_strategy": 0.8,
            "strategy_to_creative": 0.7,
            "internal_consistency": 0.6,
        },
        "judge_b": {
            "brief_understanding": 0.5,
            "insight_to_strategy": 0.6,
            "strategy_to_creative": 0.7,
            "internal_consistency": 0.8,
        },
    }

    async def _fake_eval_async(stages, brand, scenario, api_client, model):
        return score_map[model], f"{model} ok"

    monkeypatch.setattr(coherence, "_evaluate_with_model_async", _fake_eval_async)

    result = asyncio.run(
        coherence.score_async(
            TRANSCRIPT,
            SCENARIO,
            BRAND,
            api_client=object(),
            models=MODELS,
            allow_llm=True,
        )
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.765)
    assert per_judge["judge_b"] == pytest.approx(0.635)


def test_judgment_score_includes_per_judge_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    score_map = {
        "judge_a": {
            "selection_reasoning": 0.9,
            "strategy_alignment": 0.8,
            "feasibility_awareness": 0.7,
            "selection_quality": 0.6,
        },
        "judge_b": {
            "selection_reasoning": 0.5,
            "strategy_alignment": 0.6,
            "feasibility_awareness": 0.7,
            "selection_quality": 0.8,
        },
    }

    def _fake_eval(ideas, selection, positioning, brand, api_client, model, evidence):
        return score_map[model]

    monkeypatch.setattr(judgment, "_evaluate_with_model", _fake_eval)

    result = judgment.score(
        TRANSCRIPT,
        SCENARIO,
        BRAND,
        api_client=object(),
        models=MODELS,
        allow_llm=True,
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.8)
    assert per_judge["judge_b"] == pytest.approx(0.6)


def test_judgment_score_async_includes_per_judge_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    score_map = {
        "judge_a": {
            "selection_reasoning": 0.9,
            "strategy_alignment": 0.8,
            "feasibility_awareness": 0.7,
            "selection_quality": 0.6,
        },
        "judge_b": {
            "selection_reasoning": 0.5,
            "strategy_alignment": 0.6,
            "feasibility_awareness": 0.7,
            "selection_quality": 0.8,
        },
    }

    async def _fake_eval_async(ideas, selection, positioning, brand, api_client, model):
        return score_map[model]

    monkeypatch.setattr(judgment, "_evaluate_with_model_async", _fake_eval_async)

    result = asyncio.run(
        judgment.score_async(
            TRANSCRIPT,
            SCENARIO,
            BRAND,
            api_client=object(),
            models=MODELS,
            allow_llm=True,
        )
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.8)
    assert per_judge["judge_b"] == pytest.approx(0.6)


def test_voice_score_includes_per_judge_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    score_map = {
        "judge_a": {
            "tone_consistency": 0.9,
            "vocabulary_match": 0.8,
            "format_adaptation": 0.7,
            "cross_output_consistency": 0.6,
        },
        "judge_b": {
            "tone_consistency": 0.5,
            "vocabulary_match": 0.6,
            "format_adaptation": 0.7,
            "cross_output_consistency": 0.8,
        },
    }

    def _fake_eval(responses, brand, scenario, api_client, model, evidence):
        return score_map[model], f"{model} reason"

    monkeypatch.setattr(voice, "_evaluate_with_model", _fake_eval)

    result = voice.score(
        TRANSCRIPT,
        SCENARIO,
        BRAND,
        api_client=object(),
        models=MODELS,
        allow_llm=True,
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.775)
    assert per_judge["judge_b"] == pytest.approx(0.625)


def test_voice_score_async_includes_per_judge_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    score_map = {
        "judge_a": {
            "tone_consistency": 0.9,
            "vocabulary_match": 0.8,
            "format_adaptation": 0.7,
            "cross_output_consistency": 0.6,
        },
        "judge_b": {
            "tone_consistency": 0.5,
            "vocabulary_match": 0.6,
            "format_adaptation": 0.7,
            "cross_output_consistency": 0.8,
        },
    }

    async def _fake_eval_async(responses, brand, scenario, api_client, model):
        return score_map[model], f"{model} ok", f"{model} reasoning"

    monkeypatch.setattr(voice, "_evaluate_with_model_async", _fake_eval_async)

    result = asyncio.run(
        voice.score_async(
            TRANSCRIPT,
            SCENARIO,
            BRAND,
            api_client=object(),
            models=MODELS,
            allow_llm=True,
        )
    )

    per_judge = result["breakdown"]["per_judge_scores"]
    assert set(per_judge.keys()) == set(MODELS)
    assert per_judge["judge_a"] == pytest.approx(0.775)
    assert per_judge["judge_b"] == pytest.approx(0.625)
