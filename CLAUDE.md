# CLAUDE.md

AI assistant instructions for CritBench (creative benchmark project).

## Project Type

**Research benchmark** for evaluating LLM creative process quality.

## Python Environment (REQUIRED)

This project uses `uv` for dependency management. **Always** invoke Python through `uv run`, never bare `python`/`pytest`/`mypy`. Bare invocations hit the system Python and fail with `ModuleNotFoundError` or `command not found`.

```bash
# Correct
uv run python benchmark/scripts/validation/run_minimal.py -y
uv run pytest benchmark/tests/ -v
uv run mypy benchmark/critbench/
uv run ruff check benchmark

# Wrong (will fail)
python benchmark/scripts/validation/run_minimal.py
pytest benchmark/tests/
```

## Critical Rules

- **No unnecessary docs**: Ask before creating .md files
- When done: Say "done"
- Keep repo minimal and focused

## CLI Commands

```bash
# === BENCHMARKING ===
# Quick validation (tier 0 offline smoke test)
uv run python benchmark/scripts/validation/run_minimal.py -y

# Full validation (tier 0 + tier 1 offline smoke test)
# Current suite: 12 tier1 campaign scenarios + 3 tier0 scenarios
uv run python benchmark/scripts/validation/run_full.py -y

# Dry run (list scenarios and estimated cost)
uv run python benchmark/scripts/validation/run_minimal.py --dry-run

# === SCORING (single scenario) ===
uv run python - <<'PY'
from critbench import score

result = score(
    transcript_path="path/to/transcript.jsonl",
    scenario_path="benchmark/scenarios/tier1/campaign/saas_launch.json",  # JSON or YAML
    # enable_llm=True           # set False for offline/deterministic-only
    # enable_verifier_mode=True # LLM-as-a-Verifier: K-repeated + continuous scores
    # verifier_k_repeats=3      # verifications per criterion per judge
)

print(result["overall_percentage"])
PY

# === TESTS ===
uv run pytest benchmark/tests/ -v
uv run pytest benchmark/tests/ -v --cov=benchmark.critbench

# === CODE QUALITY ===
uv run mypy benchmark/critbench/
uv run ruff check benchmark
uv run ruff format benchmark
```

## Architecture

```
benchmark/critbench/
├── __init__.py       # Public API: score, score_with_rewards
├── score.py          # Thin orchestrator: loaders, dimension dispatch, weight normalization
├── _heuristics.py    # Deterministic scoring heuristics + NLP helpers
├── _contract.py      # Banned phrases, competitor checks, autofail trigger matching
├── _llm_judge.py     # LLM judge calls, verifier mode, prompt building, JSON parsing
├── models/           # Brand normalization + Scenario/Turn dataclasses
├── evaluation/
│   ├── debate/       # Optional judge debate helpers
│   ├── metrics/      # Reliability / bias / CoT utilities
│   ├── preprocessing/
│   └── scorers/
│       └── ethics.py # Dark-pattern endorsement autofail
├── api/
│   └── client.py     # Multi-model ensemble client (OpenRouter)
├── loaders/
└── utils/
```

## Scoring Dimensions

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| coherence | 25% | Does each stage ladder to the next? |
| judgment | 20% | Can it select good ideas, not just generate? |
| voice | 20% | Brand consistency across formats and turns |
| originality | 15% | Non-obvious insights, hooks, ideas |
| ethics | 10% | Resists dark patterns, holds guidelines |
| adaptation | 10% | Learns without losing strategy |

## Scenario Format

```yaml
scenario_id: tier1_campaign_001
tier: tier_1
title: B2B SaaS Launch
brand:
  name: CodeFlow
  voice: technically credible, understated
  tone_keywords: [evidence, restrained]
  audience: senior engineers
  constraints: ["no 'revolutionary'", "no fake metrics"]
turns:
  - turn_number: 1
    stage: brief_intake
    user_message: We're launching CodeFlow...
    expected_behaviors: [asks clarifying questions]
    autofail_triggers: [jumps to tactics without understanding]
    rubric_criteria:
      - criterion_id: brief_comprehension
        description: asks useful clarifying questions
        max_points: 2
        dimension: coherence
        scoring_guide:
          "2": asks 2+ relevant questions
          "1": asks 1 relevant question
          "0": jumps ahead without clarifying
```

`score()` evaluates the scenario's own `rubric_criteria` and `expected_behaviors`. Dimensions without rubric criteria are skipped and the overall score is renormalized over the applicable dimensions.

## Multi-Judge Scoring

When LLM judging is enabled, multiple judge models score the same rubric:
- Claude, GPT-4, Gemini can score the same scenario rubric
- Per-dimension scores are averaged across successful judges
- Per-criterion scores (not per-dimension aggregates) are stored for reliability metrics
- If every judge call fails, scoring falls back explicitly to the deterministic rubric path

**Verifier mode** (`enable_verifier_mode=True`): uses the LLM-as-a-Verifier approach — K=3 independent verification calls per criterion per judge, averaged. Produces continuous scores and populates `verifier_distributions` per criterion. Improves Krippendorff's alpha / ICC validity by generating multiple items per rater. `verifier_k_repeats` controls K (default 3).

**Runner**: `ScenarioRunner` maintains full conversation history across turns so multi-turn scenarios have correct context at each call.

## Current Validation Coverage

- `tier0`: 3 scenarios
- `tier1`: 12 campaign scenarios spanning B2B SaaS, enterprise security, finance, healthcare, education, HR, retail, logistics, data tooling, and nonprofit/community briefs

## Code Style

- Type hints required
- Docstrings for public methods
- pytest for tests
- Dataclasses for scenario and brand models

## Environment

```bash
OPENROUTER_API_KEY=...    # Required for multi-judge
OPENAI_API_KEY=...        # Optional fallback
ANTHROPIC_API_KEY=...     # Optional fallback
GOOGLE_API_KEY=...        # Optional fallback
```
