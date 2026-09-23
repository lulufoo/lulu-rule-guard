"""Tests for add-guard-rule --local."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

_SPEC = importlib.util.spec_from_file_location(
    "add_guard_rule", SCRIPTS / "add-guard-rule.py"
)
add_guard_rule = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(add_guard_rule)


def _write_md(path: Path, glob: str, body: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nrule-guard:\n  globs:\n    - \"{glob}\"\n---\n\n{body}",
        encoding="utf-8",
    )


def test_local_registers_and_replaces_same_glob(tmp_path: Path) -> None:
    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        config = tmp_path / ".cursor" / "skills" / "lulu-rule-guard" / "rule-guard-config.json"
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps(
                {
                    "version": 2,
                    "fileGuard": {
                        "enabled": True,
                        "rules": [
                            {"glob": "**/*.py", "required": ["docs/old.md"]},
                            {
                                "glob": "**/*.{ts,js}",
                                "required": ["docs/coding/py.md"],
                            },
                        ],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        local_dir = tmp_path / ".cursor" / "skills" / "lulu-discipline-skills"
        _write_md(local_dir / "coding" / "py.md", "**/*.py")
        (local_dir / "git").mkdir(parents=True)
        (local_dir / "git" / "git.md").write_text("# no frontmatter\n", encoding="utf-8")
        rc = add_guard_rule.main(["--local", str(local_dir)])
        assert rc == 0
        data = json.loads(config.read_text(encoding="utf-8"))
        rules = data["fileGuard"]["rules"]
        assert len(rules) == 1
        assert rules[0]["glob"] == "**/*.py"
        assert rules[0]["required"] == [
            ".cursor/skills/lulu-discipline-skills/coding/py.md"
        ]
    finally:
        os.chdir(old)


def test_local_missing_path(tmp_path: Path) -> None:
    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        rc = add_guard_rule.main(["--local", "nope.md"])
        assert rc == 1
    finally:
        os.chdir(old)


def test_source_url_and_local_mutex() -> None:
    with pytest.raises(SystemExit):
        add_guard_rule.main(
            ["--source-url", "github:o/r@main/a.md", "--local", "x.md"]
        )
