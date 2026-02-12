
# Proposal: Trendlines + Artifacts — Stable results JSON and markdown leaderboard with deltas

## Intent

CritBench can score transcripts but produces no persistent output. The `score()` function returns a dict that evaporates when the process exits. There is no way to:

1. Compare today's run against yesterday's run
2. See which model or dimension regressed
3. Share a quick summary with a human reviewer

Without trendlines, the benchmark is a black box — you run it, see numbers in the terminal, and forget them. This spec adds the minimum artifacts needed to make progress legible: a stable JSON file per run, a summary markdown file (leaderboard + deltas), and a thin results index so historical data stays accessible.

## Scope

**In scope:**
- A `BenchmarkResult` Pydantic model that defines the schema of a single benchmark run
- A `ResultsWriter` that persists each run as a timestamped JSON file under `results/`
- A `SummaryRenderer` that reads the latest run (and optionally the previous run) and emits a markdown file with a leaderboard table and per-dimension deltas
- A `results/index.json` manifest listing all runs for fast lookup without globbing
- Integration into `score()` via an optional `results_dir` parameter — when set, auto-persist
- A standalone CLI entrypoint (`python -m benchmark.critbench.results`) that can re-generate summaries from existing JSON

**Out of scope:**
- HTML reports or dashboards (future spec)
- Chart/graph generation (keep it text-only for now)
- Database storage — flat JSON files are sufficient at this scale
- CI integration or GitHub Actions workflow
- Changing the scoring logic itself

## Approach

1. **Define the schema** — A `BenchmarkResult` Pydantic model in `benchmark/critbench/models/result.py` that wraps the current `score()` return dict with explicit fields, a `run_id` (ISO 8601 timestamp + 6-char hash), and a `schema_version` field for forward compatibility.

2. **Write results** — `ResultsWriter` in `benchmark/critbench/results/writer.py` saves each result as `results/{run_id}.json` and appends an entry to `results/index.json`. The index is a flat JSON array of summary entries (run_id, timestamp, scenario_id, overall_score, overall_percentage).

3. **Render summary** — `SummaryRenderer` in `benchmark/critbench/results/summary.py` reads the two most recent runs for the same scenario and produces `results/SUMMARY.md` containing:
   - Header with timestamp and run metadata
   - Leaderboard table: dimension | score | weight | weighted | delta (vs previous)
   - Overall score with delta
   - Autofail status
   - Per-judge breakdown (if `per_judge_scores` present in breakdown)

4. **Wire into score()** — Add an optional `results_dir: Optional[str] = None` parameter to `score()`. When non-None, after scoring completes, persist the result and regenerate the summary. Zero behavior change when omitted.

5. **Standalone CLI** — `python -m benchmark.critbench.results summary` re-renders SUMMARY.md from existing data. `python -m benchmark.critbench.results list` shows all runs in a table.

