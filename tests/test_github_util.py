"""Tests for github_util URL parsing (no live gh)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_module(name: str, rel_path: str):
    path = SCRIPTS / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


github_util = _load_module("github_util", "lib/github_util.py")


def test_parse_github_url_colon_form():
    owner, repo, ref, path = github_util.parse_github_url(
        "github:example/workflow-rules@main/lulu-sync-rules/dialogure/global-conversation.md"
    )
    assert owner == "example"
    assert repo == "workflow-rules"
    assert ref == "main"
    assert path == "lulu-sync-rules/dialogure/global-conversation.md"


def test_parse_github_url_slash_ref_form():
    owner, repo, ref, path = github_util.parse_github_url(
        "github:example/workflow-rules/main/docs/git/git-workflow-standard.md"
    )
    assert (owner, repo, ref, path) == (
        "example",
        "workflow-rules",
        "main",
        "docs/git/git-workflow-standard.md",
    )


def test_parse_github_url_https_form():
    owner, repo, ref, path = github_util.parse_github_url(
        "https://github.com/example/workflow-rules/blob/main/lulu-sync-rules/SKILL.md"
    )
    assert (owner, repo, ref, path) == (
        "example",
        "workflow-rules",
        "main",
        "lulu-sync-rules/SKILL.md",
    )


def test_parse_github_url_invalid():
    with pytest.raises(ValueError, match="Unrecognised URL"):
        github_util.parse_github_url("https://example.com/not-github")
