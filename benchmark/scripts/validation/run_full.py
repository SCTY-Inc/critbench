#!/usr/bin/env python3
from __future__ import annotations

from run_minimal import run_validation


def main() -> int:
    return run_validation(("tier0", "tier1"), "full validation")


if __name__ == "__main__":
    raise SystemExit(main())
