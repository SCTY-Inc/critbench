# CritBench

Benchmark for creative process, not just creative output. Scenarios run a model
through a multi-turn agency workflow (brief intake, insight, strategy, idea
selection, execution, refinement, pressure tests) and score the transcript
against per-turn rubrics.

## Install

```bash
uv tool install git+https://github.com/SCTY-Inc/critbench  # installs the `critbench` command
```

For development:

```bash
git clone https://github.com/SCTY-Inc/critbench && cd critbench
uv sync --extra dev
uv run pytest -q
```

## Usage

```bash
critbench run --model <model> --scenario benchmark/scenarios/tier1/campaign/saas_launch.json
critbench run --model <model> --scenario <file> --dry-run    # show scenario, no API call
critbench score --help                                       # score an existing transcript
critbench leaderboard --results results                      # table from saved score files
```

Model calls and multi-judge scoring go through OpenRouter (`OPENROUTER_API_KEY`).

Offline validation (no API calls):

```bash
uv run python benchmark/scripts/validation/run_minimal.py -y   # tier 0
uv run python benchmark/scripts/validation/run_full.py -y      # tier 0 + tier 1
```

From Python:

```python
from critbench import score

result = score(
    transcript_path="path/to/transcript.jsonl",
    scenario_path="benchmark/scenarios/tier1/campaign/saas_launch.json",
)
print(result["overall_percentage"])
```

## Scoring

Weights live in `benchmark/configs/scoring.yaml`:

| Dimension | Weight | Measures |
|-----------|--------|----------|
| coherence | 25% | each stage ladders to the next |
| judgment | 20% | selects good ideas, not just generates |
| voice | 20% | brand consistency across formats and turns |
| originality | 15% | non-obvious insights, hooks, ideas |
| ethics | 10% | resists dark patterns, holds guidelines |
| adaptation | 10% | takes feedback without losing strategy |

Scoring uses each scenario's `rubric_criteria` and `expected_behaviors`.
Dimensions with no criteria are skipped and weights renormalize.

Autofail (score zero): endorsed dark patterns, banned phrases, banned
competitor mentions, and scenario-defined structural triggers (for example no
questions on a turn that requires them).

Optional multi-judge scoring averages several judge models; if every judge call
fails, scoring falls back to the deterministic rubric path.

## Scenarios

3 tier 0 and 12 tier 1 campaign scenarios in `benchmark/scenarios/`. Format:
`benchmark/scenarios/README.md`. Background reading: `benchmark/docs/REFERENCES.md`.

## Citation

```bibtex
@software{critbench2026,
  title={CritBench: Creative Process Benchmark for Large Language Models},
  author={Ali Madad},
  year={2026},
  url={https://github.com/SCTY-Inc/critbench}
}
```

## License

MIT
