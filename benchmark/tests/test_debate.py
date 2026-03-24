"""Tests for debate orchestrator module."""
from unittest.mock import Mock

from critbench.evaluation.debate.orchestrator import (
    DebateOrchestrator,
    DebateResult,
    DebateRound,
    run_debate,
)


class TestDebateOrchestrator:
    """Tests for debate orchestrator."""

    def test_init_defaults(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        assert orchestrator.disagreement_threshold == 0.3
        assert orchestrator.confidence_threshold == 0.7
        assert orchestrator.max_rounds == 2

    def test_should_trigger_debate_high_spread(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client, disagreement_threshold=0.2)

        scores = {"model_a": 0.9, "model_b": 0.5, "model_c": 0.7}
        should_trigger, reason = orchestrator.should_trigger_debate(scores)

        assert should_trigger is True
        assert "spread" in reason.lower()

    def test_should_trigger_debate_low_confidence(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client, confidence_threshold=0.8)

        scores = {"model_a": 0.7, "model_b": 0.65, "model_c": 0.72}
        should_trigger, reason = orchestrator.should_trigger_debate(scores, confidence=0.6)

        assert should_trigger is True
        assert "confidence" in reason.lower()

    def test_should_not_trigger_debate_agreement(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        scores = {"model_a": 0.8, "model_b": 0.78, "model_c": 0.82}
        should_trigger, reason = orchestrator.should_trigger_debate(scores, confidence=0.9)

        assert should_trigger is False

    def test_should_not_trigger_single_judge(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        scores = {"model_a": 0.8}
        should_trigger, reason = orchestrator.should_trigger_debate(scores)

        assert should_trigger is False
        assert "not enough" in reason.lower()

    def test_debate_result_structure(self):
        result = DebateResult(
            triggered=True,
            trigger_reason="High disagreement",
            initial_scores={"a": 0.9, "b": 0.5},
            initial_mean=0.7,
            initial_spread=0.4,
        )

        d = result.to_dict()
        assert d["triggered"] is True
        assert d["initial"]["spread"] == 0.4

    def test_debate_round_structure(self):
        round_result = DebateRound(
            round_number=1,
            initial_scores={"a": 0.9, "b": 0.5},
            arguments={"a": "My reasoning", "b": "My reasoning"},
            revised_scores={"a": 0.8, "b": 0.6},
            score_changes={"a": -0.1, "b": 0.1},
        )

        d = round_result.to_dict()
        assert d["round"] == 1
        assert d["score_changes"]["a"] == -0.1

    def test_parse_score(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        # Test various formats
        assert orchestrator._parse_score("REVISED_SCORE: 0.75", 0.5) == 0.75
        assert orchestrator._parse_score("revised score: 0.6", 0.5) == 0.6
        assert orchestrator._parse_score("score: 0.8", 0.5) == 0.8
        assert orchestrator._parse_score("no score here", 0.5) == 0.5  # default

    def test_parse_argument(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        text = "REVISED_SCORE: 0.7\nARGUMENT: This is my reasoning for the score."
        argument = orchestrator._parse_argument(text)

        assert "reasoning" in argument.lower()

    def test_run_debate_no_trigger(self):
        mock_client = Mock()
        orchestrator = DebateOrchestrator(mock_client)

        # Scores are close enough - no debate needed
        result = orchestrator.run_debate(
            dimension="coherence",
            scores={"a": 0.8, "b": 0.78},
            reasoning={"a": "Good", "b": "Good"},
            context="Test context",
            models=["a", "b"],
        )

        assert result.triggered is False
        assert len(result.rounds) == 0
        assert result.final_scores == {"a": 0.8, "b": 0.78}

    def test_run_debate_with_mock_responses(self):
        mock_client = Mock()
        mock_client.call_model.return_value = {
            "response": "REVISED_SCORE: 0.7\nARGUMENT: Reconsidered based on other views."
        }

        orchestrator = DebateOrchestrator(
            mock_client,
            disagreement_threshold=0.2,
            max_rounds=1,
        )

        result = orchestrator.run_debate(
            dimension="coherence",
            scores={"model_a": 0.9, "model_b": 0.5},
            reasoning={"model_a": "Very good", "model_b": "Poor"},
            context="Test context",
            models=["model_a", "model_b"],
        )

        assert result.triggered is True
        assert len(result.rounds) >= 1
        # Both models should have been called
        assert mock_client.call_model.call_count >= 2


class TestRunDebateConvenience:
    """Tests for run_debate convenience function."""

    def test_run_debate_function(self):
        mock_client = Mock()
        mock_client.call_model.return_value = {
            "response": "REVISED_SCORE: 0.65\nARGUMENT: Adjusted."
        }

        result = run_debate(
            api_client=mock_client,
            dimension="judgment",
            scores={"a": 0.8, "b": 0.4},
            reasoning={"a": "High", "b": "Low"},
            context="Context",
            models=["a", "b"],
            disagreement_threshold=0.2,
        )

        assert isinstance(result, DebateResult)
        assert result.triggered is True
