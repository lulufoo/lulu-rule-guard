"""GitHub URL parsing and file fetch helpers (stdlib + gh)."""
from __future__ import annotations

import base64
import json
import re
import subprocess


def parse_github_url(url: str) -> tuple[str, str, str, str]:
    """Parse github: or https GitHub blob URL into (owner, repo, ref, path)."""
    url = url.strip()
    if url.startswith("github:"):
        rest = url[len("github:") :]
        parts = rest.split("/")
        if len(parts) < 3:
            raise ValueError(f"Expected github:owner/repo@ref/path, got: {url!r}")
        owner = parts[0]
        repo_ref = parts[1]
        if "@" in repo_ref:
            repo, ref = repo_ref.rsplit("@", 1)
            path = "/".join(parts[2:])
        elif len(parts) >= 4:
            repo, ref = parts[1], parts[2]
            path = "/".join(parts[3:])
        else:
            raise ValueError(
                f"Expected github:owner/repo@ref/path or github:owner/repo/ref/path, "
                f"got: {url!r}"
            )
        return owner, repo, ref, path
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)",
        url,
    )
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)
    raise ValueError(
        f"Unrecognised URL format: {url!r}\n"
        "  Supported: https://github.com/owner/repo/blob/ref/path\n"
        "             github:owner/repo@ref/path\n"
        "             github:owner/repo/ref/path"
    )


def gh_fetch_file(owner: str, repo: str, ref: str, path: str) -> bytes:
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/contents/{path}?ref={ref}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"gh api failed: {err}\nHint: run `gh auth login` or check the URL."
        )
    detail = json.loads(result.stdout)
    content_b64 = detail.get("content") or ""
    if detail.get("encoding") == "base64":
        return base64.b64decode(content_b64.replace("\n", ""))
    return content_b64.encode("utf-8")
