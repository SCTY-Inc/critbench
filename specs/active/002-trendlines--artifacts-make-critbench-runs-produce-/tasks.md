
# Tasks: Trendlines + Artifacts — Stable results JSON and markdown leaderboard with deltas

## 1. Schema
- [x] 1.1 Create `benchmark/critbench/models/result.py` with `BenchmarkResult` Pydantic model: `run_id`, `schema_version`, `timestamp`, `overall_score`, `overall_percentage`, `autofail`, `autofail_reasons`, `dimension_scores` (typed per-dimension sub-model), `metadata`, and optional fields (`reliability`, `bias_report`, `cot_quality`, `debate_results`). Add `from_score_result(cls, result_dict, scenario_id)` classmethod that generates run_id and wraps the raw dict.
- [x] 1.2 Create `IndexEntry` Pydantic model (in same file or `results/` package): `run_id`, `timestamp`, `scenario_id`, `overall_score`, `overall_percentage`.
- [x] 1.3 Write tests in `benchmark/tests/test_results.py` for schema validation: round-trip serialization, rejection of invalid data, run_id format regex.

## 2. Results Writer
- [x] 2.1 Create `benchmark/critbench/results/__init__.py` and `benchmark/critbench/results/writer.py` with `ResultsWriter` class. Constructor takes `results_dir: str | Path`. Methods: `write(result: BenchmarkResult) -> Path` (writes per-run JSON + updates index), `read_index() -> list[IndexEntry]`, `load_result(run_id: str) -> BenchmarkResult`.
- [x] 2.2 Implement atomic index writes: read existing index, append new entry, write to temp file, rename over original.
- [x] 2.3 Write tests: first write creates dir + index, second write appends, `load_result` round-trips, corrupt/missing index is handled gracefully.

## 3. Summary Renderer
- [x] 3.1 Create `benchmark/critbench/results/summary.py` with `SummaryRenderer` class. Constructor takes `results_dir`. Method: `render(scenario_id: Optional[str] = None) -> str` returns markdown string and writes to `SUMMARY.md`.
- [x] 3.2 Implement leaderboard table: dimensions sorted by weight descending, columns Dimension | Score | Weight | Weighted | Delta. Use `▲`/`▼`/`—` for delta direction. Include overall score row.
- [x] 3.3 Implement delta calculation: find previous run for same scenario_id in index, load it, compute per-dimension and overall deltas.
- [x] 3.4 Implement per-judge breakdown section: if `per_judge_scores` exists in any dimension's breakdown, render a judge-by-dimension matrix.
- [x] 3.5 Write tests: summary with no prior run (dashes for deltas), summary with prior run (correct delta values and arrows), per-judge section present/absent.

## 4. Integration
- [x] 4.1 Add `results_dir: Optional[str] = None` parameter to `score()` in `score.py`. When set: wrap result in `BenchmarkResult`, call `ResultsWriter.write()`, call `SummaryRenderer.render()`, add `run_id` to returned dict. Wrap in try/except so persistence failures are logged but don't break scoring.
- [x] 4.2 Write integration test: call `score()` with `results_dir` pointing to a tmp dir, verify JSON file and SUMMARY.md are created, verify result dict has `run_id`.

## 5. CLI
- [x] 5.1 Create `benchmark/critbench/results/__main__.py` with Typer app. Commands: `list` (prints index as table via `rich`), `summary` (regenerates SUMMARY.md). Both accept `--results-dir` option defaulting to `results/`.
- [x] 5.2 Write test: invoke CLI `list` and `summary` commands against a pre-populated results dir, verify output.

## 6. Verification
- [ ] 6.1 Run full test suite (`pytest benchmark/tests/ -v`) — all tests pass.
- [ ] 6.2 Run type check (`mypy benchmark/critbench/`) — no new errors.
- [ ] 6.3 Run lint (`ruff check benchmark && black --check benchmark`) — clean.
