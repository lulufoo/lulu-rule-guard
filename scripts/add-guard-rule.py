#!/usr/bin/env python3
"""Register a project Markdown file or directory in fileGuard.rules."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from config_util import (
    load_config,
    merge_file_guard_rules,
    read_rule_config_document,
    rule_config_path,
    write_file_guard_rules,
)
from lib.platform import PlatformDetectionError, detect_platform


def _parse_frontmatter_globs(text: str) -> list[str]:
    """Extract rule-guard.globs list from YAML frontmatter."""
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        return []
    fm_body = fm_match.group(1)
    rg_match = re.search(r"^rule-guard:\s*\n((?:[ \t]+.+\n?)*)", fm_body, re.MULTILINE)
    if not rg_match:
        return []
    rg_body = rg_match.group(1)
    globs_match = re.search(r"[ \t]+globs:\s*\n((?:[ \t]+-[ \t]+.+\n?)*)", rg_body)
    if not globs_match:
        return []
    globs_block = globs_match.group(1)
    globs = []
    for line in globs_block.splitlines():
        item_match = re.match(r'[ \t]+-[ \t]+["\']?([^"\']+)["\']?', line)
        if item_match:
            globs.append(item_match.group(1).strip())
    return globs


def _iter_local_md(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*.md") if p.is_file())
    return []


def _project_rel(path: Path) -> str | None:
    """Project-relative posix path. None when the resolved path leaves the project."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return None


def _replace_rules_by_glob(existing: list[dict], new_rules: list[dict]) -> list[dict]:
    new_globs = {r.get("glob") for r in new_rules}
    new_names = {
        Path(p).name for r in new_rules for p in (r.get("required") or [])
    }
    kept = []
    for rule in existing:
        if rule.get("glob") in new_globs:
            continue
        required = rule.get("required") or []
        if any(Path(p).name in new_names for p in required):
            continue
        kept.append(rule)
    return merge_file_guard_rules(kept, new_rules)


def _write_merged(config_file: Path, new_rules: list[dict]) -> int:
    existing_data = read_rule_config_document(config_file)
    fg = existing_data.get("fileGuard")
    existing_rules = fg.get("rules", []) if isinstance(fg, dict) else []
    merged = _replace_rules_by_glob(existing_rules, new_rules)
    write_file_guard_rules(config_file, merged)
    return len(merged)


def _register_local(local_path: Path, config_file: Path) -> int:
    if _project_rel(local_path) is None:
        print(
            f"[add-guard-rule] path is outside the project: {local_path.as_posix()}",
            file=sys.stderr,
        )
        return 1
    files = _iter_local_md(local_path)
    if not files:
        print(f"[add-guard-rule] no .md files at {local_path.as_posix()}", file=sys.stderr)
        return 1
    new_rules: list[dict] = []
    for path in files:
        doc_path = _project_rel(path)
        if doc_path is None:
            print(f"[add-guard-rule] skip (outside the project): {path.as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        globs = _parse_frontmatter_globs(text)
        if not globs:
            print(f"[add-guard-rule] skip (no rule-guard.globs): {path.as_posix()}")
            continue
        for glob in globs:
            new_rules.append({"glob": glob, "required": [doc_path]})
            print(f"  + {glob} -> {doc_path}")
    if not new_rules:
        print("[add-guard-rule] no local files with rule-guard.globs", file=sys.stderr)
        return 1
    total = _write_merged(config_file, new_rules)
    print(
        f"[add-guard-rule] updated {config_file.as_posix()} "
        f"fileGuard.rules ({total} total rule(s))"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Register a project Markdown file or directory in fileGuard.rules"
    )
    parser.add_argument(
        "--local",
        dest="local",
        required=True,
        help="Project .md file or directory (register only; no copy)",
    )
    args = parser.parse_args(argv)

    try:
        platform = detect_platform()
    except PlatformDetectionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    cfg = load_config(platform)
    config_file = rule_config_path(cfg)

    local_path = Path(args.local)
    if not local_path.exists():
        print(f"[add-guard-rule] local path not found: {args.local}", file=sys.stderr)
        return 1
    return _register_local(local_path, config_file)


if __name__ == "__main__":
    raise SystemExit(main())
