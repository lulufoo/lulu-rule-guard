#!/usr/bin/env python3
"""Add a rule markdown to fileGuard.rules from GitHub or a local path."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from config_util import (
    load_config,
    merge_file_guard_rules,
    read_rule_config_document,
    resolve_rules_docs_dir,
    rule_config_path,
    write_file_guard_rules,
)
from lib.github_util import gh_fetch_file, parse_github_url

DEFAULT_FRONTMATTER = """\
---
rule-guard:
  globs:
    - "**/*.{*}"
---

"""


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


def _ensure_frontmatter(text: str) -> str:
    """Prepend default rule-guard frontmatter if the file has none."""
    if re.match(r"^---\s*\n", text):
        return text
    return DEFAULT_FRONTMATTER + text


def _iter_local_md(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*.md") if p.is_file())
    return []


def _project_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


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


def _write_merged(config_file: Path, new_rules: list[dict], *, replace_glob: bool) -> int:
    existing_data = read_rule_config_document(config_file)
    fg = existing_data.get("fileGuard")
    existing_rules = fg.get("rules", []) if isinstance(fg, dict) else []
    if replace_glob:
        merged = _replace_rules_by_glob(existing_rules, new_rules)
    else:
        merged = merge_file_guard_rules(existing_rules, new_rules)
    write_file_guard_rules(config_file, merged)
    return len(merged)


def _register_local(local_path: Path, config_file: Path) -> int:
    files = _iter_local_md(local_path)
    if not files:
        print(f"[add-guard-rule] no .md files at {local_path.as_posix()}", file=sys.stderr)
        return 1
    new_rules: list[dict] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        globs = _parse_frontmatter_globs(text)
        if not globs:
            print(f"[add-guard-rule] skip (no rule-guard.globs): {path.as_posix()}")
            continue
        doc_path = _project_rel(path)
        for glob in globs:
            new_rules.append({"glob": glob, "required": [doc_path]})
            print(f"  + {glob} -> {doc_path}")
    if not new_rules:
        print("[add-guard-rule] no local files with rule-guard.globs", file=sys.stderr)
        return 1
    total = _write_merged(config_file, new_rules, replace_glob=True)
    print(
        f"[add-guard-rule] updated {config_file.as_posix()} "
        f"fileGuard.rules ({total} total rule(s))"
    )
    return 0


def _register_github(source_url: str, path_prefix: str, config_file: Path) -> int:
    try:
        owner, repo, ref, path = parse_github_url(source_url)
    except ValueError as exc:
        print(f"[add-guard-rule] {exc}", file=sys.stderr)
        return 1

    filename = Path(path).name
    if not filename.endswith(".md"):
        print(
            f"[add-guard-rule] source URL must point to a .md file, got: {filename!r}",
            file=sys.stderr,
        )
        return 1

    print(f"[add-guard-rule] fetching {owner}/{repo} @ {ref}: {path}")
    try:
        raw = gh_fetch_file(owner, repo, ref, path)
    except RuntimeError as exc:
        print(f"[add-guard-rule] {exc}", file=sys.stderr)
        return 1

    text = _ensure_frontmatter(raw.decode("utf-8"))
    globs = _parse_frontmatter_globs(text)
    if not globs:
        print(
            "[add-guard-rule] warning: no rule-guard.globs in frontmatter after injection; "
            "using default glob",
            file=sys.stderr,
        )
        globs = ["**/*.{*}"]

    docs_dir = Path(path_prefix)
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / filename
    dest.write_text(text, encoding="utf-8")
    print(f"[add-guard-rule] saved  {dest.as_posix()}")

    doc_path = f"{path_prefix.rstrip('/')}/{filename}"
    new_rules = [{"glob": g, "required": [doc_path]} for g in globs]
    total = _write_merged(config_file, new_rules, replace_glob=False)
    print(
        f"[add-guard-rule] updated {config_file.as_posix()} "
        f"fileGuard.rules ({total} total rule(s))"
    )
    for r in new_rules:
        print(f"  + {r['glob']} -> {r['required'][0]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add a rule markdown to fileGuard.rules from GitHub or a local path"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--source-url",
        dest="source_url",
        help=(
            "GitHub URL of the rule markdown "
            "(https://github.com/owner/repo/blob/ref/path, "
            "github:owner/repo@ref/path, or github:owner/repo/ref/path)"
        ),
    )
    source.add_argument(
        "--local",
        dest="local",
        help="Local .md file or directory (register only; no copy)",
    )
    parser.add_argument(
        "--rules-docs-dir",
        dest="rules_docs_dir",
        default=None,
        help=(
            "Directory for rule markdown files; overrides fileGuard.rulesDocsDir "
            "for this invocation (GitHub source only)"
        ),
    )
    args = parser.parse_args(argv)

    cfg = load_config()
    config_file = rule_config_path(cfg)

    if args.local:
        local_path = Path(args.local)
        if not local_path.exists():
            print(f"[add-guard-rule] local path not found: {args.local}", file=sys.stderr)
            return 1
        return _register_local(local_path, config_file)

    path_prefix = resolve_rules_docs_dir(cfg, args.rules_docs_dir)
    print(f"[add-guard-rule] rulesDocsDir: {path_prefix}")
    return _register_github(args.source_url, path_prefix, config_file)


if __name__ == "__main__":
    raise SystemExit(main())
