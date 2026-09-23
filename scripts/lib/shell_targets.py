from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import List

from lib.rules import _should_skip


def _find_redirects(tokens: List[str]) -> List[str]:
    results: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in (">", ">>"):
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("&"):
                results.append(tokens[i + 1])
            i += 2
        else:
            m = re.match(r"^>>?([^&&\s].+)$", t)
            if m:
                results.append(m.group(1))
            i += 1
    return results


def _extract_targets(command: str) -> List[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []

    if not tokens:
        return []

    targets: List[str] = []
    cmd0 = Path(tokens[0]).name

    targets.extend(_find_redirects(tokens))

    for i, t in enumerate(tokens):
        if Path(t).name == "tee":
            for rt in tokens[i + 1:]:
                if rt.startswith("-"):
                    continue
                targets.append(rt)
                break

    if cmd0 == "cp":
        non_flags = [t for t in tokens[1:] if not t.startswith("-")]
        if len(non_flags) >= 2:
            targets.append(non_flags[-1])

    if cmd0 == "mv":
        non_flags = [t for t in tokens[1:] if not t.startswith("-")]
        if len(non_flags) >= 2:
            targets.append(non_flags[-1])

    if cmd0 == "sed":
        has_inline = any(t.startswith("-i") for t in tokens[1:])
        if has_inline:
            skip_next_expr = True
            for t in tokens[1:]:
                if t.startswith("-"):
                    continue
                if skip_next_expr:
                    skip_next_expr = False
                    continue
                targets.append(t)

    seen: set = set()
    result: List[str] = []
    for t in targets:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        if not _should_skip(t):
            result.append(t)
    return result


def get_shell_write_targets(command: str) -> List[str]:
    try:
        return _extract_targets(command)
    except Exception:
        return []
