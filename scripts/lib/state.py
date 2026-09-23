from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Set


def resolve_rule_path(path: str) -> Path:
    """Absolute path with symlinks followed."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def read_state_file(session_id: str, path: str, state_root: Path) -> Path:
    """State file keyed by the resolved rule path, not its basename."""
    try:
        identity = resolve_rule_path(path).as_posix()
    except OSError:
        identity = path
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return state_root / session_id / f"{digest}.json"


def check_doc_loaded(doc: str, session_id: str, state_root: Path) -> bool:
    try:
        state_file = read_state_file(session_id, doc, state_root)
        if not state_file.exists():
            return False
        state_file.read_text(encoding="utf-8")
        return True
    except OSError:
        return False


def write_read_state(session_id: str, path: str, state_root: Path) -> None:
    now = datetime.now(timezone.utc)
    state_file = read_state_file(session_id, path, state_root)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"read_at": now.isoformat(), "path": path}
    try:
        state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def cleanup_old_state_dirs(state_root: Path) -> None:
    try:
        if not state_root.exists():
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for d in state_root.iterdir():
            if not d.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    shutil.rmtree(str(d), ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


def count_lines(path: str) -> Optional[int]:
    try:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path.cwd() / resolved
        text = resolved.read_text(encoding="utf-8", errors="replace")
        return len(text.splitlines())
    except OSError:
        return None


def is_rule_doc_path(path: str, required_set: Set[str]) -> bool:
    if not required_set:
        return False
    try:
        got = resolve_rule_path(path)
    except OSError:
        return False
    for required in required_set:
        try:
            if resolve_rule_path(required) == got:
                return True
        except OSError:
            continue
    return False
