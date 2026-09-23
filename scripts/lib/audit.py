from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def append_write_log(
    log_path: Path, decision: str, target: str, session_id: str, missing: str
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{decision}] {target} sid={session_id} missing={missing}\n"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
