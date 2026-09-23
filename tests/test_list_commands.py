"""Tests for lulu-rule-guard --list."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lulu-rule-guard.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_list_flag() -> None:
    result = run("--list")
    assert result.returncode == 0
    assert result.stdout.strip() == "1. add-guard-rule"


def test_list_subcommand() -> None:
    result = run("list")
    assert result.returncode == 0
    assert result.stdout.strip() == "1. add-guard-rule"
