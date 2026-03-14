"""CLI for CritBench benchmark - run, score, and leaderboard commands."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from critbench import score as score_fn
from critbench.loaders.scenario_loader import ScenarioLoader
from critbench.models.result import BenchmarkResult
from critbench.results.writer import ResultsWriter
from critbench.runner import ScenarioRunner

app = typer.Typer(help="CritBench creative process benchmark")
console = Console()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@app.command()
def run(
    model: str = typer.Option(
        ...,
        "--model",
        help="Model identifier (e.g., anthropic/claude-3.5-sonnet)",
    ),
    scenario: str = typer.Option(
        ...,
        "--scenario",
        help="Path to scenario YAML/JSON file",
    ),
    out: str = typer.Option(
        None,
        "--out",
        help="Output directory (default: results/{scenario_id}/{model_slug}/{timestamp}/)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show turns without calling API",
    ),
    no_score: bool = typer.Option(
        False,
        "--no-score",
        help="Collect transcript only, skip scoring",
    ),
    debate: bool = typer.Option(
        False,
        "--debate",
        help="Enable debate for disagreements",
    ),
    anonymous: bool = typer.Option(
        False,
        "--anonymous",
        help="Anonymize transcript before scoring",
    ),
) -> None:
    """Run a model through a scenario and score it.

    Example:
        critbench run \\
            --model anthropic/claude-3.5-sonnet \\
            --scenario benchmark/scenarios/tier1/campaign/saas_launch.yaml
    """
    # Load scenario
    loader = ScenarioLoader()
    try:
        scenario_obj = loader.load(scenario)
    except Exception as e:
        console.print(f"[red]Error loading scenario: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]Loaded scenario:[/green] {scenario_obj.title}")
    console.print(f"  Scenario ID: {scenario_obj.scenario_id}")
    console.print(f"  Turns: {scenario_obj.total_turns}")

    if dry_run:
        console.print("\n[yellow]Dry run mode - showing turns only[/yellow]")
        for turn in scenario_obj.turns:
            console.print(f"\n[bold]Turn {turn.turn_number}[/bold] ({turn.stage.value if turn.stage else 'unknown'})")
            console.print(f"  {turn.user_message[:100]}...")
        return

    # Run scenario
    console.print(f"\n[bold]Running scenario with {model}...[/bold]")
    try:
        runner = ScenarioRunner(model, scenario_obj)
        transcript_path = Path(out) if out else None

        if not transcript_path:
            # Create default output directory
            model_slug = model.replace("/", "-")
            timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
            transcript_path = Path("results") / scenario_obj.scenario_id / model_slug / timestamp
            transcript_path.mkdir(parents=True, exist_ok=True)

        transcript_file = transcript_path / "transcript.jsonl" if isinstance(transcript_path, Path) else Path(transcript_path) / "transcript.jsonl"
        transcript_file = runner.run_to_file(transcript_file)
        console.print(f"[green]✓ Transcript saved to {transcript_file}[/green]")
    except Exception as e:
        console.print(f"[red]Error running scenario: {e}[/red]")
        raise typer.Exit(1) from e

    if no_score:
        console.print("[yellow]Skipping scoring (--no-score flag)[/yellow]")
        return

    # Score transcript
    console.print("\n[bold]Scoring transcript...[/bold]")
    try:
        result_dict = score_fn(
            str(transcript_file),
            scenario,
            enable_llm=True,
            enable_debate=debate,
            enable_anonymization=anonymous,
        )

        # Save result
        result = BenchmarkResult.from_score_result(result_dict, scenario_obj.scenario_id)
        writer = ResultsWriter(str(transcript_file.parent))
        writer.write(result)

        # Print summary
        console.print(f"[green]✓ Score: {result.overall_percentage:.1f}%[/green]")
        console.print(f"  Overall: {result.overall_score:.3f}")
        for dim, score in result.dimension_scores.__dict__.items():
            console.print(f"  {dim}: {score.score:.3f}")

    except Exception as e:
        console.print(f"[red]Error scoring: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def score(
    transcript: str = typer.Option(
        ...,
        "--transcript",
        help="Path to transcript JSONL file",
    ),
    scenario: str = typer.Option(
        ...,
        "--scenario",
        help="Path to scenario YAML/JSON file",
    ),
    debate: bool = typer.Option(
        False,
        "--debate",
        help="Enable debate for disagreements",
    ),
) -> None:
    """Score an existing transcript against a scenario.

    Example:
        critbench score \\
            --transcript results/tier1_campaign_001/anthropic-claude-3.5-sonnet/2026-03-14T12-00/transcript.jsonl \\
            --scenario benchmark/scenarios/tier1/campaign/saas_launch.yaml
    """
    console.print("[bold]Scoring transcript...[/bold]")
    try:
        result_dict = score_fn(
            transcript,
            scenario,
            enable_llm=True,
            enable_debate=debate,
        )

        # Print result
        console.print(f"[green]✓ Overall: {result_dict.get('overall_percentage', 0):.1f}%[/green]")
        dimensions = result_dict.get("dimension_scores", {})
        for dim, data in dimensions.items():
            if isinstance(data, dict):
                console.print(f"  {dim}: {data.get('score', 0):.3f}")

    except Exception as e:
        console.print(f"[red]Error scoring: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def leaderboard(
    results: str = typer.Option(
        "results",
        "--results",
        help="Results directory",
    ),
    out: str | None = typer.Option(
        None,
        "--out",
        help="Output file (default: stdout)",
    ),
) -> None:
    """Show leaderboard from results directory.

    Example:
        critbench leaderboard --results results/ --out leaderboard.md
    """
    results_dir = Path(results)
    if not results_dir.exists():
        console.print(f"[red]Results directory not found: {results_dir}[/red]")
        raise typer.Exit(1)

    # Aggregate results by model
    results_by_model: dict[str, dict[str, list[float]]] = {}
    scenario_ids: set[str] = set()
    run_count: dict[str, int] = {}

    # Find all score.json files
    for score_file in results_dir.glob("*/*/*/score.json"):
        try:
            with open(score_file) as f:
                result = json.load(f)

            # Extract model from path (results/{scenario_id}/{model_slug}/{timestamp}/score.json)
            parts = score_file.parts
            if len(parts) >= 4:
                model_slug = parts[-3]
                scenario_id = parts[-4]

                # Normalize model slug back to readable form
                model_name = model_slug.replace("-", "/")
                scenario_ids.add(scenario_id)

                if model_name not in results_by_model:
                    results_by_model[model_name] = {
                        "overall": [],
                        "coherence": [],
                        "judgment": [],
                        "voice": [],
                        "originality": [],
                        "ethics": [],
                        "adaptation": [],
                    }
                    run_count[model_name] = 0

                run_count[model_name] += 1
                results_by_model[model_name]["overall"].append(result.get("overall_percentage", 0))

                # Extract dimension scores
                dims = result.get("dimension_scores", {})
                for dim in ["coherence", "judgment", "voice", "originality", "ethics", "adaptation"]:
                    if dim in dims and isinstance(dims[dim], dict):
                        results_by_model[model_name][dim].append(dims[dim].get("score", 0) * 100)

        except Exception as e:
            logger.warning(f"Could not load {score_file}: {e}")

    if not results_by_model:
        console.print("[yellow]No results found in results directory[/yellow]")
        return

    # Build leaderboard table
    table = Table(title="CritBench Leaderboard")
    table.add_column("Model", style="cyan")
    table.add_column("Overall", justify="right")
    table.add_column("Coherence", justify="right")
    table.add_column("Judgment", justify="right")
    table.add_column("Voice", justify="right")
    table.add_column("Originality", justify="right")
    table.add_column("Ethics", justify="right")
    table.add_column("Adaptation", justify="right")
    table.add_column("Runs", justify="right")

    # Sort by overall score (descending)
    sorted_models = sorted(
        results_by_model.items(),
        key=lambda x: (
            sum(x[1]["overall"]) / len(x[1]["overall"]) if x[1]["overall"] else 0
        ),
        reverse=True,
    )

    for model_name, scores in sorted_models:
        overall_avg = sum(scores["overall"]) / len(scores["overall"]) if scores["overall"] else 0
        coherence_avg = sum(scores["coherence"]) / len(scores["coherence"]) if scores["coherence"] else 0
        judgment_avg = sum(scores["judgment"]) / len(scores["judgment"]) if scores["judgment"] else 0
        voice_avg = sum(scores["voice"]) / len(scores["voice"]) if scores["voice"] else 0
        originality_avg = sum(scores["originality"]) / len(scores["originality"]) if scores["originality"] else 0
        ethics_avg = sum(scores["ethics"]) / len(scores["ethics"]) if scores["ethics"] else 0
        adaptation_avg = sum(scores["adaptation"]) / len(scores["adaptation"]) if scores["adaptation"] else 0

        table.add_row(
            model_name,
            f"{overall_avg:.1f}",
            f"{coherence_avg:.1f}",
            f"{judgment_avg:.1f}",
            f"{voice_avg:.1f}",
            f"{originality_avg:.1f}",
            f"{ethics_avg:.1f}",
            f"{adaptation_avg:.1f}",
            str(run_count[model_name]),
        )

    console.print(table)

    # Add footer
    console.print(f"\n*Scenarios: {', '.join(sorted(scenario_ids))} (n={len(scenario_ids)})*")
    console.print("*Judge validation: ρ = [pending human gold set]*")

    # Output to file if requested
    if out:
        # Export as markdown
        md_lines = [
            "# CritBench Leaderboard\n",
            "| Model | Overall | Coherence | Judgment | Voice | Originality | Ethics | Adaptation | Runs |",
            "|-------|---------|-----------|----------|-------|-------------|--------|------------|------|",
        ]

        for model_name, scores in sorted_models:
            overall_avg = sum(scores["overall"]) / len(scores["overall"]) if scores["overall"] else 0
            coherence_avg = sum(scores["coherence"]) / len(scores["coherence"]) if scores["coherence"] else 0
            judgment_avg = sum(scores["judgment"]) / len(scores["judgment"]) if scores["judgment"] else 0
            voice_avg = sum(scores["voice"]) / len(scores["voice"]) if scores["voice"] else 0
            originality_avg = sum(scores["originality"]) / len(scores["originality"]) if scores["originality"] else 0
            ethics_avg = sum(scores["ethics"]) / len(scores["ethics"]) if scores["ethics"] else 0
            adaptation_avg = sum(scores["adaptation"]) / len(scores["adaptation"]) if scores["adaptation"] else 0

            md_lines.append(
                f"| {model_name} | {overall_avg:.1f} | {coherence_avg:.1f} | {judgment_avg:.1f} | "
                f"{voice_avg:.1f} | {originality_avg:.1f} | {ethics_avg:.1f} | {adaptation_avg:.1f} | {run_count[model_name]} |"
            )

        md_lines.extend([
            "\n*Judge validation: ρ = [pending human gold set]*",
            f"*Scenarios: {', '.join(sorted(scenario_ids))} (n={len(scenario_ids)})*",
        ])

        with open(out, "w") as f:
            f.write("\n".join(md_lines))

        console.print(f"\n[green]✓ Leaderboard saved to {out}[/green]")


if __name__ == "__main__":
    app()
