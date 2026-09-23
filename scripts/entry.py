#!/usr/bin/env python3
"""Unified entry point for rule-guard hooks."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Tuple
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config_util
from guards import GuardOutcome, file_guard, read_tracker
from lib.audit import append_write_log
from lib.rules import parse_rules_list
from lib.shell_targets import get_shell_write_targets

def _load_adapter(platform: str):
    if platform == "copilot":
        from platforms import copilot as adapter
    else:
        from platforms import cursor as adapter
    return adapter

def _read_payload() -> Tuple[dict, str]:
    try:
        raw = sys.stdin.read()
        payload: dict = json.loads(raw) if raw.strip() else {}
        return (payload if isinstance(payload, dict) else {}), ""
    except json.JSONDecodeError as exc:
        return {}, str(exc)
    except Exception as exc:
        return {}, str(exc)

def _write_targets(event) -> list[str]:
    if event.action == "write":
        return [event.path] if event.path.strip() else []
    return get_shell_write_targets(event.command)

def main() -> int:
    parser = argparse.ArgumentParser(description="rule-guard hook entry point")
    parser.add_argument("--platform", default="cursor", choices=["cursor", "copilot"])
    platform = parser.parse_args().platform
    adapter = _load_adapter(platform)
    payload, parse_error = _read_payload()
    if parse_error:
        print(adapter.render_deny(["payload-parse-error"], [parse_error], "stdin"))
        return 0
    event = adapter.parse(payload)
    cfg = config_util.load_config(platform)
    rules = parse_rules_list(cfg.file_guard.rules).rules
    state_root = config_util.rules_state_root(platform)
    write_log = config_util.write_decisions_log(platform)
    if event.action == "read":
        if cfg.file_guard.enabled:
            out = read_tracker.handle(
                event,
                rules=rules,
                state_root=state_root,
                adapter=adapter,
            )
        else:
            out = GuardOutcome(0, adapter.render_allow())
        print(out.stdout)
        return out.returncode
    if event.action in ("write", "shell"):
        targets = _write_targets(event)
        if not targets:
            print(adapter.render_allow())
            return 0
        if cfg.file_guard.enabled:
            out = file_guard.check(
                targets,
                rules=parse_rules_list(cfg.file_guard.rules),
                session_id=event.session_id,
                state_root=state_root,
                write_log=write_log,
                adapter=adapter,
            )
        else:
            out = GuardOutcome(0, adapter.render_allow())
        print(out.stdout)
        return out.returncode
    if payload.get("tool_name"):
        append_write_log(write_log, "unknown-tool", payload["tool_name"], event.session_id, "")
    print(adapter.render_unknown_log())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
