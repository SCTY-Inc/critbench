"""CLI for CritBench benchmark - run, score, and leaderboard commands."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from critbench import score as score_fn
from critbench._agent_cli import DoctorCheck, doctor_runner, emit_json, emit_path
from critbench.loaders.scenario_loader import ScenarioLoader

# ScenarioRunner, BenchmarkResult, and ResultsWriter are still imported lazily
# inside `run` because:
#   - `critbench.runner` imports `AsyncModelAPIClient` from `critbench.api`,
#     but that class has never been added on this branch (it exists only on
#     fix/SCT-29, which is unmerged). Top-level import would crash --help.
#   - `critbench.results.writer` imports `BenchmarkResult, IndexEntry` from
#     `critbench.models.result`, a module that does not exist on any branch.
# These are genuine upstream gaps, not a cli.py defect — re-creating
# `models/result.py` is out of scope for this task.

app = typer.Typer(help="CritBench creative process benchmark")
console = Console(
    no_color=bool(os.environ.get("NO_COLOR")) or not sys.stdout.isatty(),
    force_terminal=not (bool(os.environ.get("NO_COLOR")) or not sys.stdout.isatty()),
    highlight=False,
    soft_wrap=True,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_RESULTS_DIR = Path("results")
DEFAULT_SCENARIOS_DIR = Path("benchmark/scenarios")


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
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON envelope on stdout",
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
        if json_out:
            emit_json(status="error", command="run", error=f"load_scenario: {e}")
        else:
            console.print(f"[red]Error loading scenario: {e}[/red]")
        raise typer.Exit(1) from e

    if not json_out:
        console.print(f"[green]Loaded scenario:[/green] {scenario_obj.title}")
        console.print(f"  Scenario ID: {scenario_obj.scenario_id}")
        console.print(f"  Turns: {scenario_obj.total_turns}")

    if dry_run:
        if json_out:
            emit_json(
                status="ok",
                command="run",
                data={
                    "dry_run": True,
                    "scenario_id": scenario_obj.scenario_id,
                    "total_turns": scenario_obj.total_turns,
                },
            )
            return
        console.print("\n[yellow]Dry run mode - showing turns only[/yellow]")
        for turn in scenario_obj.turns:
            console.print(f"\n[bold]Turn {turn.turn_number}[/bold] ({turn.stage.value if turn.stage else 'unknown'})")
            console.print(f"  {turn.user_message[:100]}...")
        return

    # Run scenario
    if not json_out:
        console.print(f"\n[bold]Running scenario with {model}...[/bold]")
    try:
        from critbench.runner import ScenarioRunner  # noqa: PLC0415

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
        if json_out:
            emit_path(transcript_file, label="transcript")
        else:
            console.print(f"[green]✓ Transcript saved to {transcript_file}[/green]")
    except Exception as e:
        if json_out:
            emit_json(status="error", command="run", error=f"run_scenario: {e}")
        else:
            console.print(f"[red]Error running scenario: {e}[/red]")
        raise typer.Exit(1) from e

    if no_score:
        if json_out:
            emit_json(
                status="ok",
                command="run",
                data={
                    "scenario_id": scenario_obj.scenario_id,
                    "model": model,
                    "transcript_path": str(transcript_file),
                    "scored": False,
                },
            )
            return
        console.print("[yellow]Skipping scoring (--no-score flag)[/yellow]")
        return

    # Score transcript
    if not json_out:
        console.print("\n[bold]Scoring transcript...[/bold]")
    try:
        result_dict = score_fn(
            str(transcript_file),
            scenario,
            enable_llm=True,
            enable_debate=debate,
            enable_anonymization=anonymous,
        )

        # Lazy imports so missing result/writer modules don't break --help.
        from critbench.models.result import BenchmarkResult  # noqa: PLC0415
        from critbench.results.writer import ResultsWriter  # noqa: PLC0415

        # Save result
        result = BenchmarkResult.from_score_result(result_dict, scenario_obj.scenario_id)
        writer = ResultsWriter(str(transcript_file.parent))
        writer.write(result)

        if json_out:
            emit_path(transcript_file.parent, label="results_dir")
            emit_json(
                status="ok",
                command="run",
                data={
                    "scenario_id": scenario_obj.scenario_id,
                    "model": model,
                    "overall_score": result.overall_score,
                    "overall_percentage": result.overall_percentage,
                    "run_id": getattr(result, "run_id", None),
                    "timestamp": getattr(result, "timestamp", None),
                    "transcript_path": str(transcript_file),
                    "results_dir": str(transcript_file.parent),
                },
            )
            return

        # Print summary
        console.print(f"[green]✓ Score: {result.overall_percentage:.1f}%[/green]")
        console.print(f"  Overall: {result.overall_score:.3f}")
        for dim, score in result.dimension_scores.__dict__.items():
            console.print(f"  {dim}: {score.score:.3f}")

    except Exception as e:
        if json_out:
            emit_json(status="error", command="run", error=f"score: {e}")
        else:
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
    out: str | None = typer.Option(
        None,
        "--out",
        help="Output file for full result JSON (default: <transcript-dir>/result.json)",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON envelope on stdout",
    ),
) -> None:
    """Score an existing transcript against a scenario.

    Example:
        critbench score \\
            --transcript results/tier1_campaign_001/anthropic-claude-3.5-sonnet/2026-03-14T12-00/transcript.jsonl \\
            --scenario benchmark/scenarios/tier1/campaign/saas_launch.yaml
    """
    if not json_out:
        console.print("[bold]Scoring transcript...[/bold]")
    try:
        result_dict = score_fn(
            transcript,
            scenario,
            enable_llm=True,
            enable_debate=debate,
        )

        # Persist full result to disk instead of dumping it to the console.
        transcript_path = Path(transcript)
        out_path = Path(out) if out else transcript_path.parent / "result.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result_dict, indent=2, default=str),
            encoding="utf-8",
        )
        emit_path(out_path, label="result")

        overall_pct = float(result_dict.get("overall_percentage", 0) or 0)
        overall_score = float(result_dict.get("overall_score", 0) or 0)
        dimensions = result_dict.get("dimension_scores", {}) or {}

        if json_out:
            dim_summary: dict[str, float] = {}
            for dim, data in dimensions.items():
                if isinstance(data, dict):
                    dim_summary[dim] = float(data.get("score", 0) or 0)
            emit_json(
                status="ok",
                command="score",
                data={
                    "overall_score": overall_score,
                    "overall_percentage": overall_pct,
                    "dimension_scores": dim_summary,
                    "result_path": str(out_path),
                    "autofail": result_dict.get("autofail", False),
                },
            )
            return

        # Human summary: overall + per-dimension only.
        console.print(f"[green]✓ Overall: {overall_pct:.1f}%[/green]")
        for dim, data in dimensions.items():
            if isinstance(data, dict):
                console.print(f"  {dim}: {data.get('score', 0):.3f}")

    except Exception as e:
        if json_out:
            emit_json(status="error", command="score", error=str(e))
        else:
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
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON envelope on stdout",
    ),
) -> None:
    """Show leaderboard from results directory.

    Example:
        critbench leaderboard --results results/ --out leaderboard.md
    """
    results_dir = Path(results)
    if not results_dir.exists():
        if json_out:
            emit_json(
                status="error",
                command="leaderboard",
                error=f"results_dir_not_found: {results_dir}",
            )
        else:
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
        if json_out:
            emit_json(
                status="ok",
                command="leaderboard",
                data={"models": [], "scenarios": []},
            )
            return
        console.print("[yellow]No results found in results directory[/yellow]")
        return

    # Sort once up front so both JSON + human paths use the same ordering.
    sorted_models_pre = sorted(
        results_by_model.items(),
        key=lambda x: (
            sum(x[1]["overall"]) / len(x[1]["overall"]) if x[1]["overall"] else 0
        ),
        reverse=True,
    )

    if json_out:
        rows: list[dict] = []
        for model_name, scores in sorted_models_pre:
            row: dict = {"model": model_name, "runs": run_count[model_name]}
            for dim in ("overall", "coherence", "judgment", "voice", "originality", "ethics", "adaptation"):
                vals = scores.get(dim, [])
                row[dim] = (sum(vals) / len(vals)) if vals else 0.0
            rows.append(row)
        emit_json(
            status="ok",
            command="leaderboard",
            data={
                "models": rows,
                "scenarios": sorted(scenario_ids),
                "results_dir": str(results_dir),
            },
        )
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


@app.command()
def doctor() -> None:
    """Validate environment + filesystem preconditions.

    Checks:
      - OPENROUTER_API_KEY is present
      - Scenarios dir exists
      - Results dir exists or can be created
    """
    scenarios_dir = DEFAULT_SCENARIOS_DIR
    # Allow invocation from repo root OR benchmark/ subdir.
    if not scenarios_dir.exists() and Path("scenarios").exists():
        scenarios_dir = Path("scenarios")

    results_dir = DEFAULT_RESULTS_DIR

    def _results_writable() -> bool:
        try:
            results_dir.mkdir(parents=True, exist_ok=True)
            return results_dir.is_dir() and os.access(results_dir, os.W_OK)
        except OSError:
            return False

    checks = [
        DoctorCheck(
            name="OPENROUTER_API_KEY",
            check=lambda: bool(os.environ.get("OPENROUTER_API_KEY")),
            hint="export OPENROUTER_API_KEY=<key>",
        ),
        DoctorCheck(
            name=f"scenarios dir ({scenarios_dir})",
            check=lambda: scenarios_dir.is_dir(),
            hint="run from repo root, or pass an explicit --scenario path",
        ),
        DoctorCheck(
            name=f"results dir ({results_dir}) writable",
            check=_results_writable,
            hint="check filesystem permissions",
        ),
    ]
    raise typer.Exit(doctor_runner(checks, exit_on_fail=False))


@app.command()
def get(
    run_id: str = typer.Option(..., "--run-id", help="Run ID to load (filename stem in results dir)"),
    results: str = typer.Option("results", "--results", help="Results directory"),
    full: bool = typer.Option(False, "--full", help="Return the complete result record"),
) -> None:
    """Fetch a single benchmark result by run_id as JSON.

    Walks the results directory looking for `<run_id>.json`. Default output
    narrows to (model, overall, timestamp, run_id); pass --full for the
    complete record.
    """
    results_dir = Path(results)
    if not results_dir.exists():
        emit_json(status="error", command="get", error=f"results_dir_not_found: {results_dir}")
        raise typer.Exit(1)

    # Results writer saves `<run_id>.json` one level below the parent dir
    # the writer was constructed with, but `run` persists to a nested dir
    # (results/<scenario>/<model_slug>/<ts>/<run_id>.json). Search recursively.
    candidates = list(results_dir.rglob(f"{run_id}.json"))
    # Exclude index files just in case.
    candidates = [p for p in candidates if p.name != "index.json"]
    if not candidates:
        emit_json(status="error", command="get", error=f"run_not_found: {run_id}")
        raise typer.Exit(1)

    run_path = candidates[0]
    try:
        record = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        emit_json(status="error", command="get", error=f"load_failed: {e}")
        raise typer.Exit(1) from e

    if full:
        emit_json(
            status="ok",
            command="get",
            data={"run_id": run_id, "path": str(run_path), "record": record},
        )
        return

    metadata = record.get("metadata") or {}
    narrow = {
        "run_id": record.get("run_id", run_id),
        "model": record.get("model") or metadata.get("model"),
        "overall": record.get("overall_percentage", record.get("overall_score")),
        "timestamp": record.get("timestamp"),
    }
    emit_json(status="ok", command="get", data=narrow)


if __name__ == "__main__":
    app()
