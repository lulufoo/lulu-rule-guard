"""Rule identity follows symlinks and does not collapse to the basename."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENTRY = SCRIPTS / "entry.py"
sys.path.insert(0, str(SCRIPTS))

from lib.state import check_doc_loaded, write_read_state  # noqa: E402


def _run_entry(payload: dict, cwd: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--platform", "cursor"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def _write_config(project: Path, required: str) -> None:
    dest = project / ".cursor" / "skills" / "lulu-rule-guard" / "rule-guard-config.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(
        json.dumps(
            {
                "version": 2,
                "fileGuard": {
                    "enabled": True,
                    "rules": [{"glob": "**/*.py", "required": [required]}],
                },
            }
        ),
        encoding="utf-8",
    )


def test_symlink_outside_project_read_allows_write(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "rule.md").write_text("# rule\n", encoding="utf-8")
    project = tmp_path / "project"
    link_parent = project / ".cursor" / "skills"
    link_parent.mkdir(parents=True)
    (link_parent / "rules").symlink_to(outside, target_is_directory=True)
    required = ".cursor/skills/rules/rule.md"
    _write_config(project, required)

    session = "symlink-session"
    read_out = _run_entry(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Read",
            "conversation_id": session,
            "tool_input": {"path": required},
        },
        project,
    )
    assert read_out.get("permission") == "allow"
    write_out = _run_entry(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "conversation_id": session,
            "tool_input": {"file_path": "app.py", "content": "x = 1\n"},
        },
        project,
    )
    assert write_out.get("permission") == "allow", write_out


def test_same_basename_does_not_share_read_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    (project / "a").mkdir(parents=True)
    (project / "b").mkdir()
    (project / "a" / "rule.md").write_text("a\n", encoding="utf-8")
    (project / "b" / "rule.md").write_text("b\n", encoding="utf-8")
    monkeypatch.chdir(project)
    state_root = tmp_path / "state"
    session = "same-name"
    write_read_state(session, "a/rule.md", state_root)
    assert check_doc_loaded("a/rule.md", session, state_root)
    assert not check_doc_loaded("b/rule.md", session, state_root)
