"""R1: Test the full guard flow (read → deny → allow) for both platforms.

Tests that:
1. A write to a guarded file is denied when the rule doc has NOT been read.
2. After a full read of the rule doc, the same write is allowed.
3. A shell command writing to a guarded path obeys the same logic.
4. Files with no matching rules are always allowed.

Uses entry.py via subprocess with JSON payloads (black-box integration).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENTRY = SCRIPTS / "entry.py"

RULE_DOC_NAME = "coding-global.md"
RULE_DOC_RPATH = f"skill-config/cursor-rule-guard/{RULE_DOC_NAME}"  # path in rules JSON
GUARDED_FILE = "frontend/js/main.js"
UNGUARDED_FILE = "README.md"

RULE_GUARD_JSON = {
    "fileGuard": {
        "enabled": True,
        "rules": [
            {
                "glob": "frontend/**/*.js",
                "required": [RULE_DOC_RPATH],
            }
        ],
    }
}


def _write_runtime_config(tmp_path: Path, platform: str) -> None:
    if platform == "cursor":
        dest = tmp_path / ".cursor" / "skills" / "lulu-rule-guard" / "rule-guard-config.json"
    else:
        dest = tmp_path / ".github" / "lulu-rule-guard" / "rule-guard-config.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"version": 2, **RULE_GUARD_JSON}),
        encoding="utf-8",
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _setup_project(tmp_path: Path, platform: str) -> tuple[Path, Path]:
    """Write rule-guard-config.json in tmp_path for given platform."""
    rules_dir = tmp_path / "skill-config" / "cursor-rule-guard"
    rules_dir.mkdir(parents=True)

    rule_doc = rules_dir / RULE_DOC_NAME
    rule_doc.write_text("# Coding global rules\n...\n", encoding="utf-8")

    _write_runtime_config(tmp_path, platform)

    return tmp_path, rule_doc

def _run_entry(platform: str, payload: dict, cwd: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--platform", platform],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert result.returncode == 0, f"entry.py crashed:\n{result.stderr}"
    return json.loads(result.stdout.strip())


def _is_allowed_cursor(out: dict) -> bool:
    return out.get("permission") == "allow"


def _is_denied_cursor(out: dict) -> bool:
    return out.get("permission") == "deny"


def _is_allowed_copilot(out: dict) -> bool:
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "allow"


def _is_denied_copilot(out: dict) -> bool:
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# ── Subprocess helpers ─────────────────────────────────────────────────────────

class TestCursorGuardFlow:
    def test_write_denied_before_read(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "cursor")
        payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "conversation_id": "test-sess-cursor",
            "tool_input": {
                "file_path": GUARDED_FILE,
                "content": "new content",
            },
        }
        out = _run_entry("cursor", payload, cwd)
        assert _is_denied_cursor(out), f"Expected deny, got: {out}"
        assert RULE_DOC_NAME in json.dumps(out)

    def test_write_allowed_after_full_read(self, tmp_path):
        cwd, rule_doc = _setup_project(tmp_path, "cursor")
        session_id = "test-sess-cursor-2"

        # Step 1: full read of rule doc (path matches RULE_DOC_RPATH in rules JSON)
        read_payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Read",
            "conversation_id": session_id,
            "tool_input": {
                "path": RULE_DOC_RPATH,
                # No offset/limit → full read
            },
        }
        out_read = _run_entry("cursor", read_payload, cwd)
        assert _is_allowed_cursor(out_read), f"Read should allow: {out_read}"

        # Step 2: write to guarded file should now be allowed
        write_payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "conversation_id": session_id,
            "tool_input": {
                "file_path": GUARDED_FILE,
                "content": "new content",
            },
        }
        out_write = _run_entry("cursor", write_payload, cwd)
        assert _is_allowed_cursor(out_write), f"Expected allow after read, got: {out_write}"

    def test_unguarded_file_always_allowed(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "cursor")
        payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "conversation_id": "test-unguarded",
            "tool_input": {"file_path": UNGUARDED_FILE, "content": "x"},
        }
        out = _run_entry("cursor", payload, cwd)
        assert _is_allowed_cursor(out), f"Unguarded file should allow: {out}"

    def test_shell_write_denied_before_read(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "cursor")
        payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Shell",
            "conversation_id": "test-shell-cursor",
            "tool_input": {
                "command": f"echo hello > {GUARDED_FILE}",
            },
        }
        out = _run_entry("cursor", payload, cwd)
        assert _is_denied_cursor(out), f"Shell write should be denied: {out}"

    def test_read_only_shell_always_allowed(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "cursor")
        payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "Shell",
            "conversation_id": "test-shell-ro",
            "tool_input": {"command": "cat README.md"},
        }
        out = _run_entry("cursor", payload, cwd)
        assert _is_allowed_cursor(out), f"Read-only shell should allow: {out}"

    def test_unknown_tool_always_allowed(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "cursor")
        payload = {
            "hook_event_name": "preToolUse",
            "tool_name": "SomeFutureTool",
            "conversation_id": "test-unknown",
            "tool_input": {},
        }
        out = _run_entry("cursor", payload, cwd)
        assert _is_allowed_cursor(out), f"Unknown tool should allow: {out}"


# ── Copilot tests ──────────────────────────────────────────────────────────────

class TestCopilotGuardFlow:
    def test_write_denied_before_read(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "copilot")
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "create_file",
            "sessionId": "copilot-sess-1",
            "tool_input": {
                "filePath": GUARDED_FILE,
                "content": "new content",
            },
        }
        out = _run_entry("copilot", payload, cwd)
        assert _is_denied_copilot(out), f"Expected deny, got: {out}"
        reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        assert RULE_DOC_NAME in reason

    def test_write_allowed_after_full_read(self, tmp_path):
        cwd, rule_doc = _setup_project(tmp_path, "copilot")
        session_id = "copilot-sess-2"
        doc_rel = str(rule_doc.relative_to(tmp_path))

        # Step 1: full read of rule doc (no startLine/endLine → full)
        read_payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "read_file",
            "sessionId": session_id,
            "tool_input": {"filePath": RULE_DOC_RPATH},
        }
        out_read = _run_entry("copilot", read_payload, cwd)
        assert _is_allowed_copilot(out_read), f"Read should allow: {out_read}"

        # Step 2: write now allowed
        write_payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "replace_string_in_file",
            "sessionId": session_id,
            "tool_input": {
                "filePath": GUARDED_FILE,
                "oldString": "a",
                "newString": "b",
            },
        }
        out_write = _run_entry("copilot", write_payload, cwd)
        assert _is_allowed_copilot(out_write), f"Expected allow after read, got: {out_write}"

    def test_multi_replace_denied_before_read(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "copilot")
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "multi_replace_string_in_file",
            "sessionId": "copilot-multi",
            "tool_input": {
                "filePath": GUARDED_FILE,
                "replacements": [],
            },
        }
        out = _run_entry("copilot", payload, cwd)
        assert _is_denied_copilot(out), f"Expected deny for multi_replace: {out}"

    def test_shell_write_denied_before_read(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "copilot")
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "run_in_terminal",
            "sessionId": "copilot-shell",
            "tool_input": {"command": f"echo hello > {GUARDED_FILE}"},
        }
        out = _run_entry("copilot", payload, cwd)
        assert _is_denied_copilot(out), f"Shell write should be denied: {out}"

    def test_unguarded_file_always_allowed(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "copilot")
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "create_file",
            "sessionId": "copilot-unguarded",
            "tool_input": {"filePath": UNGUARDED_FILE, "content": "x"},
        }
        out = _run_entry("copilot", payload, cwd)
        assert _is_allowed_copilot(out), f"Unguarded file should allow: {out}"

    def test_unknown_tool_always_allowed(self, tmp_path):
        cwd, _ = _setup_project(tmp_path, "copilot")
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "some_future_tool",
            "sessionId": "copilot-unknown",
            "tool_input": {},
        }
        out = _run_entry("copilot", payload, cwd)
        assert _is_allowed_copilot(out), f"Unknown tool should allow: {out}"
