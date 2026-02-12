# Log: Trendlines + artifacts: make critbench runs produce a stable results JSON + a markdown summary (leaderboard + deltas) so progress is legible.

## 2026-02-12
- Spec generated from backlog

### Iteration 1 - 04:08:11
Task: 1.1 Create `benchmark/critbench/models/result.py` with `BenchmarkResult` Pydantic model: `run_id`, `schema_version`, `timestamp`, `overall_score`, `overall_percentage`, `autofail`, `autofail_reasons`, `dimension_scores` (typed per-dimension sub-model), `metadata`, and optional fields (`reliability`, `bias_report`, `cot_quality`, `debate_results`). Add `from_score_result(cls, result_dict, scenario_id)` classmethod that generates run_id and wraps the raw dict.
Result: ✓ Complete

### Iteration 2 - 04:08:40
Task: 1.2 Create `IndexEntry` Pydantic model (in same file or `results/` package): `run_id`, `timestamp`, `scenario_id`, `overall_score`, `overall_percentage`.
Result: ✓ Complete
