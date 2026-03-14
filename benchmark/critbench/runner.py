"""Scenario runner that drives a model through a creative scenario turn-by-turn."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from critbench.api import AsyncModelAPIClient
from critbench.models import Scenario

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Drives a model through a scenario and collects the transcript."""

    def __init__(
        self,
        model: str,
        scenario: Scenario,
        api_client: AsyncModelAPIClient | None = None,
        timeout_per_turn: float = 30.0,
        max_retries: int = 2,
    ):
        """Initialize runner.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3.5-sonnet")
            scenario: Scenario to run through
            api_client: Optional AsyncModelAPIClient. If None, will create one.
            timeout_per_turn: Timeout in seconds per turn
            max_retries: Maximum retries on failure per turn
        """
        self.model = model
        self.scenario = scenario
        self.api_client = api_client
        self.timeout_per_turn = timeout_per_turn
        self.max_retries = max_retries
        self._client_owned = api_client is None

    async def run_async(self) -> list[dict[str, Any]]:
        """Run scenario asynchronously and collect transcript.

        Returns:
            List of transcript entries, one per turn (user + assistant)
        """
        # Create client if we own it
        if self._client_owned:
            self.api_client = AsyncModelAPIClient()

        transcript: list[dict[str, Any]] = []

        try:
            # Build system prompt from brand
            system_prompt = self._build_system_prompt()

            for turn in self.scenario.turns:
                # Add user message to transcript
                transcript.append({
                    "turn": turn.turn_number,
                    "stage": turn.stage.value if turn.stage else None,
                    "role": "user",
                    "content": turn.user_message,
                })

                # Call model with retries
                assistant_response = None
                last_error = None

                for attempt in range(self.max_retries + 1):
                    try:
                        assistant_response = await asyncio.wait_for(
                            self._call_model(system_prompt, turn.user_message),
                            timeout=self.timeout_per_turn,
                        )
                        break
                    except TimeoutError:
                        last_error = "timeout"
                        logger.warning(
                            f"Turn {turn.turn_number} timeout after {self.timeout_per_turn}s "
                            f"(attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(
                            f"Turn {turn.turn_number} error: {e} "
                            f"(attempt {attempt + 1}/{self.max_retries + 1})"
                        )

                # Add assistant response (or error marker)
                if assistant_response:
                    transcript.append({
                        "turn": turn.turn_number,
                        "stage": turn.stage.value if turn.stage else None,
                        "role": "assistant",
                        "content": assistant_response,
                    })
                else:
                    transcript.append({
                        "turn": turn.turn_number,
                        "stage": turn.stage.value if turn.stage else None,
                        "role": "assistant",
                        "content": "",
                        "error": last_error or "unknown",
                    })

            return transcript

        finally:
            # Clean up if we created the client
            if self._client_owned and self.api_client:
                # close() is not typed in api client
                _ = await self.api_client.close()  # type: ignore

    def run(self) -> list[dict[str, Any]]:
        """Run scenario synchronously and collect transcript.

        Returns:
            List of transcript entries
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.run_async())

    def run_to_file(self, output_path: str | Path) -> Path:
        """Run scenario and write transcript to JSONL file.

        Args:
            output_path: Path to write JSONL transcript

        Returns:
            Path to written file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        transcript = self.run()

        with open(output_path, "w") as f:
            for entry in transcript:
                f.write(json.dumps(entry) + "\n")

        logger.info(f"Wrote {len(transcript)} transcript entries to {output_path}")
        return output_path

    def _build_system_prompt(self) -> str:
        """Build system prompt from scenario brand.

        Returns:
            System prompt string
        """
        brand = self.scenario.brand
        constraints_str = ", ".join(brand.constraints) if brand.constraints else "none"
        banned_str = ", ".join(brand.banned_phrases) if brand.banned_phrases else "none"

        return (
            f"You are working on a creative brief. "
            f"Brand: {brand.name}. "
            f"Voice: {brand.voice}. "
            f"Audience: {brand.audience}. "
            f"Constraints: {constraints_str}. "
            f"Banned phrases: {banned_str}."
        )

    async def _call_model(self, system_prompt: str, user_message: str) -> str:
        """Call model with system and user message.

        Args:
            system_prompt: System prompt
            user_message: User message

        Returns:
            Model response text
        """
        if not self.api_client:
            raise RuntimeError("API client not initialized")

        result = await self.api_client.call_model(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        response: str = result.get("response", "")
        return response
