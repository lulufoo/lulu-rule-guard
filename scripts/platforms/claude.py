#!/usr/bin/env python3
"""Claude Code platform adapter for rule-guard.

PreToolUse input (https://code.claude.com/docs/en/hooks):
  hook_event_name : "PreToolUse"
  session_id      : session identifier
  tool_name       : Read | Write | Edit | Bash | PowerShell | ...
  tool_input      : file_path for Read/Write/Edit; command for Bash/PowerShell
  Read range      : offset (line to start), limit (line count)
  deny format     : hookSpecificOutput.permissionDecision = deny
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List

from lib.state import count_lines

READ_TOOLS = {"Read"}
WRITE_TOOLS = {"Write", "Edit"}
SHELL_TOOLS = {"Bash", "PowerShell"}


@dataclass
class ParsedEvent:
    session_id: str
    event_type: str
    action: str
    path: str
    command: str
    tool_input: dict


def parse(payload: dict) -> ParsedEvent:
    session_id = (payload.get("session_id") or "unknown").strip() or "unknown"
    event_type = payload.get("hook_event_name") or ""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if event_type != "PreToolUse":
        return ParsedEvent(session_id, event_type, "unknown", "", "", tool_input)

    if tool_name in READ_TOOLS:
        path = tool_input.get("file_path") or ""
        return ParsedEvent(session_id, event_type, "read", path, "", tool_input)
    if tool_name in WRITE_TOOLS:
        path = tool_input.get("file_path") or ""
        return ParsedEvent(session_id, event_type, "write", path, "", tool_input)
    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command") or ""
        return ParsedEvent(session_id, event_type, "shell", "", str(command), tool_input)

    return ParsedEvent(session_id, event_type, "unknown", "", "", tool_input)


def is_full_read(tool_input: dict) -> bool:
    """True when Read starts at the first line and limit covers the file."""
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    if isinstance(offset, int) and offset > 1:
        return False
    if limit is None or not isinstance(limit, int):
        return True
    path = tool_input.get("file_path") or ""
    total = count_lines(path)
    if total is None:
        return True
    return limit >= total


def render_allow() -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }
    )


def render_deny(missing_names: List[str], missing_paths: List[str], target: str) -> str:
    missing_list = ", ".join(missing_names)
    missing_full = ", ".join(missing_paths)
    reason = (
        f"[rule-guard] 写入被拦截：{missing_list} 未在本会话中读取。"
        f"rule-guard blocked write to '{target}'. "
        f"Missing: {missing_list}. "
        f"Read {missing_full} first."
    )
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        ensure_ascii=False,
    )


def render_unknown_log() -> str:
    return render_allow()
