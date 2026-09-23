"""R8: Test config_util path functions for both platforms.

Verifies that platform-specific config and cache paths are correct
and that backward-compatible aliases still point to cursor paths.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_util


def test_cursor_config_path():
    p = config_util.config_path("cursor")
    assert str(p) == ".cursor/skills/lulu-rule-guard/rule-guard-config.json"


def test_copilot_config_path():
    p = config_util.config_path("copilot")
    assert str(p) == ".github/lulu-rule-guard/rule-guard-config.json"


def test_cursor_cache_root():
    p = config_util.cache_root("cursor")
    assert str(p) == ".cache/cursor/lulu-rule-guard"


def test_copilot_cache_root():
    p = config_util.cache_root("copilot")
    assert str(p) == ".cache/copilot/lulu-rule-guard"


def test_backward_compat_CONFIG_PATH():
    """CONFIG_PATH alias still points to cursor path."""
    assert str(config_util.CONFIG_PATH) == ".cursor/skills/lulu-rule-guard/rule-guard-config.json"


def test_backward_compat_CACHE_ROOT():
    """CACHE_ROOT alias still points to cursor cache path."""
    assert str(config_util.CACHE_ROOT) == ".cache/cursor/lulu-rule-guard"


def test_rules_state_root_cursor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.rules_state_root("cursor")
    assert p.as_posix() == ".cache/cursor/lulu-rule-guard/rules-state"


def test_rules_state_root_copilot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.rules_state_root("copilot")
    assert p.as_posix() == ".cache/copilot/lulu-rule-guard/rules-state"


def test_logs_dir_cursor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.logs_dir("cursor")
    assert p.as_posix() == ".cache/cursor/lulu-rule-guard/logs"


def test_logs_dir_copilot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.logs_dir("copilot")
    assert p.as_posix() == ".cache/copilot/lulu-rule-guard/logs"


def test_write_decisions_log_cursor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.write_decisions_log("cursor")
    assert "cursor" in str(p)
    assert p.name == "write-decisions.log"


def test_write_decisions_log_copilot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.write_decisions_log("copilot")
    assert "copilot" in str(p)
    assert p.name == "write-decisions.log"


def test_rules_state_dir_cursor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.rules_state_dir("session-abc", "cursor")
    assert p.as_posix() == ".cache/cursor/lulu-rule-guard/rules-state/session-abc"


def test_rules_state_dir_copilot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = config_util.rules_state_dir("sess-xyz", "copilot")
    assert p.as_posix() == ".cache/copilot/lulu-rule-guard/rules-state/sess-xyz"


def test_load_config_missing_returns_default(tmp_path, monkeypatch):
    """load_config returns a LoadedConfig with default values when no config file exists."""
    monkeypatch.chdir(tmp_path)
    cfg = config_util.load_config("cursor")
    assert isinstance(cfg, config_util.LoadedConfig)
    assert cfg.rule_config == config_util.DEFAULT_RULE_CONFIG_FILE
    assert cfg.file_guard.enabled is True
    assert cfg.file_guard.rules == []
    assert cfg.file_guard.rules_docs_dir == "docs"
    assert config_util.rules_docs_dir(cfg).as_posix() == "docs"


def _write_rule_config(root: Path, payload: dict, platform: str = "cursor") -> Path:
    dest = config_util.config_path(platform)
    dest = root / dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def test_rules_docs_dir_from_file_guard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_rule_config(
        tmp_path,
        {"version": 2, "fileGuard": {"enabled": True, "rulesDocsDir": "docs/coding", "rules": []}},
    )
    cfg = config_util.load_config("cursor")
    assert cfg.file_guard.rules_docs_dir == "docs/coding"
    assert config_util.rules_docs_dir(cfg).as_posix() == "docs/coding"


def test_rules_docs_dir_legacy_top_level_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_rule_config(
        tmp_path,
        {"version": 2, "rulesDocsDir": "docs/legacy", "fileGuard": {"enabled": True, "rules": []}},
    )
    cfg = config_util.load_config("cursor")
    assert cfg.file_guard.rules_docs_dir == "docs/legacy"


def test_rules_docs_dir_rejects_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_rule_config(
        tmp_path,
        {"version": 2, "fileGuard": {"rulesDocsDir": "/tmp/rules", "rules": []}},
    )
    with pytest.warns(UserWarning, match="rulesDocsDir"):
        cfg = config_util.load_config("cursor")
    assert cfg.file_guard.rules_docs_dir == "docs"


def test_leftover_pointer_and_skill_config_are_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    leftover = tmp_path / "skill-config/lulu-rule-guard/rule-guard-config.json"
    leftover.parent.mkdir(parents=True)
    leftover.write_text(
        json.dumps(
            {
                "version": 2,
                "fileGuard": {
                    "enabled": True,
                    "rulesDocsDir": "UNIQUE_SKILL_CONFIG",
                    "rules": [],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pointer = tmp_path / ".cursor/lulu-rule-guard/config.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(
        json.dumps({"version": 2, "ruleConfig": leftover.as_posix()}) + "\n",
        encoding="utf-8",
    )
    cfg = config_util.load_config("cursor")
    assert cfg.file_guard.rules_docs_dir != "UNIQUE_SKILL_CONFIG"


def _cfg_with_rules_docs_dir(tmp_path, rules_docs_dir: str) -> config_util.LoadedConfig:
    _write_rule_config(
        tmp_path,
        {
            "version": 2,
            "fileGuard": {
                "enabled": True,
                "rulesDocsDir": rules_docs_dir,
                "rules": [],
            },
        },
    )
    return config_util.load_config("cursor")


def test_resolve_rules_docs_dir_passthrough_chain_a(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = _cfg_with_rules_docs_dir(tmp_path, "docs/coding")
    assert config_util.resolve_rules_docs_dir(cfg, None) == "docs/coding"
    assert config_util.resolve_rules_docs_dir(cfg, "") == "docs/coding"


def test_resolve_rules_docs_dir_cli_overrides_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = _cfg_with_rules_docs_dir(tmp_path, "docs")
    assert config_util.resolve_rules_docs_dir(cfg, "docs/special") == "docs/special"


def test_resolve_rules_docs_dir_cli_invalid_falls_back_to_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = _cfg_with_rules_docs_dir(tmp_path, "docs/coding")
    with pytest.warns(UserWarning, match="rulesDocsDir"):
        resolved = config_util.resolve_rules_docs_dir(cfg, "/tmp/abs")
    assert resolved == "docs/coding"


def test_resolve_rules_docs_dir_cli_without_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = config_util.load_config("cursor")
    assert cfg.file_guard.rules_docs_dir == "docs"
    assert config_util.resolve_rules_docs_dir(cfg, "docs/foo") == "docs/foo"


def test_init_seeds_rule_config_not_pointer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import init as init_mod

    assert init_mod.main(["--platform", "cursor"]) == 0
    root = tmp_path / ".cursor/skills/lulu-rule-guard"
    assert (root / "rule-guard-config.json").is_file()
    assert not (root / "config.json").exists()
    assert not (tmp_path / "skill-config/lulu-rule-guard/rule-guard-config.json").exists()
    payload = json.loads((root / "rule-guard-config.json").read_text(encoding="utf-8"))
    assert payload["fileGuard"]["rules"] == []


def test_init_does_not_overwrite_existing_rule_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dest = _write_rule_config(tmp_path, {"version": 2, "fileGuard": {"rules": [{"keep": True}]}})
    import init as init_mod

    assert init_mod.main(["--platform", "cursor"]) == 0
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["fileGuard"]["rules"] == [{"keep": True}]
