#!/usr/bin/env python3
"""Codex platform adapter for rule-guard.

PreToolUse input (https://developers.openai.com/codex/hooks):
  hook_event_name : "PreToolUse"
  session_id      : session identifier
  tool_name       : Bash | apply_patch | read_file | ...
  tool_input      : command for Bash and apply_patch; file_path, offset, limit for read_file
  deny format     : hookSpecificOutput.permissionDecision = deny

apply_patch file headers (codex apply_patch grammar):
  *** Add File: <path>
  *** Update File: <path>
  *** Delete File: <path>
  *** Move to: <path>
"""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List

from lib.shell_targets import get_shell_write_targets
from lib.state import count_lines

_FILE_HEADER = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$")
_MOVE_TO = re.compile(r"^\*\*\* Move to: (.+?)\s*$")


@dataclass
class ParsedEvent:
    session_id: str
    event_type: str
    action: str
    path: str
    command: str
    tool_input: dict


def cat_read_paths(command: str) -> List[str]:
    """Paths from a bare `cat file...` command. Flags, pipes, and redirects are not reads."""
    if re.search(r"[|&;<>()]", command):
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if not tokens or Path(tokens[0]).name != "cat":
        return []
    paths: List[str] = []
    for token in tokens[1:]:
        if token.startswith("-"):
            return []
        paths.append(token)
    return paths


def patch_paths(command: str) -> List[str]:
    paths: List[str] = []
    seen: set[str] = set()
    for line in command.splitlines():
        match = _FILE_HEADER.match(line) or _MOVE_TO.match(line)
        if not match:
            continue
        path = match.group(1).strip()
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def parse(payload: dict) -> ParsedEvent:
    session_id = (payload.get("session_id") or "unknown").strip() or "unknown"
    event_type = payload.get("hook_event_name") or ""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if event_type != "PreToolUse":
        return ParsedEvent(session_id, event_type, "unknown", "", "", tool_input)

    command = tool_input.get("command") or ""
    command = command if isinstance(command, str) else str(command)

    if tool_name == "read_file":
        path = tool_input.get("file_path") or ""
        path = path if isinstance(path, str) else ""
        return ParsedEvent(session_id, event_type, "read", path, "", tool_input)
    if tool_name == "Bash":
        if not get_shell_write_targets(command):
            reads = cat_read_paths(command)
            if reads:
                return ParsedEvent(
                    session_id,
                    event_type,
                    "read",
                    "\n".join(reads),
                    command,
                    tool_input,
                )
        return ParsedEvent(session_id, event_type, "shell", "", command, tool_input)
    if tool_name == "apply_patch":
        paths = patch_paths(command)
        return ParsedEvent(
            session_id,
            event_type,
            "write",
            "\n".join(paths),
            command,
            tool_input,
        )

    return ParsedEvent(session_id, event_type, "unknown", "", "", tool_input)


def is_full_read(tool_input: dict) -> bool:
    """read_file offset is 1-based. A bare cat has no offset or limit."""
    if tool_input.get("mode") == "indentation":
        return False
    offset = tool_input.get("offset")
    if isinstance(offset, int) and offset != 1:
        return False
    limit = tool_input.get("limit")
    if not isinstance(limit, int):
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


def render_unparsed_write() -> str:
    reason = (
        "[rule-guard] 写入被拦截：apply_patch 里没有文件路径。"
        "rule-guard blocked apply_patch because the patch has no file path."
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
