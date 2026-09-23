#!/usr/bin/env python3
"""lulu-rule-guard CLI entry — list rule-install commands."""
from __future__ import annotations

import argparse
import sys

COMMANDS: tuple[str, ...] = (
    "add-guard-rule",
)


def print_command_list() -> None:
    for index, name in enumerate(COMMANDS, start=1):
        print(f"{index}. {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lulu-rule-guard")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available rule-install commands (numbered)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        help="Subcommand name (or 'list')",
    )
    args = parser.parse_args(argv)

    if args.list or (args.command and args.command.lower() == "list"):
        print_command_list()
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    print(f"[lulu-rule-guard] unknown command: {args.command!r}", file=sys.stderr)
    print("[lulu-rule-guard] run with --list to see available commands.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
