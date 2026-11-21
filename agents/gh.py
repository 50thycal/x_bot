"""GitHub REST + git helpers for the agents (standard library only).

Uses GITHUB_TOKEN / GITHUB_REPOSITORY from the Actions environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from publisher.xbot import GH_API, ROOT

LABEL_COLORS = {"engagement-queue": "1d76db", "weekly-review": "5319e7", "drafts": "0e8a16"}


class GHError(RuntimeError):
    pass


def repo() -> str:
    r = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not r:
        raise GHError("GITHUB_REPOSITORY is not set")
    return r


def api(method: str, path: str, body: dict | None = None, query: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise GHError("GITHUB_TOKEN is not set")
    url = f"{GH_API}{path}" + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "x-bot-agents"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise GHError(f"GitHub {method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from None


def ensure_label(name: str) -> None:
    try:
        api("GET", f"/repos/{repo()}/labels/{urllib.parse.quote(name)}")
    except GHError:
        api("POST", f"/repos/{repo()}/labels", {"name": name, "color": LABEL_COLORS.get(name, "ededed")})


def issues_with_label(label: str, limit: int = 7) -> list[dict]:
    items = api("GET", f"/repos/{repo()}/issues",
                query={"labels": label, "state": "all", "per_page": limit, "sort": "created", "direction": "desc"})
    return [i for i in items if "pull_request" not in i]


def find_issue(title: str, label: str) -> dict | None:
    for i in issues_with_label(label, limit=30):
        if i.get("title") == title:
            return i
    return None


def create_issue(title: str, body: str, label: str) -> dict:
    ensure_label(label)
    return api("POST", f"/repos/{repo()}/issues", {"title": title, "body": body, "labels": [label]})


def create_pr(branch: str, title: str, body: str, base: str = "main") -> dict:
    return api("POST", f"/repos/{repo()}/pulls", {"title": title, "head": branch, "base": base, "body": body})


def dispatch_workflow(workflow_file: str, ref: str) -> None:
    api("POST", f"/repos/{repo()}/actions/workflows/{workflow_file}/dispatches", {"ref": ref})


def remote_branch_exists(branch: str) -> bool:
    out = subprocess.run(["git", "ls-remote", "--heads", "origin", branch],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    return bool(out.stdout.strip())


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        raise GHError(f"git {' '.join(args)} failed: {out.stderr.strip()[:500]}")
    return out.stdout.strip()


def commit_to_new_branch(branch: str, paths: list[str], message: str) -> str:
    """Create `branch` from the current HEAD, commit `paths`, push. Returns the branch actually used."""
    name, n = branch, 2
    while remote_branch_exists(name):
        name, n = f"{branch}-{n}", n + 1
    git("config", "user.name", "x-bot")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("checkout", "-b", name)
    git("add", "--", *paths)
    git("commit", "-m", message)
    git("push", "-u", "origin", name)
    return name
