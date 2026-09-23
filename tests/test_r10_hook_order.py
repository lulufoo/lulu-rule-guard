"""R10: fileGuard hook order for write/read operations."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ENTRY = SCRIPTS / "entry.py"

MD_RULE_DOC = "docs/md/md-operations.md"
CODING_RULE_DOC = "docs/coding/coding-global-discipline.md"
def _run_entry(platform: str, payload: dict, cwd: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--platform", platform],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert result.returncode == 0, f"entry.py crashed:\n{result.stderr}"
    return json.loads(result.stdout.strip())


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@t.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "T"],
        check=True,
        capture_output=True,
    )
    (repo / ".gitignore").write_text(".cache\n", encoding="utf-8")
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )


def _write_runtime_config(repo: Path, *, rules: list[dict]) -> None:
    dest = repo / ".cursor" / "skills" / "lulu-rule-guard" / "rule-guard-config.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "version": 2,
                "fileGuard": {"enabled": True, "rules": rules},
            }
        ),
        encoding="utf-8",
    )


def _setup_repo(tmp_path: Path, rules: list[dict]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "docs" / "md").mkdir(parents=True)
    (repo / "docs" / "md" / "md-operations.md").write_text("# md ops\n", encoding="utf-8")
    (repo / "docs" / "coding").mkdir(parents=True)
    (repo / "docs" / "coding" / "coding-global-discipline.md").write_text(
        "# coding\n", encoding="utf-8"
    )

    _write_runtime_config(repo, rules=rules)

    _init_git_repo(repo)
    return repo


class TestHookOrder:
    def test_md_write_denies_rule_guard(self, tmp_path):
        repo = _setup_repo(
            tmp_path,
            [{"glob": "**/*.md", "required": [MD_RULE_DOC]}],
        )
        target = str(repo / "docs" / "test.md")
        out = _run_entry(
            "cursor",
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "conversation_id": "hook-order-md",
                "tool_input": {"file_path": target, "content": "x"},
            },
            repo,
        )
        assert out.get("permission") == "deny"
        msg = json.dumps(out, ensure_ascii=False)
        assert "[rule-guard]" in msg
        assert "md-operations" in msg

    def test_md_write_to_cache_allowed_after_read(self, tmp_path):
        repo = _setup_repo(
            tmp_path,
            [{"glob": "**/*.md", "required": [MD_RULE_DOC]}],
        )
        session = "hook-order-md-cache"
        _run_entry(
            "cursor",
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Read",
                "conversation_id": session,
                "tool_input": {"path": MD_RULE_DOC},
            },
            repo,
        )
        target = str(repo / ".cache" / "test.md")
        out = _run_entry(
            "cursor",
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "conversation_id": session,
                "tool_input": {"file_path": target, "content": "x"},
            },
            repo,
        )
        assert out.get("permission") == "allow"

    def test_code_write_denies_discipline(self, tmp_path):
        repo = _setup_repo(
            tmp_path,
            [
                {
                    "glob": "**/*.{js,ts,jsx,tsx,py,go,rs,rb,swift,html,css,json,java,kt}",
                    "required": [CODING_RULE_DOC],
                }
            ],
        )
        (repo / "src").mkdir()
        target = str(repo / "src" / "foo.ts")
        out = _run_entry(
            "cursor",
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "conversation_id": "hook-order-code",
                "tool_input": {"file_path": target, "content": "x"},
            },
            repo,
        )
        assert out.get("permission") == "deny"
        msg = json.dumps(out, ensure_ascii=False)
        assert "[rule-guard]" in msg
        assert "coding-global-discipline" in msg
