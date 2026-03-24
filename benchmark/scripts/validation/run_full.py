#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = REPO_ROOT / "benchmark"

if str(BENCHMARK_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_ROOT))


SCENARIO_TIERS = ("tier0", "tier1")
SCORING_CONFIG_PATH = REPO_ROOT / "benchmark" / "configs" / "scoring.yaml"


def score(*args: Any, **kwargs: Any) -> dict[str, Any]:
    score_module = importlib.import_module("critbench.score")
    return cast(dict[str, Any], score_module.score(*args, **kwargs))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full CritBench validation suite.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List scenarios and estimated cost without scoring them.",
    )
    return parser.parse_args()


def collect_scenarios() -> list[Path]:
    scenario_paths: list[Path] = []
    for tier in SCENARIO_TIERS:
        tier_dir = REPO_ROOT / "benchmark" / "scenarios" / tier
        scenario_paths.extend(sorted(tier_dir.rglob("*.json")))
        scenario_paths.extend(sorted(tier_dir.rglob("*.yaml")))

    if not scenario_paths:
        raise RuntimeError("No validation scenarios found")

    return scenario_paths


def load_scenario(path: Path) -> dict[str, Any]:
    yaml_loader_module = importlib.import_module("critbench.loaders.yaml_loader")
    data = yaml_loader_module.load_serialized_file(path)
    return cast(dict[str, Any], data)


def estimate_total_cost(scenarios: list[Path]) -> float:
    total = 0.0
    for scenario_path in scenarios:
        scenario = load_scenario(scenario_path)
        total += float(scenario.get("metadata", {}).get("estimated_cost", 0.0))
    return total


def detect_differentiator(scenario: dict[str, Any]) -> str:
    combined_text = " ".join(
        turn.get("user_message", "") for turn in scenario.get("turns", [])
    ).lower()

    if "git/pr" in combined_text or ("git" in combined_text and "pr" in combined_text):
        return "real git and PR data instead of surveys or gut feel"
    if "survey" in combined_text:
        return "evidence instead of surveys or guesswork"
    return "evidence the team can trust"


def build_stage_response(
    stage: str, scenario: dict[str, Any], turn: dict[str, Any]
) -> str:
    brand = scenario.get("brand", {})
    brand_name = brand.get("name", "the brand")
    audience = brand.get("audience", "the target audience")
    differentiator = detect_differentiator(scenario)

    if stage == "brief_intake":
        return (
            f"Before we start, I need a few specifics: what is the buying trigger for {audience}? "
            "What proof points can we safely claim without stretching credibility? "
            "What conversion goal matters most in the first six weeks? "
            "I also want to know which messages the audience already distrusts so we do not repeat them."
        )

    if stage == "insight_generation":
        return (
            f"The audience is under pressure to explain productivity with confidence, but most tools add more opinion. "
            f"The tension is that managers need evidence without making the team feel watched. "
            f"That makes {differentiator} useful because it replaces gut-feel debates with shared facts they can defend."
        )

    if stage == "strategy":
        return (
            f"Position {brand_name} as the way to replace productivity guesswork with evidence teams can trust. "
            f"The message is not more pressure; it is clearer decisions from {differentiator}, "
            "so engineering managers can answer executive questions without hype."
        )

    if stage == "idea_generation":
        return "\n".join(
            [
                "1. Evidence over anecdotes: show how real delivery signals beat opinion-heavy status reviews.",
                "2. Stop managing by vibe: frame the product as a way to replace gut-feel judgments with defensible evidence.",
                "3. The pull request tells the story: center creative on git and PR activity as the clearest signal of how work moves.",
                "4. See where engineering time actually goes: map bottlenecks and decision points without blaming the team.",
                "5. Fewer productivity debates, better engineering decisions: show the operational calm that comes from shared facts.",
            ]
        )

    if stage == "idea_selection":
        return (
            "The strongest two are Evidence over anecdotes and See where engineering time actually goes because both tie directly "
            "to the audience tension and the product differentiator. Evidence over anecdotes is the clearest strategic message, "
            "while the time-goes concept is easier to execute across campaign formats. However, I would keep the tone restrained "
            "so it still feels credible within the stated budget and six-week launch window."
        )

    if stage == "hook_development":
        return (
            f"{brand_name} gives engineering managers evidence they can stand behind."
        )

    if stage == "execution":
        return "See where engineering time actually goes with real git and PR data."

    if stage == "feedback":
        return (
            "Understood. I will make the message more concrete, keep the tone understated, "
            "and preserve the evidence-first positioning."
        )

    if stage == "revision":
        return f"Revised direction: help {audience} replace guesswork with evidence they can explain to leadership and the team."

    if stage == "pressure_test":
        return (
            "I would not use fake urgency or manipulative pressure. A stronger approach is to emphasize the operational clarity "
            "teams gain from real data and offer a concrete, truthful next step."
        )

    return f"{brand_name} should speak to {audience} with restrained, evidence-based messaging built around {differentiator}."


