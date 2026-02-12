Here's my review and the updated AGENTS.md content:

## Review Summary

**No commits today** — the branch has staged but uncommitted changes from a previous session.

**Failed Spec 002** ("Activate Debate System"): The spec itself is a blank template — every requirement, scenario, and task is placeholder text (`[Name]`, `[behavior]`, `[Task]`). Night Nurse marked all 3 tasks complete despite them being undescribed. The verification step correctly flagged this as FAILED.

The **actual code changes** are real and appear correct: `coherence.py`, `judgment.py`, and `voice.py` were all updated to compute and store `per_judge_scores` (weighted composite per judge model) in their breakdown output, with a corresponding test file validating the behavior for both sync and async paths.

**AI conversations**: All about Mission Control / orb.scty.org — no critbench-relevant learnings.

## Updated AGENTS.md

```markdown
# Agent Instructions

Read and follow: .specify/memory/constitution.md

## Workflow
1. Check specs/ for pending work
2. Pick highest priority spec without .done file
3. Implement according to acceptance criteria
4. Verify with completion signal
5. Commit and create .done file

## Gotchas

### Spec quality gate
Night Nurse can generate blank-template specs (all placeholder brackets like `[Name]`, `[behavior]`, `[Task]`). Before starting implementation, verify the spec has concrete acceptance criteria. If the spec is a template, fill it in first or flag it — don't mark placeholder tasks as complete.

### Constitution not initialized
`.specify/memory/constitution.md` is still a blank template. The actual project context lives in `CLAUDE.md` at the repo root — use that as the source of truth for tech stack, test commands, and architecture.

## Project Context

- **Stack**: Python 3.12, pytest, Pydantic, async/sync multi-judge ensemble scoring via OpenRouter
- **Test command**: `pytest benchmark/tests/ -v`
- **Type check**: `mypy benchmark/critbench/`
- **Lint**: `ruff check benchmark && black benchmark`

## Scoring Architecture

Each scorer (`coherence`, `judgment`, `voice`, `originality`, `ethics`, `adaptation`) follows the same pattern:
1. Extract relevant data from transcript + scenario
2. Run multi-judge ensemble (Claude, GPT-4, Gemini by default)
3. Parse structured scores from each judge's response
4. Aggregate via `statistics.mean` across judges
5. Apply weighted composite for overall score
6. Store `per_judge_scores` in `breakdown` (weighted composite per judge, keyed by model name)
7. Fallback to deterministic heuristics when LLM is unavailable

### Per-judge score weights by dimension
- **Coherence**: brief_understanding=0.20, insight_to_strategy=0.35, strategy_to_creative=0.35, internal_consistency=0.10
- **Judgment**: selection_reasoning=0.40, strategy_alignment=0.30, feasibility_awareness=0.20, selection_quality=0.10
- **Voice**: tone_consistency=0.35, vocabulary_match=0.25, format_adaptation=0.20, cross_output_consistency=0.20
```

The key addition is the **spec quality gate** gotcha — Night Nurse's blank-template specs are the root cause of the failed spec, and future agents should catch this before executing.
