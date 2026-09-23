#!/usr/bin/env python3
"""Emit platform context JSON for session bootstrap."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.platform import PlatformDetectionError, resolve_platform_context


def main() -> int:
    try:
        payload = resolve_platform_context(script_path=Path(__file__).resolve())
    except PlatformDetectionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
