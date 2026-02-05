# [BUG] Bug: Redundant no-op in `_parse_coherence_evaluation`

## Source
- Type: error
- Detected: 2026-01-27T13:57:03Z
- Priority: P2
- Report: reports/2026-01-27.md

## Problem
From AI review (ai-review-2026-01-27). Effort: unknown

## Review Details
**`coherence.py:248-249`** — The line:
```python
label = key.upper().replace("_", "_")
```
`.replace("_", "_")` does nothing. The same no-op is repeated on line 249. This looks like a find/replace artifact. The parsing logic works only because both sides of the comparison do the same no-op, but it obscures intent.

### API client not closed on exception paths
**`score.py:118-122`** — If `ModelAPIClient()` init succeeds but any scorer raises an exception, `api_client.close()` at line 248 is never reached. The client supports context manager protocol (`__enter__`/`__exit__`) but `score()` doesn't use it. An uncaught exception during scoring leaks an open `httpx.Client`.

### `score_with_rotation` creates ephemeral `ScenarioRotator` — usage tracking is lost
**`score.py:385-413`** — A fresh `ScenarioRotator` is constructed every call. Line 413 records usage (`rotator.record_usage(...)`) on this ephemeral object that's immediately garbage collected. The rotation tracking is stateless and never persists, so the contamination-prevention mechanism does nothing across runs.

### Global mutable state in `llm_mode.py`
**`llm_mode.py:7`** — `_LLM_ENABLED` is a module-level global, mutated via `set_llm_enabled()`. This is process-wide shared state with no thread safety. In any concurrent execution (parallel benchmark runs, test parallelism), one call to `set_llm_enabled(False)` silently disables LLM for all callers.

### Ethics scorer uses naive keyword matching
**`ethics.py:70-77`** — Substring matching on lowercased text means "24 hours" matches "available 24 hours a day" and "right now" matches "the right now-moment". This creates false positives on legitimate creative copy. The scanner also can't detect semantic dark patterns that don't use exact keyword phrases.

## Context


## Acceptance Criteria
- [ ] Error is handled gracefully (no crash)
- [ ] Appropriate error message is logged
- [ ] Existing functionality is not affected
- [ ] Recovery/fallback behavior works

## Completion Signal
```bash
npm run build
npm run test
# Verify: trigger the error condition and confirm graceful handling
```

## Constraints
- Keep changes minimal and focused
- Don't break existing functionality
- Add error handling, not workarounds
