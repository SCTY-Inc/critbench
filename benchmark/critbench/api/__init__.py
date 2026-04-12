"""Multi-model API client for ensemble judging."""
from __future__ import annotations

from .client import ModelAPIClient, resolve_scorer_model

__all__ = ["ModelAPIClient", "resolve_scorer_model"]
