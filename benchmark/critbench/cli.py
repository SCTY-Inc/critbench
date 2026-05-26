"""CritBench CLI for running, scoring, and summarizing benchmark runs."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .loaders import ScenarioLoader
from .runner import ScenarioRunner
from .score import score as score_fn

app = typer.Typer(help="CritBench creative benchmark")
console = Console()


def _default_output_dir(scenario_id: str, model: str) -> Path:
    model_slug = model.replace("/", "-")
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    return Path("results") / scenario_id / model_slug / timestamp


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _collect_scores(results_dir: Path) -> dict[str, dict[str, list[float]]]:
    grouped: dict[str, dict[str, list[float]]] = {}

    for score_file in sorted(results_dir.glob("*/*/*/score.json")):
        with score_file.open() as handle:
            result = json.load(handle)

        model_slug = score_file.parts[-3]
        model_name = model_slug.replace("-", "/")
        model_scores = grouped.setdefault(model_name, {"overall": []})
        model_scores["overall"].append(float(result.get("overall_percentage", 0.0)))

        for dimension, payload in result.get("dimension_scores", {}).items():
            if isinstance(payload, dict):
                dimension_scores = model_scores.setdefault(dimension, [])
                dimension_scores.append(float(payload.get("score", 0.0)) * 100)

    return grouped


@app.command()
def run(
    model: str = typer.Option(..., "--model", help="Model identifier to run."),
    scenario: str = typer.Option(..., "--scenario", help="Scenario JSON or YAML file."),
    out: str | None = typer.Option(None, "--out", help="Output directory for run artifacts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the scenario without calling an API."),
    no_score: bool = typer.Option(False, "--no-score", help="Skip post-run scoring."),
    anonymous: bool = typer.Option(False, "--anonymous", help="Anonymize transcript before scoring."),
) -> None:
    """Run a model through a scenario and optionally score the transcript."""
    loader = ScenarioLoader()
    scenario_obj = loader.load(scenario)

    console.print(f"[green]Loaded:[/green] {scenario_obj.title} ({scenario_obj.total_turns} turns)")

    if dry_run:
        for turn in scenario_obj.turns:
            stage = turn.stage.value if turn.stage else "unknown"
            console.print(f"[bold]Turn {turn.turn_number}[/bold] [{stage}] {turn.user_message}")
        return

    output_dir = Path(out) if out else _default_output_dir(scenario_obj.scenario_id, model)
    transcript_path = output_dir / "transcript.jsonl"

    runner = ScenarioRunner(model=model, scenario=scenario_obj)
    runner.run_to_file(transcript_path)
    console.print(f"[green]Transcript:[/green] {transcript_path}")

    if no_score:
        return

    result = score_fn(
        transcript_path=str(transcript_path),
        scenario_path=scenario,
        enable_llm=True,
        enable_anonymization=anonymous,
    )
    result["metadata"] = {
        **result.get("metadata", {}),
        "model": model,
        "scenario_path": scenario,
        "transcript_path": str(transcript_path),
    }
    score_path = output_dir / "score.json"
    _write_json(score_path, result)
    console.print(f"[green]Score:[/green] {result['overall_percentage']:.1f}%")
    console.print(f"[green]Saved:[/green] {score_path}")


@app.command()
def score(
    transcript: str = typer.Option(..., "--transcript", help="Transcript JSONL file."),
    scenario: str = typer.Option(..., "--scenario", help="Scenario JSON or YAML file."),
    out: str | None = typer.Option(None, "--out", help="Optional path for the score JSON."),
    anonymous: bool = typer.Option(False, "--anonymous", help="Anonymize transcript before scoring."),
) -> None:
    """Score an existing transcript."""
    result = score_fn(
        transcript_path=transcript,
        scenario_path=scenario,
        enable_llm=True,
        enable_anonymization=anonymous,
    )

    console.print(f"[green]Overall:[/green] {result['overall_percentage']:.1f}%")
    if out:
        score_path = Path(out)
        _write_json(score_path, result)
        console.print(f"[green]Saved:[/green] {score_path}")


@app.command()
def leaderboard(
    results: str = typer.Option("results", "--results", help="Results root directory."),
    out: str | None = typer.Option(None, "--out", help="Optional file to write markdown output."),
) -> None:
    """Build a simple leaderboard from saved score files."""
    results_dir = Path(results)
    if not results_dir.exists():
        console.print(f"[red]Results directory not found: {results_dir}[/red]")
        raise typer.Exit(1)

    grouped = _collect_scores(results_dir)
    if not grouped:
        console.print("[yellow]No score files found.[/yellow]")
        return

    ordered = sorted(
        grouped.items(),
        key=lambda item: sum(item[1]["overall"]) / len(item[1]["overall"]),
        reverse=True,
    )
    table = Table(title="CritBench Leaderboard")
    table.add_column("Model")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Overall", justify="right")

    lines = ["# CritBench Leaderboard", "", "| Model | Runs | Avg Overall |", "| --- | ---: | ---: |"]
    for model_name, scores in ordered:
        average = sum(scores["overall"]) / len(scores["overall"])
        table.add_row(model_name, str(len(scores["overall"])), f"{average:.1f}%")
        lines.append(f"| {model_name} | {len(scores['overall'])} | {average:.1f}% |")

    console.print(table)

    if out:
        output_path = Path(out)
        output_path.write_text("\n".join(lines) + "\n")
        console.print(f"[green]Saved:[/green] {output_path}")


if __name__ == "__main__":
    app()
