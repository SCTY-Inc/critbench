# [FEATURE] No tests for `score.py`, the core public API

## Source
- Type: feature
- Requested: 2026-01-27T13:57:04Z
- Priority: P2

## Goal
From AI review (ai-review-2026-01-27). Effort: unknown

## Review Details
There is no `test_score.py`. The `score()`, `score_with_rewards()`, and `score_with_rotation()` functions — the primary public API — have zero test coverage. These are complex orchestration functions with multiple code paths (LLM on/off, debate, anonymization, autofail).

## Context


## Acceptance Criteria
- [ ] Feature works as described
- [ ] Tests pass
- [ ] No regressions in existing functionality
- [ ] Documentation updated if needed

## Completion Signal
```bash
npm run build
npm run test
```

## Constraints
- Follow existing code patterns
- Keep changes focused on the feature
