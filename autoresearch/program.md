# Campaign: CritBench Scenario Pass Rate

Optimize CritBench scenario coverage and scoring reliability. Target: all tier1 scenarios passing validation with ≥1 model achieving ≥70% average score.

## Metric

Average score across tier1 scenarios from the multi-judge scorer — higher is better, max 100.

## Eval Command

```bash
cd /home/deploy/scty-repos/critbench
source .venv/bin/activate 2>/dev/null || (uv venv && source .venv/bin/activate && uv pip install -e ".[all]")
source ~/.env
python benchmark/scripts/validation/run_minimal.py -y 2>&1 | tail -20
```

Note: first run establishes baseline. The validation script runs tier0 smoke test. For full tier1, use the CLI scorer against scenario files directly.

## Metric Parsing (for run_experiment.sh)

- **regex**: `average[:\s]+([0-9.]+)`
- **direction**: `higher`
- **fail_regex**: `Traceback|Error|FAILED|ImportError`
- **baseline**: TBD (run validation first)

## Mutable Files

- `benchmark/scenarios/tier1/**/*.json` — scenario definitions (turns, evaluation criteria)
- `critbench/scoring/rubric*.yaml` — scoring rubric dimensions
- `critbench/judges/` — judge model configs and prompts

## Locked Files (DO NOT MODIFY)

- `benchmark/critbench/cli.py` — scoring CLI entrypoint
- `benchmark/scripts/validation/` — validation harness
- Core evaluation logic

## Thresholds

- COMMIT if: average score improves by 1+ point
- REVERT if: score drops or stays same
- REVERT if: any previously-passing scenario starts hard-failing

## Budget

- Max experiments per target: 4
- Max experiments total: 16
- Max wall time per experiment: 10 min
- Max campaign time: 4 hours

## Targets (priority order)

### Target 1: Scenario turn quality — brief intake stage

The brief intake stage (turn 1-2) sets up the whole transcript. If the scenario's user prompts are too vague, all judges score low on `comprehension` and `clarifying_questions`. Tighten the brief intake user turns to be realistically ambiguous (not underspecified).
**File:** `benchmark/scenarios/tier1/campaign/*.json`

### Target 2: Evaluation criteria specificity

`evaluate: [asks_clarifying_questions]` is binary but the rubric may not define what counts. Add explicit criteria strings to each eval tag in scenario JSON so judges have less ambiguity.
**File:** `benchmark/scenarios/tier1/**/*.json`

### Target 3: Judge prompt calibration

If judges are systematically low on one dimension (e.g., `insight_depth`), the judge prompt may be too strict. Adjust judge instructions to calibrate against human-level creative work, not perfection.
**File:** `critbench/judges/` prompt files
