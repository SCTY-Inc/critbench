"""LLM mode utilities for toggling between LLM and deterministic scoring."""
from __future__ import annotations

import os

# Global flag for LLM mode
_LLM_ENABLED: bool = True


def llm_enabled(allow_llm: bool = True) -> bool:
    """Check if LLM-assisted scoring is enabled.

    Args:
        allow_llm: Local override (False disables even if global is True)

    Returns:
        True if LLM scoring should be used
    """
    global _LLM_ENABLED

    # Environment variable override
    env_setting = os.getenv("CRITBENCH_ENABLE_LLM", "").lower()
    if env_setting == "false" or env_setting == "0":
        return False

    return _LLM_ENABLED and allow_llm


def set_llm_enabled(enabled: bool) -> None:
    """Set global LLM mode.

    Args:
        enabled: Whether to enable LLM-assisted scoring
    """
    global _LLM_ENABLED
    _LLM_ENABLED = enabled
