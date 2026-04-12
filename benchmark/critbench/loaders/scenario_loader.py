"""Validated scenario loading for CritBench."""
from __future__ import annotations

from pathlib import Path

from ..models import Scenario
from .yaml_loader import YAMLLoader


class ScenarioLoader:
    """Load and validate scenario files in JSON or YAML format."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self.yaml_loader = YAMLLoader(self.base_dir)

    def load(self, path: str | Path) -> Scenario:
        raw_data = self.yaml_loader.load(path)
        try:
            return Scenario.from_dict(raw_data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid scenario format in {path}: {exc}") from exc

    def load_many(self, paths: list[str | Path]) -> list[Scenario]:
        return [self.load(path) for path in paths]
