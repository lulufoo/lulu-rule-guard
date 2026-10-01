#!/usr/bin/env python3
"""Initialize rule-guard in the current project.

  python3 init.py --platform cursor
  python3 init.py --platform copilot

Cursor  → .cursor/hooks.json          (preToolUse + stop)
Copilot → .github/hooks/hooks.json    (PreToolUse + Stop)
Claude  → .claude/settings.json       (PreToolUse + Stop)
Codex   → .codex/hooks.json           (PreToolUse + Stop)
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_util import (
    ensure_rule_config,
    logs_dir,
    rules_state_root,
)
from lib.grouped_hooks import merge_claude_hooks, merge_codex_hooks
from lib.platform import PlatformDetectionError, detect_platform

SKILL_ROOT = SCRIPT_DIR.parent
SKILL_README = SKILL_ROOT / "templates" / "README.md"

# ── Cursor hooks ───────────────────────────────────────────────────────────────
CURSOR_HOOKS_PATH = Path(".cursor/hooks.json")
CURSOR_SKILL_SCRIPTS = "~/.agents/skills/lulu-rule-guard/scripts"
CURSOR_ENTRY = f"python3 {CURSOR_SKILL_SCRIPTS}/entry.py --platform cursor"
CURSOR_CHIME = f"python3 {CURSOR_SKILL_SCRIPTS}/play_chime.py --platform cursor"

CURSOR_GUARD_PRE_TOOL_USE = [
    {
        "matcher": "Read|Write|Edit|Shell",
        "command": CURSOR_ENTRY,
        "timeout": 5,
        "failClosed": False,
    },
]
CURSOR_CHIME_STOP = {
    "command": CURSOR_CHIME,
    "timeout": 5,
    "failClosed": False,
}

# ── Copilot hooks ──────────────────────────────────────────────────────────────
COPILOT_HOOKS_PATH = Path(".github/hooks/hooks.json")
COPILOT_SKILL_SCRIPTS = "~/.copilot/skills/lulu-rule-guard/scripts"
COPILOT_ENTRY = f"python3 {COPILOT_SKILL_SCRIPTS}/entry.py --platform copilot"
COPILOT_CHIME = f"python3 {COPILOT_SKILL_SCRIPTS}/play_chime.py --platform copilot"

COPILOT_GUARD_PRE_TOOL_USE = [
    {
        "type": "command",
        "command": COPILOT_ENTRY,
        "timeout": 5,
    },
]
COPILOT_CHIME_STOP = {
    "type": "command",
    "command": COPILOT_CHIME,
    "timeout": 5,
}


# ── Cursor merge helpers ───────────────────────────────────────────────────────

def _is_rule_guard_entry(cmd: str) -> bool:
    return (
        "rule-guard/scripts/entry" in cmd
        or "cursor-rule-guard/scripts/audit-read" in cmd
        or "cursor-rule-guard/scripts/guard-write" in cmd
    )


def _is_prompt_entry(cmd: str) -> bool:
    return "rule-guard/scripts/prompt_entry" in cmd


def _is_chime_command(cmd: str) -> bool:
    c = cmd.lower()
    return "play_chime" in c or "play-chime" in c


def _cursor_merge_pre_tool_use(existing: list) -> list:
    other = [
        e for e in existing
        if not _is_rule_guard_entry(e.get("command", ""))
    ]
    return [deepcopy(e) for e in CURSOR_GUARD_PRE_TOOL_USE] + other


def _cursor_strip_before_read(hooks: dict) -> None:
    """Remove rule-guard entries from beforeReadFile; drop key if empty."""
    before = hooks.get("beforeReadFile")
    if not isinstance(before, list):
        return
    kept = [
        e for e in before
        if not _is_rule_guard_entry(e.get("command", ""))
    ]
    if kept:
        hooks["beforeReadFile"] = kept
    elif "beforeReadFile" in hooks:
        del hooks["beforeReadFile"]


def _cursor_strip_prompt_entry(hooks: dict) -> None:
    """Remove legacy pathGuard prompt_entry; keep other beforeSubmitPrompt hooks."""
    bsp = hooks.get("beforeSubmitPrompt")
    if not isinstance(bsp, list):
        return
    kept = [
        e for e in bsp
        if not _is_prompt_entry(e.get("command", ""))
    ]
    if kept:
        hooks["beforeSubmitPrompt"] = kept
    elif "beforeSubmitPrompt" in hooks:
        del hooks["beforeSubmitPrompt"]


def _cursor_merge_stop(existing: list) -> list:
    kept = [e for e in existing if not _is_chime_command(e.get("command", ""))]
    kept.append(deepcopy(CURSOR_CHIME_STOP))
    return kept


def _strip_chime_from_other_cursor_events(hooks: dict) -> None:
    for event, entries in list(hooks.items()):
        if event == "stop" or not isinstance(entries, list):
            continue
        hooks[event] = [
            e for e in entries if not _is_chime_command(e.get("command", ""))
        ]


def _merge_cursor_hooks() -> str:
    if CURSOR_HOOKS_PATH.exists():
        data = json.loads(CURSOR_HOOKS_PATH.read_text(encoding="utf-8"))
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    data["version"] = 1
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    data["hooks"] = hooks

    _strip_chime_from_other_cursor_events(hooks)

    pre = hooks.get("preToolUse")
    hooks["preToolUse"] = _cursor_merge_pre_tool_use(pre if isinstance(pre, list) else [])

    _cursor_strip_before_read(hooks)

    stop = hooks.get("stop")
    hooks["stop"] = _cursor_merge_stop(stop if isinstance(stop, list) else [])

    _cursor_strip_prompt_entry(hooks)

    for event in list(hooks.keys()):
        entries = hooks.get(event)
        if isinstance(entries, list) and len(entries) == 0:
            del hooks[event]

    CURSOR_HOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_HOOKS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(CURSOR_HOOKS_PATH)


# ── OpenCode plugin ─────────────────────────────────────────────────────────────
OPENCODE_PLUGIN_PATH = Path(".opencode/plugins/lulu-rule-guard.ts")

OPENCODE_PLUGIN_SOURCE = """\
// lulu-rule-guard bridge for OpenCode.
// Managed by `lulu-rule-guard init --platform opencode`.
const ENTRY = "~/.agents/skills/lulu-rule-guard/scripts/entry.py"

