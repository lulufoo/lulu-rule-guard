#!/usr/bin/env python3
"""Cursor platform adapter for rule-guard.

Cursor hook payload fields:
  preToolUse     : hook_event_name="preToolUse", tool_name=Read|Write|Edit|Shell
  session key    : conversation_id
  file path keys : file_path (Write/Edit), path (Read), command (Shell)
  Read offset/limit: offset, limit (line-based)
  deny format    : {"permission": "deny", "user_message": "...", "agent_message": "..."}
  allow format   : {"permission": "allow"}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from lib.state import count_lines

READ_TOOLS = {"Read"}
WRITE_TOOLS = {"Write", "Edit"}
SHELL_TOOLS = {"Shell"}


@dataclass
class ParsedEvent:
    session_id: str
    event_type: str   # "preToolUse" | "unknown"
    action: str       # "read" | "write" | "shell" | "unknown"
    path: str
    command: str
    tool_input: dict


def parse(payload: dict) -> ParsedEvent:
    session_id = (payload.get("conversation_id") or "unknown").strip() or "unknown"
    event_type = payload.get("hook_event_name") or ""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if event_type == "preToolUse":
        if tool_name in READ_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("path") or ""
            return ParsedEvent(
                session_id=session_id,
                event_type="preToolUse",
                action="read",
                path=path,
                command="",
                tool_input=tool_input,
            )
        if tool_name in WRITE_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("path") or ""
            return ParsedEvent(
                session_id=session_id,
                event_type="preToolUse",
                action="write",
                path=path,
                command="",
                tool_input=tool_input,
            )
        if tool_name in SHELL_TOOLS:
            command = tool_input.get("command") or ""
            return ParsedEvent(
                session_id=session_id,
                event_type="preToolUse",
                action="shell",
                path="",
                command=str(command),
                tool_input=tool_input,
            )

    return ParsedEvent(
        session_id=session_id,
        event_type=event_type,
        action="unknown",
        path="",
        command="",
        tool_input=tool_input,
    )


def is_full_read(tool_input: dict) -> bool:
    """True if the Cursor Read tool call covers the entire file."""
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")

    if offset is not None and isinstance(offset, int) and offset > 0:
        return False

    if limit is None:
        return True

    if not isinstance(limit, int):
        return True

    path = tool_input.get("file_path") or tool_input.get("path") or ""
    total = count_lines(path)
    if total is None:
        return True

    return limit >= total


def render_allow() -> str:
    return json.dumps({"permission": "allow"})


def render_deny(missing_names: List[str], missing_paths: List[str], target: str) -> str:
    missing_list = ", ".join(missing_names)
    missing_full = ", ".join(missing_paths)
    return json.dumps(
        {
            "permission": "deny",
            "user_message": (
                f"[rule-guard] 写入被拦截：{missing_list} 未在本会话中读取。"
                "请先 Read 该规则文档。"
            ),
            "agent_message": (
                f"rule-guard blocked write to '{target}'. "
                f"Missing: {missing_list}. "
                f"Read {missing_full} first."
            ),
        },
        ensure_ascii=False,
    )


def render_unknown_log() -> str:
    return render_allow()
