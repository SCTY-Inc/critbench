"""Multi-agent debate module for resolving judge disagreements."""
from .orchestrator import (
    DebateOrchestrator,
    DebateResult,
    run_debate,
)

__all__ = [
    "DebateOrchestrator",
    "DebateResult",
    "run_debate",
]
