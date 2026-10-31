#!/usr/bin/env python3
"""Run the vendored yuque-cli without installing the PyPI package."""

from __future__ import annotations

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "vendor"
sys.path.insert(0, str(VENDOR))

from yuque_cli.cli import app  # noqa: E402


def main() -> None:
    app()


if __name__ == "__main__":
    main()
