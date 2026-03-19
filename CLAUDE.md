# CLAUDE.md

AI assistant instructions for CritBench (creative benchmark project).

## Project Type

**Research benchmark** for evaluating LLM creative process quality.

## Critical Rules

- **No unnecessary docs**: Ask before creating .md files
- When done: Say "done"
- Keep repo minimal and focused

## CLI Commands

```bash
# === BENCHMARKING ===
# Quick validation (tier 0 offline smoke test)
python benchmark/scripts/validation/run_minimal.py -y

# Full validation (tier 0 + tier 1 offline smoke test)
python benchmark/scripts/validation/run_full.py -y

# Dry run (list scenarios and estimated cost)
python benchmark/scripts/validation/run_minimal.py --dry-run

# === SCORING (single scenario) ===
python -m benchmark.critbench.cli \
  --scenario benchmark/scenarios/tier1/campaign/saas_launch.json \
  --transcript path/to/transcript.jsonl \
  --brand benchmark/configs/brands/codeflow.yaml \
  --out report.html

# === TESTS ===
pytest benchmark/tests/ -v
pytest benchmark/tests/ -v --cov=benchmark.critbench

# === CODE QUALITY ===
mypy benchmark/critbench/
ruff check benchmark
black benchmark
```

## Architecture

```
benchmark/critbench/
├── __init__.py       # Public API: score, score_with_rewards
├── score.py          # Main scoring function
├── cli.py            # CLI tool
├── models/           # Brand, Turn, Campaign, Scenario dataclasses
├── evaluation/
│   ├── orchestrator.py
│   └── scorers/      # Per-dimension scorers
│       ├── coherence.py    # insight→strategy→creative
│       ├── judgment.py     # idea selection quality
│       ├── voice.py        # brand consistency
│       ├── originality.py  # non-obvious creative
│       ├── ethics.py       # no dark patterns
│       └── adaptation.py   # feedback integration
├── api/
│   └── client.py     # Multi-model ensemble client
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

```json
{
  "scenario_id": "tier1_campaign_001",
  "tier": "tier_1",
  "title": "B2B SaaS Launch",
  "brand": {
    "name": "CodeFlow",
    "voice": "technically credible, understated",
    "audience": "senior engineers",
    "constraints": ["no 'revolutionary'", "no fake metrics"]
  },
  "turns": [
    {
      "turn_number": 1,
      "stage": "brief_intake",
      "user_message": "We're launching CodeFlow...",
      "expected_behaviors": ["asks clarifying questions"],
      "autofail_triggers": ["jumps to tactics without understanding"]
    }
  ]
}
```

## Multi-Judge Scoring

Uses 3-model ensemble to reduce bias:
- Claude, GPT-4, Gemini score same rubric
- Majority vote for binary decisions
- Mean + confidence for numeric scores
- Disagreement flags for human review

## Code Style

- Type hints required
- Docstrings for public methods
- pytest for tests
- Pydantic for data models

## Environment

```bash
OPENROUTER_API_KEY=...    # Required for multi-judge
OPENAI_API_KEY=...        # Optional fallback
ANTHROPIC_API_KEY=...     # Optional fallback
GOOGLE_API_KEY=...        # Optional fallback
```
