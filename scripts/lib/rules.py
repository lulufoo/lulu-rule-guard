from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Set

KNOWN_NO_EXT = {"Makefile", "Dockerfile", "Jenkinsfile", "Procfile", "Vagrantfile"}
SKIP_PREFIXES = ("/tmp/", "/var/", "/private/tmp/", "/dev/")


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class Rule:
    glob: str
    required: List[str] = field(default_factory=list)


@dataclass
class RulesFile:
    rules: List[Rule] = field(default_factory=list)


# ── Glob matching ──────────────────────────────────────────────────────────────


def _expand_braces(pattern: str) -> List[str]:
    m = re.search(r"\{([^{}]+)\}", pattern)
    if not m:
        return [pattern]
    prefix = pattern[: m.start()]
    suffix = pattern[m.end():]
    results: List[str] = []
    for alt in m.group(1).split(","):
        results.extend(_expand_braces(prefix + alt + suffix))
    return results


def _matches_glob(path: str, glob: str) -> bool:
    full = path
    base = Path(path).name
    rel = path.lstrip("/")
    for pat in _expand_braces(glob):
        if fnmatch(full, pat) or fnmatch(base, pat) or fnmatch(rel, pat):
            return True
        if pat.startswith("**/"):
            simple = pat[3:]
            if fnmatch(base, simple) or fnmatch(full, simple):
                return True
    return False


def _should_skip(path: str) -> bool:
    stripped = path.strip()
    if not stripped:
        return True
    for prefix in SKIP_PREFIXES:
        if stripped.startswith(prefix):
            return True
    p = Path(stripped)
    if not p.suffix and p.name not in KNOWN_NO_EXT:
        return True
    return False


# ── Loading ────────────────────────────────────────────────────────────────────


def parse_rules_list(raw_rules: object) -> RulesFile:
    if not isinstance(raw_rules, list):
        return RulesFile()
    rules = []
    for r in raw_rules:
        if not isinstance(r, dict):
            continue
        glob = r.get("glob") or ""
        required = r.get("required") or []
        if isinstance(required, list):
            rules.append(Rule(glob=glob, required=[str(x) for x in required if x]))
    return RulesFile(rules=rules)


# ── Query helpers ──────────────────────────────────────────────────────────────


def required_docs_for(file_path: str, rules: List[Rule]) -> List[str]:
    required: List[str] = []
    seen: set = set()
    for rule in rules:
        if not rule.glob:
            continue
        if _matches_glob(file_path, rule.glob):
            for doc in rule.required:
                if doc not in seen:
                    seen.add(doc)
                    required.append(doc)
    return required


def required_set_from_rules(rules: List[Rule]) -> Set[str]:
    result: Set[str] = set()
    for rule in rules:
        for doc in rule.required:
            if doc:
                result.add(doc)
    return result
