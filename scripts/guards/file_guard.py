from __future__ import annotations

from pathlib import Path
from typing import List

from guards import GuardOutcome
from lib.audit import append_write_log
from lib.rules import RulesFile, required_docs_for
from lib.state import check_doc_loaded, cleanup_old_state_dirs


def check(
    targets: List[str],
    *,
    rules: RulesFile,
    session_id: str,
    state_root: Path,
    write_log: Path,
    adapter,
) -> GuardOutcome:
    if not rules.rules:
        return GuardOutcome(0, adapter.render_allow())

    all_missing: list[str] = []
    missing_seen: set = set()
    for target in targets:
        for doc in required_docs_for(target, rules.rules):
            if not check_doc_loaded(doc, session_id, state_root):
                if doc not in missing_seen:
                    missing_seen.add(doc)
                    all_missing.append(doc)

    primary_target = targets[0] if len(targets) == 1 else ", ".join(targets)

    if all_missing:
        decision = "deny"
        missing_names = [Path(d).name for d in all_missing]
        result = adapter.render_deny(missing_names, all_missing, primary_target)
    else:
        decision = "allow"
        result = adapter.render_allow()

    missing_log = ", ".join(Path(d).name for d in all_missing)
    for target in targets:
        append_write_log(write_log, decision, target, session_id, missing_log)

    cleanup_old_state_dirs(state_root)
    return GuardOutcome(0, result)
