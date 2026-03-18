#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Sequence

import yaml


SCRIPT_PATH = Path(__file__).resolve()
BENCHMARK_ROOT = SCRIPT_PATH.parents[2]
SCORING_CONFIG_PATH = BENCHMARK_ROOT / "configs" / "scoring.yaml"

if str(BENCHMARK_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_ROOT))

from critbench import score as score_transcript
from critbench.loaders.scenario_loader import ScenarioLoader
from critbench.models import Scenario, StageType, Turn


SUPPORTED_SUFFIXES = {".json", ".yaml", ".yml"}


@dataclass(frozen=True)
class ScenarioEntry:
    source_path: Path
    scenario: Scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CritBench validation scenarios and print an average score."
    )
    parser.add_argument(
        "-y",
        action="store_true",
        dest="yes",
        help="Skip confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the estimated cost and exit without scoring.",
    )
    return parser.parse_args()


def _suffix_priority(path: Path) -> int:
    if path.suffix == ".json":
        return 0
    if path.suffix in {".yaml", ".yml"}:
        return 1
    return 2


def collect_scenarios(tier_dirs: Sequence[str]) -> list[ScenarioEntry]:
    loader = ScenarioLoader(BENCHMARK_ROOT)
    candidates = []

    for tier_dir in tier_dirs:
        scenario_dir = BENCHMARK_ROOT / "scenarios" / tier_dir
        candidates.extend(
            path
            for path in scenario_dir.rglob("*")
            if path.is_file() and path.suffix in SUPPORTED_SUFFIXES
        )

    if not candidates:
        joined = ", ".join(tier_dirs)
        raise FileNotFoundError(f"No scenarios found under {joined}")

    chosen: dict[str, ScenarioEntry] = {}
    for path in sorted(candidates, key=lambda item: (_suffix_priority(item), str(item))):
        scenario = loader.load(path)
        if scenario.scenario_id not in chosen:
            chosen[scenario.scenario_id] = ScenarioEntry(source_path=path, scenario=scenario)

    return sorted(chosen.values(), key=lambda entry: entry.source_path.as_posix())


def estimate_total_cost(entries: Sequence[ScenarioEntry]) -> float:
    return sum(float(entry.scenario.metadata.get("estimated_cost", 0.0)) for entry in entries)


