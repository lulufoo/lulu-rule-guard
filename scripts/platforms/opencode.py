#!/usr/bin/env python3
"""OpenCode platform adapter for rule-guard.

OpenCode plugin payload fields (stdin JSON from the
.opencode/plugins/lulu-rule-guard.ts bridge):
  action      : "read" | "write" | "shell"
  session key : session_id
  file path   : path (read/write), absolute
  command     : command (shell)
  read paging : offset, limit (line-based)
  deny format : "DENY\\t<agent_message>"  (plugin throws to block)
  allow format: "ALLOW"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from lib.state import count_lines


@dataclass
class ParsedEvent:
    session_id: str
    event_type: str   # "tool" | "unknown"
    action: str       # "read" | "write" | "shell" | "unknown"
    path: str
    command: str
    tool_input: dict


def parse(payload: dict) -> ParsedEvent:
    session_id = (payload.get("session_id") or "unknown").strip() or "unknown"
    action = payload.get("action") or ""

    if action == "read":
        path = str(payload.get("path") or "")
        return ParsedEvent(
            session_id=session_id,
            event_type="tool",
            action="read",
            path=path,
            command="",
            tool_input={
                "file_path": path,
                "offset": payload.get("offset"),
                "limit": payload.get("limit"),
            },
        )
    if action == "write":
        path = str(payload.get("path") or "")
        return ParsedEvent(
            session_id=session_id,
            event_type="tool",
            action="write",
            path=path,
            command="",
            tool_input={"file_path": path},
        )
    if action == "shell":
        return ParsedEvent(
            session_id=session_id,
            event_type="tool",
            action="shell",
            path="",
            command=str(payload.get("command") or ""),
            tool_input={},
        )

    return ParsedEvent(
        session_id=session_id,
        event_type="",
        action="unknown",
        path="",
        command="",
        tool_input={},
    )


def is_full_read(tool_input: dict) -> bool:
    """True if the OpenCode read tool call covers the entire file."""
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")

    if offset is not None and isinstance(offset, int) and offset > 0:
        return False

    if limit is None:
        return True

    if not isinstance(limit, int):
        return True

    path = tool_input.get("file_path") or ""
    total = count_lines(path)
    if total is None:
        return True

    return limit >= total


def render_allow() -> str:
    return "ALLOW"


def render_deny(missing_names: List[str], missing_paths: List[str], target: str) -> str:
    missing_list = ", ".join(missing_names)
    missing_full = ", ".join(missing_paths)
    return (
        "DENY\t"
        f"rule-guard blocked write to '{target}'. "
        f"Missing: {missing_list}. "
        f"Read {missing_full} first."
    )


def render_unknown_log() -> str:
    return "ALLOW"
