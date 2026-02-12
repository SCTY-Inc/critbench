# Spec: Async Parallel Judge Scoring - Convert to async httpx and parallelize 18 sequential API calls for 3-5x speedup

## Requirements

### Requirement: Parallelize judge API calls
The system SHALL execute LLM judge API calls concurrently (async) using httpx.AsyncClient, replacing the current sequential calls across all per-dimension judges (6 dimensions x 3 models).

#### Scenario: [Happy path]
- GIVEN a transcript, scenario, and LLM scoring enabled with the default 3-judge ensemble
- WHEN scoring runs
- THEN the 18 judge calls are dispatched in parallel (async), and scoring outputs (scores, breakdowns, reasoning, autofail behavior) match the previous sequential behavior while reducing wall time by roughly 3-5x in typical runs.

### Requirement: Preserve non-LLM and error behavior
The system SHALL preserve deterministic fallback when LLM scoring is disabled or unavailable, and SHALL surface API errors in the same way as before.

#### Scenario: LLM disabled
- GIVEN LLM scoring disabled
- WHEN scoring runs
- THEN deterministic scoring paths are used and no async API calls are made.

## Completion Signal
```bash
rg -n "AsyncModelAPIClient|asyncio\\.gather" benchmark/critbench/score.py benchmark/critbench/evaluation/scorers
```
