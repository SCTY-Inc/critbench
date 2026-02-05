# [FEATURE] No tests for `client.py`

## Source
- Type: feature
- Requested: 2026-01-27T13:57:04Z
- Priority: P2

## Goal
From AI review (ai-review-2026-01-27). Effort: unknown

## Review Details
`ModelAPIClient` is untested. The `call_model` method does HTTP calls, response parsing, and model-name mapping — all of which can be tested with mocked responses.

### Debate test doesn't verify score convergence
**`test_debate.py:125-148`** — `test_run_debate_with_mock_responses` verifies the debate triggered and rounds ran, but doesn't assert that final scores moved toward the mock-returned value of 0.7. The test can't catch a bug where debate rounds run but scores aren't updated.

### Test coverage gap: ethics false positives
No test verifies that benign text containing dark-pattern substrings (e.g., "we'll be available 24 hours a day") correctly avoids autofail. This is the most dangerous gap given ethics triggers autofail → overall score = 0.

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
