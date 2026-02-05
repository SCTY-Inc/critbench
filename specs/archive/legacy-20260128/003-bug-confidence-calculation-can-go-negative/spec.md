# [FIX] Confidence calculation can go negative

## Task
In `benchmark/critbench/evaluation/scorers/coherence.py` around line 87, fix the confidence calculation to never go below 0.

## Problem
Confidence is computed as `1.0 - stdev(scores)`. If stdev > 1.0 (from data errors or edge cases), confidence goes negative.

## Fix
Change:
```python
confidence = 1.0 - stdev
```
To:
```python
confidence = max(0.0, 1.0 - stdev)
```

## Completion Signal
```bash
grep -n "max(0.0, 1.0 - stdev)" benchmark/critbench/evaluation/scorers/coherence.py && echo "Fixed" || exit 1
```

## Constraints
- Only change the confidence calculation line
- Same fix may be needed in judgment.py and voice.py if they have the same pattern
