"""YAML scenario loader with inheritance support.

Loads scenario files in YAML or JSON format with optional `extends:` inheritance.
Child scenarios override parent fields recursively.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override dict into base dict, with override taking precedence.

    Recursively merges nested dicts, lists are replaced (not merged).

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class YAMLLoader:
    """Loads YAML scenario files with inheritance support."""

    def __init__(self, base_dir: Path | None = None):
        """Initialize loader.

        Args:
            base_dir: Base directory for resolving relative paths in extends:
        """
        self.base_dir = base_dir or Path(".")

    def load(self, path: str | Path) -> dict[str, Any]:
        """Load a scenario file with inheritance resolution.

        Args:
            path: Path to scenario file (.yaml or .json)

        Returns:
            Fully resolved scenario dict with inheritance applied

        Raises:
            FileNotFoundError: If file or parent file not found
            ValueError: If extends: path cannot be resolved
            yaml.YAMLError: If YAML parsing fails
            json.JSONDecodeError: If JSON parsing fails
        """
        path = Path(path)
        if not path.is_absolute():
            path = self.base_dir / path

        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")

        # Load the file
        if path.suffix.lower() == ".json":
            with open(path) as f:
                data = json.load(f)
        elif path.suffix.lower() in [".yaml", ".yml"]:
            with open(path) as f:
                data = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        # Resolve inheritance
        if "extends" in data:
            parent_path = data.pop("extends")
            # Resolve parent path relative to current file's directory
            if not Path(parent_path).is_absolute():
                parent_path = path.parent / parent_path
            parent_data = self.load(parent_path)
            result: dict[str, Any] = _deep_merge(parent_data, data)
            return result

        result_dict: dict[str, Any] = data
        return result_dict
