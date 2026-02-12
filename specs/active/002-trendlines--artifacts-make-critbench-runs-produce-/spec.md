
# Spec: Trendlines + Artifacts — Stable results JSON and markdown leaderboard with deltas

## Requirements

### Requirement 1: Stable results JSON schema

The system SHALL define a `BenchmarkResult` Pydantic model that captures the complete output of a `score()` call with a versioned, forward-compatible schema.

#### Scenario: Score result round-trips through JSON

- GIVEN a `score()` return dict from any scenario (tier 0-3, LLM enabled or disabled)
- WHEN the dict is wrapped in `BenchmarkResult.from_score_result(result, scenario_id=...)`
- THEN the model validates successfully, `result.schema_version` equals `"1"`, `result.run_id` is a non-empty string matching `^\d{8}T\d{6}Z-[a-f0-9]{6}$`, and `result.model_dump_json() | json.loads` round-trips without data loss (all dimension scores, breakdowns, metadata, and optional fields preserved).

#### Scenario: Schema rejects invalid data

- GIVEN a dict missing `overall_score` or with `dimension_scores` as a string instead of dict
- WHEN passed to `BenchmarkResult.from_score_result()`
- THEN a `ValidationError` is raised.

### Requirement 2: Results persistence

The system SHALL persist each benchmark result as an individual JSON file and maintain a cumulative index.

#### Scenario: First run creates results directory and index

- GIVEN `results/` does not exist
- WHEN `ResultsWriter(results_dir="results/").write(benchmark_result)` is called
- THEN `results/` is created, `results/{run_id}.json` contains the full `BenchmarkResult` JSON, and `results/index.json` is created as a JSON array with one entry containing `run_id`, `timestamp`, `scenario_id`, `overall_score`, and `overall_percentage`.

#### Scenario: Subsequent run appends to index

- GIVEN `results/index.json` already has 3 entries
- WHEN a new result is written
- THEN `results/index.json` has 4 entries, the newest entry is last, all previous entries are unchanged, and the new per-run JSON file exists alongside the 3 prior files.

#### Scenario: Concurrent writes do not corrupt index

- GIVEN two `ResultsWriter` instances writing simultaneously
- WHEN both call `write()` at the same time
- THEN the index contains both entries (no data loss), achieved via atomic file writes (write to temp + rename).

### Requirement 3: Markdown summary with leaderboard and deltas

The system SHALL generate a human-readable markdown summary showing scores and changes from the previous run.

#### Scenario: Summary with no prior run (first run for scenario)

- GIVEN one result in the index for scenario `tier1_campaign_001`
- WHEN `SummaryRenderer(results_dir="results/").render()` is called
- THEN `results/SUMMARY.md` contains:
  - A header with run timestamp and scenario ID
  - A table with columns: Dimension | Score | Weight | Weighted | Delta
  - All 6 dimensions listed in weight-descending order (coherence, judgment, voice, originality, ethics, adaptation)
  - Delta column shows `—` (em-dash) for each dimension (no baseline)
  - Overall score and percentage at the bottom
  - Autofail status line (only if autofail is true)

#### Scenario: Summary with prior run shows deltas

- GIVEN two results in the index for scenario `tier1_campaign_001`, with the older run scoring coherence=0.70 and the newer scoring coherence=0.82
- WHEN `SummaryRenderer(results_dir="results/").render()` is called
- THEN the coherence row's Delta column shows `+0.12` (green up-arrow prefix `▲` if positive, red down-arrow `▼` if negative, `—` if zero within ±0.005)
- AND the "vs previous" line references the prior run_id

#### Scenario: Summary includes per-judge breakdown when available

- GIVEN a result where `dimension_scores.coherence.breakdown.per_judge_scores` contains `{"claude-sonnet-4-20250514": 0.78, "gpt-4.1": 0.72, "gemini-2.0-flash": 0.81}`
- WHEN the summary is rendered
- THEN a "Per-Judge Scores" section appears below the leaderboard showing each judge model and its per-dimension composite score.

### Requirement 4: Integration into score()

The `score()` function SHALL accept an optional `results_dir` parameter that, when provided, triggers automatic persistence and summary generation.

#### Scenario: score() without results_dir (default, no change)

- GIVEN `results_dir` is not passed (or is None)
- WHEN `score()` is called
- THEN behavior is identical to the current implementation; no files are written.

#### Scenario: score() with results_dir persists and renders

- GIVEN `results_dir="results/"` is passed
- WHEN `score()` completes successfully
- THEN `results/{run_id}.json` exists, `results/index.json` is updated, `results/SUMMARY.md` is regenerated, and the return dict includes a new `"run_id"` key.

#### Scenario: Persistence failure does not break scoring

- GIVEN `results_dir` points to a read-only path
- WHEN `score()` runs and persistence fails
- THEN `score()` still returns the correct result dict (persistence errors are logged, not raised).

### Requirement 5: Standalone results CLI

The system SHALL provide a CLI for inspecting and regenerating results artifacts.

#### Scenario: List runs

- GIVEN 5 results in `results/index.json`
- WHEN `python -m benchmark.critbench.results list --results-dir results/` is run
- THEN stdout shows a table of all 5 runs with columns: run_id, scenario, overall%, sorted by timestamp descending.

#### Scenario: Regenerate summary

- GIVEN 3 result JSON files in `results/`
- WHEN `python -m benchmark.critbench.results summary --results-dir results/` is run
- THEN `results/SUMMARY.md` is regenerated from the latest run and its delta computed against the prior run for the same scenario.

## Completion Signal

```bash
# All must pass
pytest benchmark/tests/test_results.py -v
python -c "from critbench.models.result import BenchmarkResult; print('schema ok')"
python -c "from critbench.results.writer import ResultsWriter; print('writer ok')"
python -c "from critbench.results.summary import SummaryRenderer; print('renderer ok')"
```

