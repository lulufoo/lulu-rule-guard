"""Platform detection for lulu-rule-guard.

Precedence: call override, then LULU_PLATFORM, then runtime signals, else cursor.
Signals, first match: Copilot, Cursor, Claude, Codex.
Codex matches CODEX_THREAD_ID or CODEX_SESSION_ID, which Codex injects into shell commands.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from config_util import cache_root, config_root

SUPPORTED_PLATFORMS = ("cursor", "copilot", "claude", "codex")


class PlatformDetectionError(Exception):
    """Raised when the platform value is unsupported, or strict detection misses."""


def _normalize_platform(value: str) -> str:
    plat = value.strip().lower()
    if plat not in SUPPORTED_PLATFORMS:
        raise PlatformDetectionError(f"unsupported platform: {value!r}")
    return plat


def _signal_platform() -> Optional[str]:
    if os.environ.get("VSCODE_TARGET_SESSION_LOG") or os.environ.get("COPILOT_AGENT") == "1":
        return "copilot"
    if os.environ.get("CURSOR_AGENT"):
        return "cursor"
    if os.environ.get("CLAUDE_CODE"):
        return "claude"
    if os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID"):
        return "codex"
    return None


def detect_platform(*, override: Optional[str] = None, strict: bool = False) -> str:
    """Detect the active platform."""
    if override:
        return _normalize_platform(override)

    lulu_platform = os.environ.get("LULU_PLATFORM")
    if lulu_platform:
        return _normalize_platform(lulu_platform)

    detected = _signal_platform()
    if detected:
        return detected

    if strict:
        raise PlatformDetectionError("No platform signal matched.")
    return "cursor"


def resolve_platform_context(
    *,
    script_path: Path,
    override: Optional[str] = None,
) -> dict[str, str]:
    """JSON payload for session bootstrap."""
    plat = detect_platform(override=override, strict=False)
    skill_root = script_path.resolve().parent.parent
    return {
        "platform": plat,
        "skill_root": str(skill_root),
        "rule_guard_dir": config_root(plat).as_posix(),
        "cache_dir": cache_root(plat).as_posix(),
    }
