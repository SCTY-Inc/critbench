"""Scenario loader that validates against Scenario model and supports YAML inheritance."""
from __future__ import annotations

from pathlib import Path

from critbench.loaders.yaml_loader import YAMLLoader
from critbench.models import Scenario


class ScenarioLoader:
    """Loads and validates scenario files in YAML or JSON format."""

    def __init__(self, base_dir: str | Path | None = None):
        """Initialize loader.

        Args:
            base_dir: Base directory for resolving relative paths in extends:
        """
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self.yaml_loader = YAMLLoader(self.base_dir)

    def load(self, path: str | Path) -> Scenario:
        """Load and validate a scenario file.

        Args:
            path: Path to scenario file (.yaml or .json)

        Returns:
            Validated Scenario object

        Raises:
            FileNotFoundError: If scenario file not found
            ValueError: If scenario validation fails
        """
        path = Path(path)
        if not path.is_absolute():
            path = self.base_dir / path

        # Load raw data
        raw_data = self.yaml_loader.load(path)

        # Validate and construct Scenario
        try:
            scenario = Scenario.from_dict(raw_data)
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid scenario format in {path}: {e}") from e

        return scenario

    def load_many(self, paths: list[str | Path]) -> list[Scenario]:
        """Load and validate multiple scenario files.

        Args:
            paths: List of paths to scenario files

        Returns:
            List of validated Scenario objects
        """
        return [self.load(path) for path in paths]
