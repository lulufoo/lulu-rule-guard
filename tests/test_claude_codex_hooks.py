"""Hook files and adapters for Claude and Codex."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_util
from lib.grouped_hooks import merge_claude_hooks, merge_codex_hooks
from platforms import claude, codex


def test_claude_and_codex_config_paths():
    assert str(config_util.config_path("claude")) == (
        ".claude/lulu-rule-guard/rule-guard-config.json"
    )
    assert str(config_util.config_path("codex")) == (
        ".codex/lulu-rule-guard/rule-guard-config.json"
    )
    assert str(config_util.cache_root("claude")) == ".cache/claude/lulu-rule-guard"
    assert str(config_util.cache_root("codex")) == ".cache/codex/lulu-rule-guard"


def test_claude_settings_merge_keeps_other_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "echo keep"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    merge_claude_hooks()
    merge_claude_hooks()
    data = json.loads(settings.read_text(encoding="utf-8"))

    assert data["permissions"] == {"allow": ["Read"]}
    pre = data["hooks"]["PreToolUse"]
    commands = [
        hook["command"]
        for group in pre
        for hook in group["hooks"]
    ]
    assert commands[0].endswith("entry.py --platform claude")
    assert commands.count(commands[0]) == 1
    assert "echo keep" in commands
    stop_commands = [
        hook["command"]
        for group in data["hooks"]["Stop"]
        for hook in group["hooks"]
    ]
    assert stop_commands == [
        "python3 ~/.claude/skills/lulu-rule-guard/scripts/play_chime.py --platform claude"
    ]


def test_codex_hooks_merge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    merge_codex_hooks()
    data = json.loads((tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    pre = data["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "Bash|apply_patch|read_file"
    assert pre["hooks"][0]["command"].endswith("entry.py --platform codex")
    assert "matcher" not in data["hooks"]["Stop"][0]


def test_claude_parses_write_and_partial_read():
    event = claude.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "s1",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/app.py"},
        }
    )
    assert event.action == "write"
    assert event.path == "/tmp/app.py"
    assert claude.is_full_read({"file_path": "rule.md", "offset": 2, "limit": 10}) is False


def test_codex_patch_paths_include_move_destination():
    command = (
        "*** Begin Patch\n"
        "*** Update File: old/name.txt\n"
        "*** Move to: renamed/dir/name.txt\n"
        "*** Add File: hello.txt\n"
        "*** End Patch\n"
    )
    assert codex.patch_paths(command) == [
        "old/name.txt",
        "renamed/dir/name.txt",
        "hello.txt",
    ]
    event = codex.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "apply_patch",
            "tool_input": {"command": command},
        }
    )
    assert event.action == "write"
    assert event.path.split("\n") == [
        "old/name.txt",
        "renamed/dir/name.txt",
        "hello.txt",
    ]


def test_codex_read_file_and_cat_count_as_reads(tmp_path):
    rule = tmp_path / "docs" / "rule.md"
    rule.parent.mkdir()
    rule.write_text("line\n" * 4, encoding="utf-8")
    full = codex.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "read_file",
            "tool_input": {"file_path": str(rule), "offset": 1},
        }
    )
    partial = codex.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "read_file",
            "tool_input": {"file_path": str(rule), "offset": 2, "limit": 1, "mode": "slice"},
        }
    )
    indented = {"file_path": str(rule), "mode": "indentation"}
    cat = codex.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {rule}"},
        }
    )
    flagged = codex.parse(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat -n {rule}"},
        }
    )
    assert full.action == "read"
    assert codex.is_full_read(full.tool_input) is True
    assert partial.action == "read"
    assert codex.is_full_read(partial.tool_input) is False
    assert codex.is_full_read(indented) is False
    assert cat.action == "read"
    assert cat.path == str(rule)
    assert flagged.action == "shell"


def test_unparsed_patch_is_denied_when_rules_exist(tmp_path):
    import subprocess

    config = tmp_path / ".codex" / "lulu-rule-guard" / "rule-guard-config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "version": 2,
                "fileGuard": {
                    "enabled": True,
                    "rules": [{"glob": "**/*.py", "required": ["docs/rule.md"]}],
                },
            }
        ),
        encoding="utf-8",
    )
    entry = Path(__file__).resolve().parent.parent / "scripts" / "entry.py"
    result = subprocess.run(
        [sys.executable, str(entry), "--platform", "codex"],
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "thr",
                "tool_name": "apply_patch",
                "tool_input": {"command": "not a patch"},
            }
        ),
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]
    assert decision == "deny"


def test_cat_then_patch_is_allowed(tmp_path):
    import shlex
    import subprocess

    rule = tmp_path / "docs" / "rule.md"
    rule.parent.mkdir()
    rule.write_text("rule\n", encoding="utf-8")
    config = tmp_path / ".codex" / "lulu-rule-guard" / "rule-guard-config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "version": 2,
                "fileGuard": {
                    "enabled": True,
                    "rules": [{"glob": "**/*.py", "required": ["docs/rule.md"]}],
                },
            }
        ),
        encoding="utf-8",
    )
    entry = Path(__file__).resolve().parent.parent / "scripts" / "entry.py"

    def run(payload: dict) -> str:
        result = subprocess.run(
            [sys.executable, str(entry), "--platform", "codex"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    assert run(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "Bash",
            "tool_input": {"command": "cat " + shlex.quote(str(rule))},
        }
    ) == "allow"
    assert run(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "thr",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: app.py\n*** End Patch\n"
            },
        }
    ) == "allow"
