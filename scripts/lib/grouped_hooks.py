"""Merge nested PreToolUse / Stop hooks for Claude and Codex.

Claude writes `.claude/settings.json`. Codex writes `.codex/hooks.json`.
Both nest handlers at hooks.<Event>[].hooks[].command.
"""
from __future__ import annotations

import json
from pathlib import Path

_ENTRY_NEEDLE = "rule-guard/scripts/entry"
_CHIME_NEEDLE = "play_chime"


def _handler(command: str) -> dict:
    return {"type": "command", "command": command, "timeout": 5}


def _group(command: str, matcher: str | None) -> dict:
    group: dict = {"hooks": [_handler(command)]}
    if matcher:
        group["matcher"] = matcher
    return group


def _strip_command(groups: list, needle: str) -> list:
    kept: list = []
    for group in groups:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            kept.append(group)
            continue
        remaining = [
            hook
            for hook in hooks
            if not (
                isinstance(hook, dict)
                and needle in str(hook.get("command", ""))
            )
        ]
        if not remaining:
            continue
        if len(remaining) == len(hooks):
            kept.append(group)
            continue
        updated = dict(group)
        updated["hooks"] = remaining
        kept.append(updated)
    return kept


def _merge(path: Path, pre_matcher: str, entry: str, chime: str) -> str:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    data["hooks"] = hooks

    pre = hooks.get("PreToolUse")
    pre_groups = _strip_command(pre if isinstance(pre, list) else [], _ENTRY_NEEDLE)
    hooks["PreToolUse"] = [_group(entry, pre_matcher)] + pre_groups

    stop = hooks.get("Stop")
    stop_groups = _strip_command(stop if isinstance(stop, list) else [], _CHIME_NEEDLE)
    hooks["Stop"] = stop_groups + [_group(chime, None)]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(path)


def merge_claude_hooks() -> str:
    scripts = "~/.claude/skills/lulu-rule-guard/scripts"
    return _merge(
        Path(".claude/settings.json"),
        "Read|Write|Edit|Bash|PowerShell",
        f"python3 {scripts}/entry.py --platform claude",
        f"python3 {scripts}/play_chime.py --platform claude",
    )


def merge_codex_hooks() -> str:
    scripts = "~/.agents/skills/lulu-rule-guard/scripts"
    return _merge(
        Path(".codex/hooks.json"),
        "Bash|apply_patch|read_file",
        f"python3 {scripts}/entry.py --platform codex",
        f"python3 {scripts}/play_chime.py --platform codex",
    )
