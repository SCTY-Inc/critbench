# [FEATURE] No tests for any of the 6 scorers

## Source
- Type: feature
- Requested: 2026-01-27T13:57:04Z
- Priority: P2

## Goal
From AI review (ai-review-2026-01-27). Effort: unknown

## Review Details
There are no tests for `coherence.py`, `judgment.py`, `voice.py`, `originality.py`, `ethics.py`, or `adaptation.py`. The ethics scorer has testable deterministic logic (keyword matching) that should be covered. The coherence parser (`_parse_coherence_evaluation`) handles string parsing that is fragile and needs edge-case tests.

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
