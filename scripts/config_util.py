#!/usr/bin/env python3
"""Shared config loading for rule-guard scripts — platform-aware.

Project config root is $RULE_GUARD_DIR. Pointer config.json and
skill-config/lulu-rule-guard/ are ignored.

Platform path layout:
  cursor  config : .cursor/skills/lulu-rule-guard/rule-guard-config.json
          cache  : .cache/cursor/lulu-rule-guard/
  copilot config : .github/lulu-rule-guard/rule-guard-config.json
          cache  : .cache/copilot/lulu-rule-guard/
"""
from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

_RULE_CONFIG_FILENAME = "rule-guard-config.json"
_LEGACY_RULES_FILENAME = "rule-guard.json"

DEFAULT_RULES_FILE = ".cursor/skills/lulu-rule-guard/rule-guard.json"
DEFAULT_RULE_CONFIG_FILE = ".cursor/skills/lulu-rule-guard/rule-guard-config.json"


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class ChimeSettings:
    enabled: bool = False
    sound: str = "/System/Library/Sounds/Funk.aiff"
    volume: float = 1.0
    gain: int = 25


@dataclass
class FileGuardConfig:
    enabled: bool = True
    rules_docs_dir: str = "docs"
    rules: List[dict] = field(default_factory=list)


@dataclass
class RuntimeConfig:
    version: int = 2
    chime: ChimeSettings = field(default_factory=ChimeSettings)
    file_guard: FileGuardConfig = field(default_factory=FileGuardConfig)


@dataclass
class LoadedConfig:
    rule_config: str
    chime: ChimeSettings
    file_guard: FileGuardConfig = field(default_factory=FileGuardConfig)
    legacy_rules_file: str = DEFAULT_RULES_FILE


# ── Platform-specific paths ────────────────────────────────────────────────────


def config_root(platform: str = "cursor") -> Path:
    if platform == "copilot":
        return Path(".github/lulu-rule-guard")
    return Path(".cursor/skills/lulu-rule-guard")


def config_path(platform: str = "cursor") -> Path:
    return config_root(platform) / _RULE_CONFIG_FILENAME


def legacy_rules_path(platform: str = "cursor") -> Path:
    return config_root(platform) / _LEGACY_RULES_FILENAME


def cache_root(platform: str = "cursor") -> Path:
    return Path(f".cache/{platform}/lulu-rule-guard")


# ── Backward-compat module-level names (default cursor) ───────────────────────
CONFIG_PATH = config_path("cursor")
CACHE_ROOT = cache_root("cursor")


# ── Config loading ─────────────────────────────────────────────────────────────


