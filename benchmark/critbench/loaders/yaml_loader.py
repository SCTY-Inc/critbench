"""Structured file loaders for CritBench scenarios and configs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_serialized_file(path: str | Path) -> Any:
    """Load a JSON or YAML file."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    with file_path.open() as handle:
        if suffix == ".json":
            return json.load(handle)
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(handle)

    raise ValueError(f"Unsupported file format: {file_path.suffix}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge nested mappings while replacing scalar and list values."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class YAMLLoader:
    """Load JSON or YAML scenario files, including simple inheritance."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(".")

    def load(self, path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.base_dir / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {file_path}")

        data = load_serialized_file(file_path)
        if not isinstance(data, dict):
            raise ValueError(f"Structured file must contain a mapping: {file_path}")

        parent_ref = data.get("extends")
        if not parent_ref:
            return data

        child = dict(data)
        child.pop("extends", None)

        parent_path = Path(parent_ref)
        if not parent_path.is_absolute():
            parent_path = file_path.parent / parent_path

        parent_data = self.load(parent_path)
        return _deep_merge(parent_data, child)