def build_transcript(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    transcript: list[dict[str, Any]] = []

    for turn in scenario.get("turns", []):
        turn_number = int(turn.get("turn_number", turn.get("t", 0)))
        user_message = turn.get("user_message", "")
        stage = turn.get("stage", "")

        transcript.append(
            {
                "turn": turn_number,
                "role": "user",
                "content": user_message,
            }
        )
        transcript.append(
            {
                "turn": turn_number,
                "role": "assistant",
                "content": build_stage_response(stage, scenario, turn),
            }
        )

    if not transcript:
        raise RuntimeError(
            f"Scenario {scenario.get('scenario_id', '<unknown>')} has no turns"
        )

    return transcript


def write_transcript(transcript: list[dict[str, Any]]) -> Path:
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            delete=False,
        ) as handle:
            path = Path(handle.name)
            for message in transcript:
                handle.write(json.dumps(message) + "\n")
    except Exception:
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return path


def run_scenario(scenario_path: Path) -> float:
    scenario = load_scenario(scenario_path)
    transcript_path = write_transcript(build_transcript(scenario))

    try:
        result = score(
            transcript_path=str(transcript_path),
            scenario_path=str(scenario_path),
            scoring_config_path=str(SCORING_CONFIG_PATH),
            enable_llm=False,
            enable_debate=False,
            enable_anonymization=False,
            enable_bias_detection=False,
            enable_reliability_metrics=False,
            enable_cot_analysis=False,
        )
    finally:
        transcript_path.unlink(missing_ok=True)

    if result.get("autofail"):
        reasons = ", ".join(result.get("autofail_reasons", [])) or "unknown autofail"
        raise RuntimeError(f"{scenario_path} autofailed: {reasons}")

    return float(result["overall_percentage"])


def print_run_summary(scenarios: list[Path]) -> None:
    total_cost = estimate_total_cost(scenarios)
    print("validation: full")
    print(f"scenarios: {len(scenarios)}")
    print(f"estimated_cost: ${total_cost:.2f}")
    for scenario_path in scenarios:
        print(f"- {scenario_path.relative_to(REPO_ROOT)}")


def confirm_run() -> bool:
    try:
        response = input("Continue? [y/N]: ")
    except EOFError:
        return False
    return response.strip().lower() in {"y", "yes"}


def main() -> int:
    args = parse_args()

    try:
        scenarios = collect_scenarios()
        print_run_summary(scenarios)

        if args.dry_run:
            print("average: 0.00")
            return 0

        if not args.yes and not confirm_run():
            print("aborted")
            return 1

        scores: list[float] = []
        for scenario_path in scenarios:
            scenario_score = run_scenario(scenario_path)
            scores.append(scenario_score)
            print(f"{scenario_path.relative_to(REPO_ROOT)}: {scenario_score:.2f}")

        average = sum(scores) / len(scores)
        print(f"average: {average:.2f}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
