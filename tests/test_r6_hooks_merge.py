"""R6: Test init.py merges hooks.json correctly for Cursor and Copilot.

Run from .cache/temp/rule-guard/:
    pytest tests/ -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

# ── helpers ────────────────────────────────────────────────────────────────────

def _load_hooks(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Cursor hooks merge ─────────────────────────────────────────────────────────

def test_cursor_hooks_created_fresh(tmp_path, monkeypatch):
    """init --platform cursor creates .cursor/hooks.json from scratch."""
    monkeypatch.chdir(tmp_path)
    # Patch config_path so init doesn't write to real .cursor/
    import init as init_mod
    import config_util

    monkeypatch.setattr(
        config_util,
        "config_path",
        lambda platform="cursor": tmp_path / f".{platform}/lulu-rule-guard/rule-guard-config.json",
    )

    result = init_mod._merge_cursor_hooks()
    hooks_path = tmp_path / ".cursor" / "hooks.json"
    assert hooks_path.exists(), "hooks.json was not created"

    data = _load_hooks(hooks_path)
    hooks = data["hooks"]

    pre = hooks["preToolUse"]
    cmds = [e["command"] for e in pre]
    assert any("entry.py --platform cursor" in c for c in cmds), cmds

    guard_entries = [e for e in pre if "entry.py --platform cursor" in e.get("command", "")]
    assert len(guard_entries) == 1, guard_entries
    assert guard_entries[0].get("matcher") == "Read|Write|Edit|Shell"

    assert "beforeReadFile" not in hooks

    # stop must have play_chime
    stop = hooks["stop"]
    assert any("play_chime" in e["command"] for e in stop)

    # legacy pathGuard prompt_entry must not be re-registered
    bsp = hooks.get("beforeSubmitPrompt", [])
    prompt_cmds = [e.get("command", "") for e in bsp]
    assert not any("prompt_entry.py" in c for c in prompt_cmds), prompt_cmds


def test_cursor_hooks_idempotent(tmp_path, monkeypatch):
    """Running cursor init twice does not duplicate entries."""
    monkeypatch.chdir(tmp_path)
    import init as init_mod

    init_mod._merge_cursor_hooks()
    init_mod._merge_cursor_hooks()

    data = _load_hooks(tmp_path / ".cursor" / "hooks.json")
    hooks = data["hooks"]

    # Each guard entry should appear exactly once
    pre_cmds = [e["command"] for e in hooks["preToolUse"]]
    cursor_entries = [c for c in pre_cmds if "entry.py --platform cursor" in c]
    assert len(cursor_entries) == 1, f"Expected 1, got {len(cursor_entries)}: {cursor_entries}"

    chime_stops = [e for e in hooks["stop"] if "play_chime" in e["command"]]
    assert len(chime_stops) == 1, f"Chime duplicated: {chime_stops}"

    prompt_entries = [
        c for c in [e["command"] for e in hooks.get("beforeSubmitPrompt", [])]
        if "prompt_entry.py" in c
    ]
    assert prompt_entries == []


def test_cursor_hooks_preserves_existing(tmp_path, monkeypatch):
    """Existing non-rule-guard entries are preserved after merge."""
    monkeypatch.chdir(tmp_path)
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    hooks_file = cursor_dir / "hooks.json"
    hooks_file.write_text(
        json.dumps({
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {"command": "python3 other-tool.py", "timeout": 3, "failClosed": False}
                ],
                "stop": [
                    {"command": "python3 my-stop.py", "timeout": 2, "failClosed": False}
                ],
            },
        }) + "\n",
        encoding="utf-8",
    )

    import init as init_mod
    init_mod._merge_cursor_hooks()

    data = _load_hooks(hooks_file)
    pre_cmds = [e["command"] for e in data["hooks"]["preToolUse"]]
    assert "python3 other-tool.py" in pre_cmds, "Existing entry lost"

    stop_cmds = [e["command"] for e in data["hooks"]["stop"]]
    assert "python3 my-stop.py" in stop_cmds, "Existing stop entry lost"


def test_cursor_hooks_replaces_old_per_script_entries(tmp_path, monkeypatch):
    """Old audit-read.py / guard-write.py entries are replaced by entry.py."""
    monkeypatch.chdir(tmp_path)
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    (cursor_dir / "hooks.json").write_text(
        json.dumps({
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {
                        "matcher": "Read",
                        "command": "python3 ~/.cursor/skills/cursor-rule-guard/scripts/audit-read.py",
                        "timeout": 5,
                        "failClosed": False,
                    },
                    {
                        "matcher": "Write|Edit|Shell",
                        "command": "python3 ~/.cursor/skills/cursor-rule-guard/scripts/guard-write.py",
                        "timeout": 5,
                        "failClosed": False,
                    },
                ]
            },
        }) + "\n",
        encoding="utf-8",
    )

    import init as init_mod
    init_mod._merge_cursor_hooks()

    data = _load_hooks(cursor_dir / "hooks.json")
    pre_cmds = [e["command"] for e in data["hooks"]["preToolUse"]]
    assert not any("audit-read" in c for c in pre_cmds), "audit-read not replaced"
    assert not any("guard-write" in c for c in pre_cmds), "guard-write not replaced"
    assert any("entry.py --platform cursor" in c for c in pre_cmds), "entry.py missing"


def test_cursor_hooks_strips_before_read_file(tmp_path, monkeypatch):
    """Re-init removes rule-guard entry from beforeReadFile; preserves other hooks."""
    monkeypatch.chdir(tmp_path)
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    hooks_file = cursor_dir / "hooks.json"
    hooks_file.write_text(
        json.dumps({
            "version": 1,
            "hooks": {
                "preToolUse": [],
                "beforeReadFile": [
                    {
                        "command": "python3 ~/.cursor/skills/lulu-rule-guard/scripts/entry.py --platform cursor",
                        "timeout": 5,
                        "failClosed": False,
                    },
                    {
                        "command": "python3 custom-read-hook.py",
                        "timeout": 5,
                        "failClosed": False,
                    },
                ],
            },
        }) + "\n",
        encoding="utf-8",
    )

    import init as init_mod
    init_mod._merge_cursor_hooks()

    data = _load_hooks(hooks_file)
    hooks = data["hooks"]
    before = hooks.get("beforeReadFile", [])
    assert len(before) == 1
    assert before[0]["command"] == "python3 custom-read-hook.py"
    assert not any("rule-guard" in e.get("command", "") for e in before)


# ── Copilot hooks merge ────────────────────────────────────────────────────────

def test_copilot_hooks_created_fresh(tmp_path, monkeypatch):
    """init copilot creates .github/hooks/hooks.json from scratch."""
    monkeypatch.chdir(tmp_path)
    import init as init_mod

    result = init_mod._merge_copilot_hooks()
    hooks_path = tmp_path / ".github" / "hooks" / "hooks.json"
    assert hooks_path.exists(), "Copilot hooks.json not created"

    data = _load_hooks(hooks_path)
    hooks = data["hooks"]

    pre = hooks["PreToolUse"]
    assert any("entry.py --platform copilot" in e["command"] for e in pre)
    # No matcher field for Copilot (catches all tools)
    assert not any("matcher" in e for e in pre)
    # VS Code requires type: "command"
    assert all(e.get("type") == "command" for e in pre)

    stop = hooks["Stop"]
    assert any("play_chime" in e["command"] for e in stop)


def test_copilot_hooks_idempotent(tmp_path, monkeypatch):
    """Running copilot init twice does not duplicate entries."""
    monkeypatch.chdir(tmp_path)
    import init as init_mod

    init_mod._merge_copilot_hooks()
    init_mod._merge_copilot_hooks()

    data = _load_hooks(tmp_path / ".github" / "hooks" / "hooks.json")
    hooks = data["hooks"]

    copilot_entries = [
        e for e in hooks["PreToolUse"]
        if "entry.py --platform copilot" in e["command"]
    ]
    assert len(copilot_entries) == 1, f"Duplicated: {copilot_entries}"

    chime_stops = [e for e in hooks["Stop"] if "play_chime" in e["command"]]
    assert len(chime_stops) == 1, f"Chime duplicated: {chime_stops}"


def test_copilot_hooks_preserves_existing(tmp_path, monkeypatch):
    """Existing non-rule-guard Copilot entries are preserved."""
    monkeypatch.chdir(tmp_path)
    hooks_dir = tmp_path / ".github" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(
        json.dumps({
            "version": 1,
            "hooks": {
                "PreToolUse": [
                    {"command": "python3 other-copilot-hook.py", "timeout": 3, "failClosed": False}
                ],
            },
        }) + "\n",
        encoding="utf-8",
    )

    import init as init_mod
    init_mod._merge_copilot_hooks()

    data = _load_hooks(hooks_dir / "hooks.json")
    pre_cmds = [e["command"] for e in data["hooks"]["PreToolUse"]]
    assert "python3 other-copilot-hook.py" in pre_cmds, "Existing Copilot entry lost"
