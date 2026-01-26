"""Multi-agent debate module for resolving judge disagreements."""
from critbench.evaluation.debate.orchestrator import (
    DebateOrchestrator,
    DebateResult,
    run_debate,
)

__all__ = [
    "DebateOrchestrator",
    "DebateResult",
    "run_debate",
]
