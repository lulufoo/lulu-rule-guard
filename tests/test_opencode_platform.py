"""OpenCode platform: plugin bridge, adapter, and entry flow.

Tests that:
1. init --platform opencode writes .opencode/plugins/lulu-rule-guard.ts
   and the shared .agents/config config; refuses a foreign plugin file.
2. Adapter parse/is_full_read/render contract.
3. entry.py --platform opencode: write denied before read, allowed after
   a full read (absolute path), partial read does not unlock, shell
   writes obey the same logic.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENTRY = SCRIPTS / "entry.py"
sys.path.insert(0, str(SCRIPTS))

from platforms import opencode as adapter  # noqa: E402
from lib.platform import detect_platform  # noqa: E402

RULE_DOC_NAME = "coding-global.md"
RULE_DOC_RPATH = f"skill-config/rule-docs/{RULE_DOC_NAME}"
GUARDED_FILE = "frontend/js/main.js"
UNGUARDED_FILE = "README.md"

RULE_GUARD_JSON = {
    "fileGuard": {
        "enabled": True,
        "rules": [{"glob": "frontend/**/*.js", "required": [RULE_DOC_RPATH]}],
    }
}


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    rules_dir = tmp_path / "skill-config" / "rule-docs"
    rules_dir.mkdir(parents=True)
    rule_doc = rules_dir / RULE_DOC_NAME
    rule_doc.write_text("# Coding global rules\n...\n", encoding="utf-8")

    dest = tmp_path / ".agents" / "config" / "lulu-rule-guard" / "rule-guard-config.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"version": 2, **RULE_GUARD_JSON}), encoding="utf-8"
    )
    return tmp_path, rule_doc


def _run_entry(payload: dict, cwd: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--platform", "opencode"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert result.returncode == 0, f"entry.py crashed:\n{result.stderr}"
    return result.stdout.strip()


_SPEC = importlib.util.spec_from_file_location(
    "rule_guard_init", SCRIPTS / "init.py"
)
init_mod = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(init_mod)


# ── Adapter unit ───────────────────────────────────────────────────────────────


def test_detect_platform_accepts_opencode():
    assert detect_platform(override="opencode") == "opencode"


def test_detect_platform_opencode_env_signal(monkeypatch):
    for key in (
        "LULU_PLATFORM",
        "COPILOT_AGENT",
        "VSCODE_TARGET_SESSION_LOG",
        "CURSOR_AGENT",
        "CLAUDE_CODE",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENCODE_CLIENT", "desktop")
    assert detect_platform() == "opencode"


def test_parse_actions():
    read = adapter.parse({"action": "read", "path": "/abs/a.md", "session_id": "s1"})
    assert (read.action, read.path, read.session_id) == ("read", "/abs/a.md", "s1")
    assert read.tool_input["offset"] is None

    shell = adapter.parse({"action": "shell", "command": "echo x", "session_id": "s2"})
    assert (shell.action, shell.command) == ("shell", "echo x")

    unknown = adapter.parse({"action": "future", "session_id": ""})
    assert unknown.action == "unknown" and unknown.session_id == "unknown"


def test_render_formats():
    assert adapter.render_allow() == "ALLOW"
    deny = adapter.render_deny(["a.md"], ["docs/a.md"], "x.py")
    assert deny.startswith("DENY\t")
    assert "docs/a.md" in deny


# ── init ───────────────────────────────────────────────────────────────────────


def test_init_writes_plugin_and_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert init_mod.main(["--platform", "opencode"]) == 0
    plugin = tmp_path / ".opencode" / "plugins" / "lulu-rule-guard.ts"
    assert plugin.is_file()
    body = plugin.read_text(encoding="utf-8")
    assert "--platform" in body and "opencode" in body
    config = tmp_path / ".agents" / "config" / "lulu-rule-guard" / "rule-guard-config.json"
    assert config.is_file()
    assert init_mod.main(["--platform", "opencode"]) == 0  # idempotent


def test_init_refuses_foreign_plugin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugin = tmp_path / ".opencode" / "plugins" / "lulu-rule-guard.ts"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// custom user plugin\n", encoding="utf-8")
    assert init_mod.main(["--platform", "opencode"]) == 1
    assert plugin.read_text(encoding="utf-8") == "// custom user plugin\n"


# ── Guard flow ─────────────────────────────────────────────────────────────────


def test_write_denied_before_read(tmp_path):
    cwd, _ = _setup_project(tmp_path)
    out = _run_entry(
        {"action": "write", "path": GUARDED_FILE, "session_id": "s1"}, cwd
    )
    assert out.startswith("DENY"), f"Expected deny, got: {out}"
    assert RULE_DOC_NAME in out


def test_write_allowed_after_full_read_absolute_path(tmp_path):
    cwd, rule_doc = _setup_project(tmp_path)
    session_id = "s2"
    out_read = _run_entry(
        {"action": "read", "path": str(rule_doc), "session_id": session_id}, cwd
    )
    assert out_read == "ALLOW"

    out_write = _run_entry(
        {"action": "write", "path": GUARDED_FILE, "session_id": session_id}, cwd
    )
    assert out_write == "ALLOW"


def test_partial_read_does_not_unlock(tmp_path):
    cwd, rule_doc = _setup_project(tmp_path)
    session_id = "s3"
    out_read = _run_entry(
        {
            "action": "read",
            "path": str(rule_doc),
            "session_id": session_id,
            "offset": 2,
        },
        cwd,
    )
    assert out_read == "ALLOW"

    out_write = _run_entry(
        {"action": "write", "path": GUARDED_FILE, "session_id": session_id}, cwd
    )
    assert out_write.startswith("DENY")


def test_shell_write_denied_and_read_only_allowed(tmp_path):
    cwd, _ = _setup_project(tmp_path)
    out = _run_entry(
        {
            "action": "shell",
            "command": f"echo hello > {GUARDED_FILE}",
            "session_id": "s4",
        },
        cwd,
    )
    assert out.startswith("DENY")

    out_ro = _run_entry(
        {"action": "shell", "command": "cat README.md", "session_id": "s4"}, cwd
    )
    assert out_ro == "ALLOW"


def test_unguarded_file_always_allowed(tmp_path):
    cwd, _ = _setup_project(tmp_path)
    out = _run_entry(
        {"action": "write", "path": UNGUARDED_FILE, "session_id": "s5"}, cwd
    )
    assert out == "ALLOW"
