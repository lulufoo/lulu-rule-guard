"""Platform detection precedence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.platform import PlatformDetectionError, detect_platform, resolve_platform_context

_SIGNAL_KEYS = (
    "LULU_PLATFORM",
    "COPILOT_AGENT",
    "VSCODE_TARGET_SESSION_LOG",
    "CURSOR_AGENT",
    "CLAUDE_CODE",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _SIGNAL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_override_wins_over_signals(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert detect_platform(override="copilot") == "copilot"


def test_lulu_platform_wins_over_cursor_agent(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LULU_PLATFORM", "claude")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert detect_platform() == "claude"


def test_lulu_platform_codex(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LULU_PLATFORM", "codex")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert detect_platform() == "codex"


def test_signal_order(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("COPILOT_AGENT", "1")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    monkeypatch.setenv("CLAUDE_CODE", "1")
    assert detect_platform() == "copilot"

    monkeypatch.delenv("COPILOT_AGENT")
    assert detect_platform() == "cursor"

    monkeypatch.delenv("CURSOR_AGENT")
    assert detect_platform() == "claude"

    monkeypatch.delenv("CLAUDE_CODE")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    assert detect_platform() == "codex"


def test_codex_signal_loses_to_earlier_hosts(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.setenv("CODEX_SESSION_ID", "session-1")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert detect_platform() == "cursor"

    monkeypatch.delenv("CURSOR_AGENT")
    monkeypatch.setenv("CLAUDE_CODE", "1")
    assert detect_platform() == "claude"

    monkeypatch.delenv("CLAUDE_CODE")
    monkeypatch.setenv("COPILOT_AGENT", "1")
    assert detect_platform() == "copilot"


def test_codex_session_id_selects_codex(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEX_SESSION_ID", "session-1")
    assert detect_platform() == "codex"


def test_strict_raises(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(PlatformDetectionError):
        detect_platform(strict=True)


def test_non_strict_defaults_cursor(monkeypatch):
    _clear(monkeypatch)
    assert detect_platform() == "cursor"


def test_resolve_platform_context_paths(tmp_path, monkeypatch):
    _clear(monkeypatch)
    script = tmp_path / "lulu-rule-guard" / "scripts" / "platform_context.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    payload = resolve_platform_context(script_path=script, override="claude")
    assert payload == {
        "platform": "claude",
        "skill_root": str((tmp_path / "lulu-rule-guard").resolve()),
        "rule_guard_dir": ".claude/lulu-rule-guard",
        "cache_dir": ".cache/claude/lulu-rule-guard",
    }


def test_platform_context_script_prints_json():
    import subprocess

    script = SCRIPTS / "platform_context.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CURSOR_AGENT": "1"},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["platform"] == "cursor"
    assert payload["rule_guard_dir"] == ".cursor/skills/lulu-rule-guard"
