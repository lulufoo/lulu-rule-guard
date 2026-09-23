"""Tests for FileGuardConfig — config_util extensions."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from config_util import (  # noqa: E402
    load_config,
    load_runtime_config,
    merge_file_guard_rules,
    migrate_legacy_rules_file,
    parse_file_guard,
    write_file_guard_rules,
)


class TestFileGuardConfig(unittest.TestCase):
    def test_full_dict(self):
        result = parse_file_guard({
            "enabled": True,
            "rulesDocsDir": "docs/coding",
            "rules": [{"glob": "**/*.md", "required": ["docs/x.md"]}],
        })
        self.assertTrue(result.enabled)
        self.assertEqual(result.rules_docs_dir, "docs/coding")
        self.assertEqual(len(result.rules), 1)
        self.assertEqual(result.rules[0]["glob"], "**/*.md")

    def test_legacy_top_level_rules_docs_dir(self):
        result = parse_file_guard(
            {"enabled": True, "rules": []},
            legacy_rules_docs_dir="docs/legacy",
        )
        self.assertEqual(result.rules_docs_dir, "docs/legacy")

    def test_absent_returns_defaults(self):
        result = parse_file_guard(None)
        self.assertTrue(result.enabled)
        self.assertEqual(result.rules, [])

    def test_bool_true(self):
        result = parse_file_guard(True)
        self.assertTrue(result.enabled)
        self.assertEqual(result.rules, [])


class TestLoadRuntimeConfigFileGuard(unittest.TestCase):
    def test_loads_file_guard_from_json(self):
        data = {
            "version": 2,
            "fileGuard": {
                "enabled": False,
                "rules": [{"glob": "*.py", "required": ["docs/a.md"]}],
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        rt = load_runtime_config(tmp_path)
        self.assertFalse(rt.file_guard.enabled)
        self.assertEqual(len(rt.file_guard.rules), 1)

    def test_falls_back_to_legacy_rules_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "rule-guard.json"
            legacy.write_text(
                json.dumps({"rules": [{"glob": "*.js", "required": ["docs/b.md"]}]}),
                encoding="utf-8",
            )
            config = Path(tmp) / "rule-guard-config.json"
            config.write_text('{"version":2}\n', encoding="utf-8")
            rt = load_runtime_config(str(config), legacy_rules_file=str(legacy))
            self.assertEqual(len(rt.file_guard.rules), 1)
            self.assertEqual(rt.file_guard.rules[0]["glob"], "*.js")


class TestFileGuardHelpers(unittest.TestCase):
    def test_merge_skips_duplicates(self):
        existing = [{"glob": "*.md", "required": ["docs/a.md"]}]
        new_rules = [{"glob": "*.md", "required": ["docs/a.md"]}, {"glob": "*.py", "required": ["docs/b.md"]}]
        merged = merge_file_guard_rules(existing, new_rules)
        self.assertEqual(len(merged), 2)

    def test_write_preserves_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "rule-guard-config.json"
            config.write_text(
                json.dumps({"version": 2, "chimeGuard": {"enabled": True}}) + "\n",
                encoding="utf-8",
            )
            write_file_guard_rules(config, [{"glob": "*.md", "required": ["docs/a.md"]}])
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertTrue(data["chimeGuard"]["enabled"])
            self.assertEqual(len(data["fileGuard"]["rules"]), 1)
            loaded = load_runtime_config(str(config))
            self.assertTrue(loaded.chime.enabled)

    def test_migrate_legacy_rules_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "rule-guard-config.json"
            config.write_text('{"version":2}\n', encoding="utf-8")
            legacy = Path(tmp) / "rule-guard.json"
            legacy.write_text(
                json.dumps({"rules": [{"glob": "*.ts", "required": ["docs/c.md"]}]}),
                encoding="utf-8",
            )
            self.assertTrue(migrate_legacy_rules_file(config, legacy))
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data["fileGuard"]["rules"][0]["glob"], "*.ts")


class TestLoadConfigFileGuard(unittest.TestCase):
    def test_propagates_file_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / ".cursor" / "skills" / "lulu-rule-guard" / "rule-guard-config.json"
            dest.parent.mkdir(parents=True)
            dest.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "fileGuard": {"enabled": False, "rules": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            old = Path.cwd()
            try:
                import os

                os.chdir(root)
                cfg = load_config("cursor")
            finally:
                os.chdir(old)
            self.assertFalse(cfg.file_guard.enabled)


if __name__ == "__main__":
    unittest.main()