def _parse_rules_docs_dir(raw: object, default: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return default
    path = raw.strip().rstrip("/")
    if os.path.isabs(path):
        warnings.warn(
            f"rulesDocsDir: absolute path {raw.strip()!r} is not allowed; using default.",
            stacklevel=4,
        )
        return default
    return path


def _parse_bool(raw: object, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return bool(raw)


def _parse_chime(raw: object, *, legacy_enabled: bool | None = None) -> ChimeSettings:
    defaults = ChimeSettings()
    if not isinstance(raw, dict):
        enabled = legacy_enabled if legacy_enabled is not None else defaults.enabled
        return ChimeSettings(enabled=enabled)
    if "enabled" in raw:
        enabled = _parse_bool(raw.get("enabled"), defaults.enabled)
    elif legacy_enabled is not None:
        enabled = legacy_enabled
    else:
        enabled = defaults.enabled
    return ChimeSettings(
        enabled=enabled,
        sound=raw.get("sound", defaults.sound),
        volume=float(raw.get("volume", defaults.volume)),
        gain=int(raw.get("gain", defaults.gain)),
    )


def _parse_rule_dicts(raw_rules: object) -> List[dict]:
    if not isinstance(raw_rules, list):
        return []
    rules: List[dict] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        glob = item.get("glob") or ""
        required = item.get("required") or []
        if not isinstance(required, list):
            required = []
        rules.append(
            {
                "glob": str(glob),
                "required": [str(x) for x in required if x],
            }
        )
    return rules


def parse_file_guard(
    raw: object,
    *,
    legacy_rules_docs_dir: object | None = None,
) -> FileGuardConfig:
    defaults = FileGuardConfig()
    if isinstance(raw, bool):
        return FileGuardConfig(enabled=raw, rules=[])
    if not isinstance(raw, dict):
        if legacy_rules_docs_dir is not None:
            return FileGuardConfig(
                rules_docs_dir=_parse_rules_docs_dir(
                    legacy_rules_docs_dir, defaults.rules_docs_dir
                ),
            )
        return defaults
    rules_docs_dir = defaults.rules_docs_dir
    if "rulesDocsDir" in raw:
        rules_docs_dir = _parse_rules_docs_dir(raw.get("rulesDocsDir"), defaults.rules_docs_dir)
    elif legacy_rules_docs_dir is not None:
        rules_docs_dir = _parse_rules_docs_dir(
            legacy_rules_docs_dir, defaults.rules_docs_dir
        )
    return FileGuardConfig(
        enabled=_parse_bool(raw.get("enabled"), defaults.enabled),
        rules_docs_dir=rules_docs_dir,
        rules=_parse_rule_dicts(raw.get("rules")),
    )


def _load_legacy_rules_file(path_str: str) -> List[dict]:
    try:
        p = Path(path_str)
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _parse_rule_dicts(data.get("rules"))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return []


def _default_rule_config_payload() -> dict:
    return {
        "version": 2,
        "fileGuard": {"enabled": True, "rulesDocsDir": "docs", "rules": []},
    }


def ensure_rule_config(platform: str = "cursor") -> Path:
    """Write missing $RULE_GUARD_DIR/rule-guard-config.json from the init default.

    Does not overwrite an existing project file. Creates parent dirs.
    Migrates $RULE_GUARD_DIR/rule-guard.json when fileGuard.rules is empty.
    """
    dest = config_path(platform)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(
            json.dumps(_default_rule_config_payload(), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    data = read_rule_config_document(dest)
    fg = data.get("fileGuard")
    if not isinstance(fg, dict) or "rules" not in fg:
        write_file_guard_rules(dest, fg.get("rules") if isinstance(fg, dict) else [])
    migrate_legacy_rules_file(dest, legacy_rules_path(platform))
    return dest


def load_runtime_config(path: str, *, legacy_rules_file: str | None = None) -> RuntimeConfig:
    defaults = RuntimeConfig()
    p = Path(path)
    if not p.exists():
        rt = defaults
        if legacy_rules_file:
            legacy_rules = _load_legacy_rules_file(legacy_rules_file)
            if legacy_rules:
                rt.file_guard.rules = legacy_rules
        return rt
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults
        legacy_enabled = None
        if "chimeEnabled" in data:
            legacy_enabled = _parse_bool(data.get("chimeEnabled"))
        chime = _parse_chime(data.get("chime"), legacy_enabled=legacy_enabled)
        file_guard = parse_file_guard(
            data.get("fileGuard"),
            legacy_rules_docs_dir=data.get("rulesDocsDir"),
        )
        if not file_guard.rules and legacy_rules_file:
            legacy_rules = _load_legacy_rules_file(legacy_rules_file)
            if legacy_rules:
                file_guard.rules = legacy_rules
        return RuntimeConfig(
            version=int(data.get("version", defaults.version)),
            chime=chime,
            file_guard=file_guard,
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return defaults


def load_config(platform: str = "cursor") -> LoadedConfig:
    """Load runtime settings from $RULE_GUARD_DIR/rule-guard-config.json.

    Missing project file → in-memory defaults.
    Leftover pointer config.json and skill-config/lulu-rule-guard/ are ignored.
    Legacy $RULE_GUARD_DIR/rule-guard.json fills empty fileGuard.rules.
    """
    dest = config_path(platform)
    legacy = legacy_rules_path(platform)
    legacy_str = str(legacy) if legacy.exists() else None
    rt = load_runtime_config(str(dest), legacy_rules_file=legacy_str)
    return LoadedConfig(
        rule_config=dest.as_posix(),
        chime=rt.chime,
        file_guard=rt.file_guard,
        legacy_rules_file=legacy.as_posix(),
    )


# ── Entity 2 read/write helpers ────────────────────────────────────────────────


def rule_config_path(cfg: LoadedConfig) -> Path:
    return Path(cfg.rule_config)


def read_rule_config_document(path: Path) -> dict:
    if not path.exists():
        return {"version": 2}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 2}
    except (json.JSONDecodeError, OSError):
        return {"version": 2}


def write_file_guard_rules(
    config_path: Path,
    rules: List[dict],
    *,
    enabled: bool | None = None,
) -> None:
    """Read-modify-write Entity 2, updating fileGuard.rules only."""
    data = read_rule_config_document(config_path)
    fg = data.get("fileGuard")
    if not isinstance(fg, dict):
        fg = {}
    fg["rules"] = _parse_rule_dicts(rules)
    if enabled is not None:
        fg["enabled"] = enabled
    elif "enabled" not in fg:
        fg["enabled"] = True
    data["fileGuard"] = fg
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge_file_guard_rules(existing: List[dict], new_rules: List[dict]) -> List[dict]:
    """Append new_rules, skipping exact duplicates."""
    merged = list(_parse_rule_dicts(existing))
    seen = {(r.get("glob"), tuple(r.get("required", []))) for r in merged}
    for r in _parse_rule_dicts(new_rules):
        key = (r.get("glob"), tuple(r.get("required", [])))
        if key not in seen:
            merged.append(r)
            seen.add(key)
    return merged


def migrate_legacy_rules_file(rule_config_path: Path, legacy_rules_path: Path) -> bool:
    """Merge legacy rule-guard.json rules into Entity 2 when fileGuard.rules is empty."""
    if not legacy_rules_path.exists():
        return False
    data = read_rule_config_document(rule_config_path)
    fg = data.get("fileGuard")
    if isinstance(fg, dict) and _parse_rule_dicts(fg.get("rules")):
        return False
    legacy_rules = _load_legacy_rules_file(str(legacy_rules_path))
    if not legacy_rules:
        return False
    write_file_guard_rules(rule_config_path, legacy_rules)
    return True


# ── Path helpers ───────────────────────────────────────────────────────────────


def rules_docs_dir(cfg: LoadedConfig) -> Path:
    return Path(cfg.file_guard.rules_docs_dir)


def resolve_rules_docs_dir(
    cfg: LoadedConfig,
    cli_override: str | None = None,
) -> str:
    default = cfg.file_guard.rules_docs_dir
    if isinstance(cli_override, str) and cli_override.strip():
        return _parse_rules_docs_dir(cli_override, default)
    return default


# ── Cache / log paths ──────────────────────────────────────────────────────────


def logs_dir(platform: str = "cursor") -> Path:
    p = cache_root(platform) / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def rules_state_root(platform: str = "cursor") -> Path:
    p = cache_root(platform) / "rules-state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def rules_state_dir(session_id: str, platform: str = "cursor") -> Path:
    d = rules_state_root(platform) / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_decisions_log(platform: str = "cursor") -> Path:
    return logs_dir(platform) / "write-decisions.log"
