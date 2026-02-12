"""Tests for benchmark result schema validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from critbench.models.result import BenchmarkResult
from critbench.results.writer import ResultsWriter

RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{6}$")


def _sample_score_result() -> dict:
    return {
        "overall_score": 0.8125,
        "overall_percentage": 81.25,
        "autofail": False,
        "autofail_reasons": [],
        "dimension_scores": {
            "coherence": {
                "score": 0.84,
                "breakdown": {
                    "brief_understanding": 0.8,
                    "insight_to_strategy": 0.86,
                    "strategy_to_creative": 0.88,
                    "internal_consistency": 0.82,
                },
                "evidence": ["Clear transition from insight to strategy"],
            },
            "judgment": {
                "score": 0.79,
                "breakdown": {
                    "selection_reasoning": 0.8,
                    "strategy_alignment": 0.78,
                    "feasibility_awareness": 0.76,
                    "selection_quality": 0.82,
                },
                "evidence": ["Tradeoff acknowledged"],
            },
            "voice": {
                "score": 0.83,
                "breakdown": {
                    "tone_consistency": 0.84,
                    "vocabulary_match": 0.8,
                    "format_adaptation": 0.82,
                    "cross_output_consistency": 0.86,
                },
                "evidence": ["Consistent voice across turns"],
            },
            "originality": {
                "score": 0.81,
                "breakdown": {"novelty": 0.82, "distinctiveness": 0.8},
                "evidence": ["Unexpected but relevant angle"],
            },
            "ethics": {
                "score": 0.9,
                "autofail": False,
                "breakdown": {"safety": 0.9, "manipulation_risk": 0.1},
                "evidence": ["No dark-pattern language"],
            },
            "adaptation": {
                "score": 0.7,
                "breakdown": {"channel_fit": 0.72, "audience_fit": 0.68},
                "evidence": ["Mostly aligned to audience"],
            },
        },
        "metadata": {
            "scenario_id": "tier1_campaign_001",
            "tier": "tier1",
            "llm_enabled": True,
        },
        "reliability": {"krippendorff_alpha": 0.71},
        "bias_report": {"flags": []},
        "cot_quality": {"overall_quality": 0.77},
        "debate_results": {"used": False},
    }


def test_benchmark_result_round_trip_serialization() -> None:
    result = BenchmarkResult.from_score_result(
        _sample_score_result(),
        scenario_id="tier1_campaign_001",
    )

    assert result.schema_version == "1"
    assert result.run_id
    assert RUN_ID_PATTERN.match(result.run_id)

    dumped = json.loads(result.model_dump_json())
    reloaded = BenchmarkResult.model_validate(dumped)

    assert reloaded.model_dump(mode="json") == result.model_dump(mode="json")


def test_benchmark_result_rejects_invalid_data() -> None:
    missing_overall = _sample_score_result()
    missing_overall.pop("overall_score")

    with pytest.raises(ValidationError):
        BenchmarkResult.from_score_result(missing_overall, scenario_id="tier1_campaign_001")

    bad_dimension_scores = _sample_score_result()
    bad_dimension_scores["dimension_scores"] = "not-a-dict"

    with pytest.raises(ValidationError):
        BenchmarkResult.from_score_result(bad_dimension_scores, scenario_id="tier1_campaign_001")


def test_benchmark_result_run_id_format_regex() -> None:
    result = BenchmarkResult.from_score_result(
        _sample_score_result(),
        scenario_id="tier1_campaign_001",
    )

    assert re.fullmatch(RUN_ID_PATTERN, result.run_id)


def test_results_writer_first_write_creates_dir_and_index(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    writer = ResultsWriter(results_dir)
    result = BenchmarkResult.from_score_result(
        _sample_score_result(),
        scenario_id="tier1_campaign_001",
    )

    run_path = writer.write(result)

    assert results_dir.exists()
    assert run_path == results_dir / f"{result.run_id}.json"
    assert run_path.exists()
    assert json.loads(run_path.read_text(encoding="utf-8")) == result.model_dump(mode="json")

    index_path = results_dir / "index.json"
    assert index_path.exists()
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(index_payload) == 1
    assert index_payload[0]["run_id"] == result.run_id
    assert index_payload[0]["scenario_id"] == "tier1_campaign_001"
    assert index_payload[0]["overall_score"] == result.overall_score
    assert index_payload[0]["overall_percentage"] == result.overall_percentage


def test_results_writer_second_write_appends_to_index(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    writer = ResultsWriter(results_dir)

    first_result = BenchmarkResult.from_score_result(
        _sample_score_result(),
        scenario_id="tier1_campaign_001",
    )
    writer.write(first_result)
    prior_index = json.loads((results_dir / "index.json").read_text(encoding="utf-8"))

    second_result_payload = _sample_score_result()
    second_result_payload["overall_score"] = 0.9
    second_result_payload["overall_percentage"] = 90.0
    second_result = BenchmarkResult.from_score_result(
        second_result_payload,
        scenario_id="tier1_campaign_001",
    )
    writer.write(second_result)

    index_payload = json.loads((results_dir / "index.json").read_text(encoding="utf-8"))
    assert len(index_payload) == 2
    assert index_payload[0] == prior_index[0]
    assert index_payload[-1]["run_id"] == second_result.run_id

    assert (results_dir / f"{first_result.run_id}.json").exists()
    assert (results_dir / f"{second_result.run_id}.json").exists()


def test_results_writer_load_result_round_trips(tmp_path: Path) -> None:
    writer = ResultsWriter(tmp_path / "results")
    result = BenchmarkResult.from_score_result(
        _sample_score_result(),
        scenario_id="tier1_campaign_001",
    )
    writer.write(result)

    loaded = writer.load_result(result.run_id)
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")


def test_results_writer_handles_missing_index_gracefully(tmp_path: Path) -> None:
    writer = ResultsWriter(tmp_path / "results")

    assert writer.read_index() == []


def test_results_writer_handles_corrupt_index_gracefully(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "index.json").write_text("{bad json", encoding="utf-8")

    writer = ResultsWriter(results_dir)

    assert writer.read_index() == []
