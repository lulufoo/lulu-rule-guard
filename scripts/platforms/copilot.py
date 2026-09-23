#!/usr/bin/env python3
"""VS Code Copilot platform adapter for rule-guard.

Copilot hook payload fields (PreToolUse):
  hook_event_name : "PreToolUse"  (snake_case)
  session_id      : "<session-id>"  (snake_case)
  tool_name     : snake_case — create_file, replace_string_in_file,
                               multi_replace_string_in_file, read_file,
                               run_in_terminal, file_search, grep_search,
                               semantic_search, list_dir, ...
  tool_input    : camelCase keys — filePath, content, oldString, newString, command
                  read_file range: startLine, endLine (1-based, inclusive)
  deny format   : {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "..."}}
  allow format  : {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "allow"}}

Reference: https://code.visualstudio.com/docs/copilot/customization/hooks
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from lib.state import count_lines

# Confirmed tool names (hooks FAQ + observed tool calls in VS Code Copilot agent).
# Unknown tools → allow + log; add to the appropriate set once confirmed.
READ_TOOLS = {
    "read_file",
    "file_search",
    "grep_search",
    "semantic_search",
    "list_dir",
}
WRITE_TOOLS = {
    "create_file",
    "replace_string_in_file",
    "multi_replace_string_in_file",
}
SHELL_TOOLS = {
    "run_in_terminal",
}


@dataclass
class ParsedEvent:
    session_id: str
    event_type: str   # "PreToolUse" | "unknown"
    action: str       # "read" | "write" | "shell" | "unknown"
    path: str
    command: str
    tool_input: dict


def parse(payload: dict) -> ParsedEvent:
    session_id = (payload.get("session_id") or payload.get("sessionId") or "unknown").strip() or "unknown"
    hook_event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if hook_event != "PreToolUse":
        return ParsedEvent(
            session_id=session_id,
            event_type=hook_event,
            action="unknown",
            path="",
            command="",
            tool_input=tool_input,
        )

    if tool_name in READ_TOOLS:
        path = tool_input.get("filePath") or tool_input.get("file_path") or ""
        return ParsedEvent(
            session_id=session_id,
            event_type="PreToolUse",
            action="read",
            path=path,
            command="",
            tool_input=tool_input,
        )

    if tool_name in WRITE_TOOLS:
        path = tool_input.get("filePath") or tool_input.get("file_path") or ""
        return ParsedEvent(
            session_id=session_id,
            event_type="PreToolUse",
            action="write",
            path=path,
            command="",
            tool_input=tool_input,
        )

    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command") or ""
        return ParsedEvent(
            session_id=session_id,
            event_type="PreToolUse",
            action="shell",
            path="",
            command=str(command),
            tool_input=tool_input,
        )

    # Unknown tool — allow + let entry.py log it.
    return ParsedEvent(
        session_id=session_id,
        event_type="PreToolUse",
        action="unknown",
        path="",
        command="",
        tool_input=tool_input,
    )


def is_full_read(tool_input: dict) -> bool:
    """True if the Copilot read_file call covers the entire file.

    Copilot uses startLine/endLine (1-based, inclusive) instead of offset/limit.
    No range fields present → full read assumed.
    """
    start = tool_input.get("startLine")
    end = tool_input.get("endLine")

    if start is None and end is None:
        return True

    if not isinstance(start, int) or not isinstance(end, int):
        return True  # Can't determine range — treat as full read

    if start > 1:
        return False  # Starts past first line → partial

    path = tool_input.get("filePath") or tool_input.get("file_path") or ""
    total = count_lines(path)
    if total is None:
        return True  # Can't count lines — treat as full read

    return end >= total


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
