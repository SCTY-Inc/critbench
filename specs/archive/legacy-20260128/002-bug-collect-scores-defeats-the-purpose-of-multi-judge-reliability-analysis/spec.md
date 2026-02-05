# [BUG] Bug: `_collect_scores` defeats the purpose of multi-judge reliability analysis

## Source
- Type: error
- Detected: 2026-01-27T13:57:03Z
- Priority: P2
- Report: reports/2026-01-27.md

## Problem
From AI review (ai-review-2026-01-27). Effort: unknown

## Review Details
**`score.py:282-299`** — The `_collect_scores` helper is supposed to collect per-judge scores for computing inter-rater reliability (Krippendorff's alpha, ICC). Instead, it copies the *same* final aggregated score to every model entry:

```python
final_score = dim_result.get("score", 0.5)
for model in models:
    all_scores[dimension][model].append(final_score)
```

This means the reliability metrics will always show perfect agreement because every judge gets assigned identical values. The comment on line 295-296 acknowledges the limitation. This is not a minor TODO — it renders the entire reliability/bias detection pipeline meaningless. Either the individual scorer modules need to return per-judge breakdowns, or this code shouldn't report reliability metrics at all (it currently reports fake reliability).

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
