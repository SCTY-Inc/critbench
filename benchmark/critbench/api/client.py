"""Multi-model API client for CritBench ensemble judging.

Supports multiple providers for robust multi-judge scoring:
- OpenRouter (primary, supports all models)
- Direct provider APIs (fallback)
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


class ModelAPIClient:
    """Unified API client for multiple LLM providers."""

    def __init__(
        self,
        openrouter_api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.timeout = timeout

        if not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY required for multi-judge scoring. "
                "Set via environment variable or pass to constructor."
            )

        try:
            import httpx
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "httpx is required for LLM judging. Install critbench with its runtime dependencies."
            ) from exc

        self._client: httpx.Client = httpx.Client(timeout=timeout)

    def call_model(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Call a model via OpenRouter.

        Args:
            model: Model identifier (e.g., "claude-sonnet-4-20250514")
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dict with "response" key containing the model output
        """
        # Map model names to OpenRouter identifiers
        model_map = {
            "claude-sonnet-4-20250514": "anthropic/claude-sonnet-4-20250514",
            "gpt-4.1": "openai/gpt-4.1",
            "gemini-2.0-flash": "google/gemini-2.0-flash-001",
        }

        openrouter_model = model_map.get(model, model)

        response = self._client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://critbench.dev",
                "X-Title": "CritBench",
            },
            json={
                "model": openrouter_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        response.raise_for_status()
        data = response.json()

        return {
            "response": data["choices"][0]["message"]["content"],
            "model": openrouter_model,
            "usage": data.get("usage", {}),
        }

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> ModelAPIClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