def confirm_run(entries: Sequence[ScenarioEntry], estimated_cost: float) -> bool:
    print(f"scenarios: {len(entries)}")
    print(f"estimated cost: ${estimated_cost:.2f}")
    response = input("continue? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def write_jsonl(messages: Iterable[dict[str, object]]) -> str:
    with NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
        for message in messages:
            handle.write(json.dumps(message))
            handle.write("\n")
        return handle.name


def write_scoreable_scenario(source_path: Path) -> str:
    if source_path.suffix == ".json":
        return str(source_path)

    with source_path.open() as handle:
        raw_scenario = yaml.safe_load(handle)

    with NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(raw_scenario, handle)
        return handle.name


def _combined_user_context(scenario: Scenario) -> str:
    return " ".join(turn.user_message.lower() for turn in scenario.turns)


def _data_phrase(context: str) -> str:
    if "git" in context or "pr" in context:
        return "git and PR data"
    if "security" in context or "endpoint" in context:
        return "technical proof and signal quality"
    if "donor" in context or "nonprofit" in context:
        return "evidence-backed stories about dignity and agency"
    if "health" in context or "parent" in context:
        return "clear, practical guidance"
    return "specific evidence"


def _pain_phrase(context: str) -> str:
    if "gut-feel" in context or "gut feel" in context:
        return "gut-feel decisions"
    if "guilt" in context:
        return "preachy guilt messaging"
    if "ciso" in context or "security" in context:
        return "tool sprawl and noisy dashboards"
    if "gen z" in context:
        return "performing for the algorithm"
    return "generic messaging"


def build_response(scenario: Scenario, turn: Turn) -> str:
    brand = scenario.brand
    context = _combined_user_context(scenario)
    data_phrase = _data_phrase(context)
    pain_phrase = _pain_phrase(context)
    audience = brand.audience

    stage_templates = {
        StageType.BRIEF_INTAKE: (
            f"Before tactics, I need three specifics: what proof matters most to {audience}, "
            f"which audience segment is the highest priority, and what outcome defines success for this launch?"
        ),
        StageType.INSIGHT_GENERATION: (
            f"The core tension is that {audience} want progress without more noise. They reject {pain_phrase}, "
            f"so the opportunity is to use {data_phrase} to make the message feel credible instead of performative."
        ),
        StageType.STRATEGY: (
            f"Position {brand.name} as the credible way for {audience} to move from {pain_phrase} to {data_phrase}. "
            f"The promise should stay specific, grounded, and useful."
        ),
        StageType.IDEA_GENERATION: (
            f"1. Evidence over opinion: a campaign that shows how {data_phrase} replaces {pain_phrase}.\n"
            f"2. The calm operator: stories about making better calls with credible evidence.\n"
            f"3. What the signal says: a proof-led series translating messy workflows into clear decisions.\n"
            f"4. Fewer assumptions, better action: practical launch assets built around real constraints.\n"
            f"5. Credibility in public: a concept that lets {audience} see the thinking, not just the claim."
        ),
        StageType.IDEA_SELECTION: (
            "The strongest options are concepts 1 and 3 because they express the positioning most directly and give us "
            "clear proof points. Concept 1 is the simplest to understand, while concept 3 creates more room for depth. "
            "However, concept 5 is a useful follow-on once we have early evidence to share."
        ),
        StageType.HOOK_DEVELOPMENT: (
            f"Core hook: stop relying on {pain_phrase} and start pointing to {data_phrase}. "
            f"It keeps the tone credible and concrete for {audience}."
        ),
        StageType.EXECUTION: (
            f"{brand.name}: replace {pain_phrase} with {data_phrase}."
        ),
        StageType.FEEDBACK: (
            f"I will keep the same positioning around {data_phrase}, but make it shorter, warmer, and more specific to {audience}."
        ),
        StageType.REVISION: (
            f"Revised version: keep the proof-led idea, cut the extra explanation, and show one concrete example that matters to {audience}."
        ),
        StageType.PRESSURE_TEST: (
            "I would avoid fake urgency or pressure tactics. The stronger move is to show the real cost of the problem and offer a clear next step."
        ),
    }

    if turn.stage is None:
        return f"{brand.name} should sound credible, specific, and useful for {audience}."

    return stage_templates.get(
        turn.stage,
        f"{brand.name} should sound credible, specific, and useful for {audience}.",
    )


def build_transcript(scenario: Scenario) -> list[dict[str, object]]:
    transcript: list[dict[str, object]] = []

    for turn in scenario.turns:
        transcript.append(
            {
                "turn": turn.turn_number,
                "stage": turn.stage.value if turn.stage else None,
                "role": "user",
                "content": turn.user_message,
            }
        )
        transcript.append(
            {
                "turn": turn.turn_number,
                "stage": turn.stage.value if turn.stage else None,
                "role": "assistant",
                "content": build_response(scenario, turn),
            }
        )

    return transcript


def run_scenario(entry: ScenarioEntry) -> float:
    transcript_path = write_jsonl(build_transcript(entry.scenario))
    scoreable_scenario_path = write_scoreable_scenario(entry.source_path)

    try:
        result = score_transcript(
            transcript_path=transcript_path,
            scenario_path=scoreable_scenario_path,
            scoring_config_path=str(SCORING_CONFIG_PATH),
            enable_llm=False,
            enable_bias_detection=False,
            enable_reliability_metrics=False,
        )
    finally:
        Path(transcript_path).unlink(missing_ok=True)
        if scoreable_scenario_path != str(entry.source_path):
            Path(scoreable_scenario_path).unlink(missing_ok=True)

    return float(result.get("overall_percentage", 0.0))


def run_validation(tier_dirs: Sequence[str], run_name: str) -> int:
    args = parse_args()
    entries = collect_scenarios(tier_dirs)
    estimated_cost = estimate_total_cost(entries)

    if args.dry_run:
        print(f"{run_name} dry run")
        print(f"scenarios: {len(entries)}")
        print(f"estimated cost: ${estimated_cost:.2f}")
        return 0

    if not args.yes and not confirm_run(entries, estimated_cost):
        print("cancelled")
        return 0

    scores: list[float] = []
    for entry in entries:
        try:
            scenario_score = run_scenario(entry)
        except Exception as exc:
            print(f"hard failure: {entry.source_path}: {exc}", file=sys.stderr)
            return 1

        scores.append(scenario_score)
        print(f"{entry.source_path.relative_to(BENCHMARK_ROOT)}: {scenario_score:.2f}")

    average = sum(scores) / len(scores)
    print(f"average: {average:.2f}")
    return 0


def main() -> int:
    return run_validation(("tier0",), "minimal validation")


if __name__ == "__main__":
    raise SystemExit(main())
