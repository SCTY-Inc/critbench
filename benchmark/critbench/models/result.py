"""Result schema models for persisted benchmark outputs."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from secrets import token_hex
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DimensionResult(BaseModel):
    """Generic per-dimension score payload."""

    model_config = ConfigDict(extra="allow")

    score: float
    breakdown: Dict[str, Any]
    evidence: List[str] = Field(default_factory=list)


class EthicsDimensionResult(DimensionResult):
    """Ethics can mark the run as autofail at dimension-level."""

    autofail: bool = False


class DimensionScores(BaseModel):
    """Strongly typed dimension container for all benchmark dimensions."""

    coherence: DimensionResult
    judgment: DimensionResult
    voice: DimensionResult
    originality: DimensionResult
    ethics: EthicsDimensionResult
    adaptation: DimensionResult


class BenchmarkResult(BaseModel):
    """Versioned benchmark result envelope."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    schema_version: Literal["1"] = "1"
    timestamp: datetime

    overall_score: float
    overall_percentage: float
    autofail: bool
    autofail_reasons: List[str] = Field(default_factory=list)

    dimension_scores: DimensionScores
    metadata: Dict[str, Any]

    reliability: Optional[Dict[str, Any]] = None
    bias_report: Optional[Dict[str, Any]] = None
    cot_quality: Optional[Dict[str, Any]] = None
    debate_results: Optional[Dict[str, Any]] = None

    @classmethod
    def from_score_result(cls, result_dict: Dict[str, Any], scenario_id: str) -> "BenchmarkResult":
        """Create a persisted benchmark result from a raw score() dictionary."""
        now = datetime.now(timezone.utc)
        run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{token_hex(3)}"

        payload = deepcopy(result_dict)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata.setdefault("scenario_id", scenario_id)
        payload["metadata"] = metadata

        payload["run_id"] = run_id
        payload["schema_version"] = "1"
        payload["timestamp"] = now

        return cls.model_validate(payload)


class IndexEntry(BaseModel):
    """Compact index row for listing benchmark runs."""

    run_id: str
    timestamp: datetime
    scenario_id: str
    overall_score: float
    overall_percentage: float
