"""Run a model through a CritBench scenario and persist the transcript."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from critbench.api import ModelAPIClient
from critbench.models import Scenario

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Drive a model through a scenario turn by turn."""

    def __init__(
        self,
        model: str,
        scenario: Scenario,
        api_client: ModelAPIClient | None = None,
        timeout_per_turn: float = 30.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.scenario = scenario
        self.api_client = api_client
        self.timeout_per_turn = timeout_per_turn
        self.max_retries = max_retries

    def run(self) -> list[dict[str, Any]]:
        transcript: list[dict[str, Any]] = []
        owned_client = False
        client = self.api_client

        if client is None:
            client = ModelAPIClient(timeout=self.timeout_per_turn)
            owned_client = True

        try:
            system_prompt = self._build_system_prompt()
            for turn in self.scenario.turns:
                transcript.append(
                    {
                        "turn": turn.turn_number,
                        "stage": turn.stage.value if turn.stage else None,
                        "role": "user",
                        "content": turn.user_message,
                    }
                )

                assistant_message, error = self._call_with_retries(
                    client=client,
                    system_prompt=system_prompt,
                    user_message=turn.user_message,
                    turn_number=turn.turn_number,
                )
                transcript.append(
                    {
                        "turn": turn.turn_number,
                        "stage": turn.stage.value if turn.stage else None,
                        "role": "assistant",
                        "content": assistant_message,
                        **({"error": error} if error else {}),
                    }
                )

            return transcript
        finally:
            if owned_client:
                client.close()

    def run_to_file(self, output_path: str | Path) -> Path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        transcript = self.run()
        with destination.open("w") as handle:
            for message in transcript:
                handle.write(json.dumps(message) + "\n")

        logger.info("Wrote %s transcript entries to %s", len(transcript), destination)
        return destination

    def _call_with_retries(
        self,
        client: ModelAPIClient,
        system_prompt: str,
        user_message: str,
        turn_number: int,
    ) -> tuple[str, str | None]:
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = client.call_model(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                )
                return str(result.get("response", "")), None
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Turn %s failed on attempt %s/%s: %s",
                    turn_number,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )

        return "", last_error

    def _build_system_prompt(self) -> str:
        brand = self.scenario.brand
        constraints = ", ".join(brand.constraints) if brand.constraints else "none"
        banned_phrases = ", ".join(brand.banned_phrases) if brand.banned_phrases else "none"
        return (
            f"You are working on a creative brief. Brand: {brand.name}. "
            f"Voice: {brand.voice}. Audience: {brand.audience}. "
            f"Constraints: {constraints}. Banned phrases: {banned_phrases}."
        )
