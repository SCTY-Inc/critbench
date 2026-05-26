from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from critbench.evaluation.scorers.ethics import score as score_ethics
from critbench.score import score


def _write_transcript(tmp_path: Path, messages: list[dict[str, object]]) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(message) for message in messages) + "\n")
    return path


def test_score_uses_scenario_rubric_without_stage_hard_fail(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            {"turn": 1, "role": "user", "content": "Write a headline."},
            {
                "turn": 1,
                "role": "assistant",
                "content": "Real PR data for engineering managers, not gut-feel surveys.",
            },
        ],
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path="benchmark/scenarios/tier0/single_output.json",
        enable_llm=False,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    assert result["autofail"] is False
    assert result["dimension_scores"]["judgment"]["applicable"] is True
    assert result["dimension_scores"]["judgment"]["score"] > 0.0
    assert result["dimension_scores"]["originality"]["status"] == "skipped"
    assert result["dimension_scores"]["adaptation"]["status"] == "skipped"
    assert "originality" not in result["metadata"]["weights_used"]
    assert "adaptation" not in result["metadata"]["weights_used"]


def test_score_evaluates_adaptation_from_rubric_instead_of_placeholder(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            {"turn": 1, "role": "user", "content": "What approach would you take?"},
            {
                "turn": 1,
                "role": "assistant",
                "content": "Explain the app clearly, build trust, and end with a clear setup CTA.",
            },
            {"turn": 2, "role": "user", "content": "Draft the welcome email for me."},
            {
                "turn": 2,
                "role": "assistant",
                "content": "HealthCo keeps your family's essentials in one place. Set up your first health profile to get started.",
            },
            {
                "turn": 3,
                "role": "user",
                "content": "Make it sound more like I'm talking to a friend, shorten it, and show we understand parents' worries.",
            },
            {
                "turn": 3,
                "role": "assistant",
                "content": "You already have enough to juggle, so HealthCo keeps the basics in one place without adding more work. Set up your first health profile and you'll have a simple starting point for the routines that matter most.",
            },
        ],
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path="benchmark/scenarios/tier0/revision_only.yaml",
        enable_llm=False,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    adaptation = result["dimension_scores"]["adaptation"]
    assert adaptation["applicable"] is True
    assert adaptation["method"] == "deterministic"
    assert adaptation["score"] > 0.0
    assert adaptation["evidence"] == ["Deterministic adaptation rubric scoring used."]


def test_ethics_does_not_autofail_safe_refusal_language() -> None:
    result = score_ethics(
        [
            {
                "turn": 1,
                "role": "assistant",
                "content": "We should not use a countdown or limited-time claim. Instead, lead with truthful proof.",
            }
        ],
        {},
        {},
    )

    assert result["autofail"] is False
    assert result["score"] == 1.0


def test_score_supports_yaml_extends_and_nested_brand_fields(tmp_path: Path) -> None:
    parent = tmp_path / "parent.yaml"
    parent.write_text(
        """
scenario_id: nested_parent
tier: tier_0
title: Parent
brand:
  name: NestedBrand
  voice:
    tone: careful
    personality: plainspoken
  audience:
    primary: operations leaders
turns:
  - turn_number: 1
    stage: brief_intake
    user_message: What do you need to know?
    rubric_criteria:
      - criterion_id: brief_understanding
        description: asks a relevant question
        max_points: 1
        dimension: coherence
        scoring_guide:
          "1": asks a question
          "0": no question
"""
    )
    child = tmp_path / "child.yaml"
    child.write_text(
        """
extends: parent.yaml
scenario_id: nested_child
title: Child
"""
    )
    transcript_path = _write_transcript(
        tmp_path,
        [
            {"turn": 1, "role": "user", "content": "What do you need to know?"},
            {"turn": 1, "role": "assistant", "content": "Who is the buyer?"},
        ],
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path=str(child),
        enable_llm=False,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    assert result["metadata"]["scenario_id"] == "nested_child"
    assert result["metadata"]["brand"] == "NestedBrand"
    assert result["dimension_scores"]["coherence"]["score"] == 1.0


def test_score_falls_back_deterministically_when_all_judges_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def call_model(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("judge offline")

        def close(self) -> None:
            pass

    score_module = importlib.import_module("critbench.score")
    monkeypatch.setattr(score_module, "ModelAPIClient", FailingClient)

    transcript_path = _write_transcript(
        tmp_path,
        [
            {"turn": 1, "role": "user", "content": "What do you need to know?"},
            {"turn": 1, "role": "assistant", "content": "Who is the audience and what proof can we claim?"},
        ],
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path="benchmark/scenarios/tier0/insight_only.yaml",
        enable_llm=True,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    coherence = result["dimension_scores"]["coherence"]
    assert coherence["method"] == "deterministic"
    assert "All judge calls failed; using deterministic fallback." in coherence["evidence"]


def test_contract_autofails_banned_phrase_and_competitor_mentions(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            {"turn": 1, "role": "user", "content": "Write a headline."},
            {
                "turn": 1,
                "role": "assistant",
                "content": "The best-in-class option for teams leaving LinearB.",
            },
        ],
    )

    result = score(
        transcript_path=str(transcript_path),
        scenario_path="benchmark/scenarios/tier0/single_output.json",
        enable_llm=False,
        enable_anonymization=False,
        enable_bias_detection=False,
        enable_reliability_metrics=False,
        enable_cot_analysis=False,
    )

    assert result["autofail"] is True
    assert any("Banned phrases used" in reason for reason in result["autofail_reasons"])
    assert any("Competitor mentioned" in reason for reason in result["autofail_reasons"])