export const RuleGuardPlugin = async (ctx: any) => {
  const entry = ENTRY.replace(/^~/, process.env.HOME ?? "")
  // entry.py resolves config and state paths relative to cwd; the GUI server
  // process may run with cwd=$HOME, so pin it to the project directory.
  const cwd: string = ctx?.directory ?? ctx?.project?.directory ?? process.cwd()

  const log = (message: string) => {
    try {
      ctx?.client?.app?.log?.({
        body: { service: "lulu-rule-guard", level: "warn", message },
      })
    } catch {}
  }

  const runViaBun = async (json: string): Promise<string> => {
    const bun = (globalThis as any).Bun
    const proc = bun.spawn(["python3", entry, "--platform", "opencode"], {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      cwd,
    })
    proc.stdin.write(json)
    proc.stdin.end()
    return await new Response(proc.stdout).text()
  }

  const runViaNode = async (json: string): Promise<string> => {
    const cp: any = await import("node:child_process")
    return await new Promise<string>((resolve, reject) => {
      const proc = cp.spawn("python3", [entry, "--platform", "opencode"], { cwd })
      let out = ""
      proc.stdout.on("data", (chunk: any) => {
        out += chunk
      })
      proc.on("error", reject)
      proc.on("close", () => resolve(out))
      proc.stdin.write(json)
      proc.stdin.end()
    })
  }

  const runEntry = async (json: string): Promise<string> => {
    const errors: string[] = []
    if (typeof (globalThis as any).Bun !== "undefined") {
      try {
        return await runViaBun(json)
      } catch (err: any) {
        errors.push("bun:" + String((err && err.message) || err))
      }
    }
    try {
      return await runViaNode(json)
    } catch (err: any) {
      errors.push("node:" + String((err && err.message) || err))
    }
    log("guard runner failed: " + errors.join(" | "))
    throw new Error(errors.join(" | "))
  }

  const guard = async (input: any, output: any): Promise<void> => {
    const sessionId = input.sessionID ?? input.callID ?? "opencode"
    const args = output.args ?? {}
    let payload: Record<string, unknown> | null = null
    if (input.tool === "read") {
      payload = {
        action: "read",
        path: args.filePath,
        session_id: sessionId,
        offset: args.offset,
        limit: args.limit,
      }
    } else if (input.tool === "edit" || input.tool === "write") {
      payload = { action: "write", path: args.filePath, session_id: sessionId }
    } else if (input.tool === "bash") {
      payload = { action: "shell", command: args.command, session_id: sessionId }
    }
    if (payload === null) return

    let stdout = ""
    try {
      stdout = await runEntry(JSON.stringify(payload))
    } catch {
      return
    }
    const decision = stdout.trim().split("\\n").pop() ?? ""
    if (decision.startsWith("DENY")) {
      throw new Error(decision.slice(4).trim() || "blocked by lulu-rule-guard")
    }
  }

  return { "tool.execute.before": guard }
}
"""


def _write_opencode_plugin() -> str:
    if OPENCODE_PLUGIN_PATH.exists():
        existing = OPENCODE_PLUGIN_PATH.read_text(encoding="utf-8")
        if "rule-guard" not in existing:
            raise OSError(
                f"{OPENCODE_PLUGIN_PATH.as_posix()} exists and is not rule-guard managed"
            )
    OPENCODE_PLUGIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENCODE_PLUGIN_PATH.write_text(OPENCODE_PLUGIN_SOURCE, encoding="utf-8")
    return str(OPENCODE_PLUGIN_PATH)


# ── Copilot merge helpers ──────────────────────────────────────────────────────

def _is_copilot_rule_guard_entry(cmd: str) -> bool:
    return "rule-guard/scripts/entry" in cmd


def _copilot_merge_pre_tool_use(existing: list) -> list:
    other = [
        e for e in existing
        if not _is_copilot_rule_guard_entry(e.get("command", ""))
    ]
    return [deepcopy(COPILOT_GUARD_PRE_TOOL_USE[0])] + other


def _copilot_merge_stop(existing: list) -> list:
    kept = [e for e in existing if not _is_chime_command(e.get("command", ""))]
    kept.append(deepcopy(COPILOT_CHIME_STOP))
    return kept


def _merge_copilot_hooks() -> str:
    if COPILOT_HOOKS_PATH.exists():
        data = json.loads(COPILOT_HOOKS_PATH.read_text(encoding="utf-8"))
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    data["version"] = 1
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    data["hooks"] = hooks

    pre = hooks.get("PreToolUse")
    hooks["PreToolUse"] = _copilot_merge_pre_tool_use(
        pre if isinstance(pre, list) else []
    )

    stop = hooks.get("Stop")
    hooks["Stop"] = _copilot_merge_stop(stop if isinstance(stop, list) else [])

    for event in list(hooks.keys()):
        entries = hooks.get(event)
        if isinstance(entries, list) and len(entries) == 0:
            del hooks[event]

    COPILOT_HOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COPILOT_HOOKS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(COPILOT_HOOKS_PATH)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _create_cache_dirs(platform: str) -> None:
    rules_state_root(platform).mkdir(parents=True, exist_ok=True)
    logs_dir(platform).mkdir(parents=True, exist_ok=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize rule-guard in the current project"
    )
    parser.add_argument("--platform", default=None)
    args = parser.parse_args(argv)
    try:
        platform = detect_platform(override=args.platform)
    except PlatformDetectionError as exc:
        print(f"[init] {exc}", file=sys.stderr)
        return 1

    _create_cache_dirs(platform)
    rule_config_file = ensure_rule_config(platform)

    mergers = {
        "cursor": _merge_cursor_hooks,
        "copilot": _merge_copilot_hooks,
        "claude": merge_claude_hooks,
        "codex": merge_codex_hooks,
        "opencode": _write_opencode_plugin,
    }
    try:
        hooks_path = mergers[platform]()
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[init] merge hooks failed: {exc}", file=sys.stderr)
        return 1

    print(f"[init] hooks updated at {hooks_path}")
    print(f"[init] rule-guard ({platform}) initialized")
    print(f"  config: {rule_config_file.as_posix()}")
    print(
        "  next: add glob → rule mappings with add-guard-rule --local <project-path>"
    )
    if SKILL_README.is_file():
        print(f"  docs: {SKILL_README.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
