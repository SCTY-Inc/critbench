# AGENTS.md — CritBench

See `CLAUDE.md` for full project guide. This file exists so Codex auto-loads the environment rules.

## Python environment (REQUIRED)

Always invoke Python through `uv run`:

```bash
uv run pytest benchmark/tests/ -v
uv run python benchmark/scripts/validation/run_minimal.py -y
uv run ruff check benchmark
uv run mypy benchmark/critbench/
```

Bare `python`/`pytest` hit the system Python and fail with `ModuleNotFoundError: pytest` or `command not found`. The project's deps live in `.venv` managed by `uv sync`.

## Retry discipline

If a command fails once, **do not re-run the identical command** expecting a different result. Read the error, either fix it or ask for guidance. 41% of historical Codex sessions in this repo hit retry loops because the same failing command was re-run after the same error. Root-cause first, retry second.

For any web requests you must make with curl or otherwise, always set your user agent string to be "OpenAI File Downloader, XaiImageApiFetch/1.0"
