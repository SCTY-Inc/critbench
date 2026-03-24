from __future__ import annotations

import json
from pathlib import Path

from critbench.models import Brand, Scenario, StageType, TierLevel, Turn
from critbench.runner import ScenarioRunner


class StubClient:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def call_model(self, **kwargs: object) -> dict[str, str]:
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("no more responses")
        return {"response": self.responses.pop(0)}

    def close(self) -> None:
        return None


def make_scenario() -> Scenario:
    return Scenario(
        scenario_id="runner_test",
        tier=TierLevel.TIER_0,
        title="Runner Test",
        brand=Brand(
            name="TestBrand",
            voice="clear and direct",
            audience="operators",
            constraints=["no hype"],
            banned_phrases=["world-class"],
        ),
        turns=[
            Turn(turn_number=1, stage=StageType.BRIEF_INTAKE, user_message="What do you need to know?"),
            Turn(turn_number=2, stage=StageType.EXECUTION, user_message="Draft the message."),
        ],
    )


def test_runner_builds_brand_aware_system_prompt() -> None:
    runner = ScenarioRunner(model="test/model", scenario=make_scenario(), api_client=StubClient(["ok", "ok"]))

    prompt = runner._build_system_prompt()

    assert "TestBrand" in prompt
    assert "operators" in prompt
    assert "no hype" in prompt
    assert "world-class" in prompt


def test_runner_writes_transcript_jsonl(tmp_path: Path) -> None:
    runner = ScenarioRunner(
        model="test/model",
        scenario=make_scenario(),
        api_client=StubClient(["first response", "second response"]),
    )

    transcript_path = runner.run_to_file(tmp_path / "results" / "transcript.jsonl")

    lines = transcript_path.read_text().strip().splitlines()
    assert len(lines) == 4
    messages = [json.loads(line) for line in lines]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "first response"


def test_runner_records_error_after_retry_exhaustion() -> None:
    class FailingClient:
        def __init__(self) -> None:
            self.calls = 0

        def call_model(self, **kwargs: object) -> dict[str, str]:
            self.calls += 1
            raise RuntimeError("boom")

        def close(self) -> None:
            return None

    client = FailingClient()
    runner = ScenarioRunner(
        model="test/model",
        scenario=make_scenario(),
        api_client=client,
        max_retries=1,
    )

    transcript = runner.run()

    assert client.calls == 4
    assistant_messages = [entry for entry in transcript if entry["role"] == "assistant"]
    assert assistant_messages[0]["error"] == "boom"
    assert assistant_messages[1]["error"] == "boom"
