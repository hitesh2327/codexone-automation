"""Minimal GitHub Actions client for the dashboard: start a workflow, find its run, read its status.

Only the fields we need ever leave this module (never a raw response body or the token). Reads are cached
for a few seconds so several tabs don't multiply API calls, and a rate-limit response pauses all reads until
GitHub says they may resume. Needs GITHUB_DISPATCH_TOKEN (fine-grained, this repo only, Actions: read + write).
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

import requests

from src.config import get_env
from src.logger import get_logger

log = get_logger("github")

API = "https://api.github.com"
CACHE_TTL = 5.0
MAX_BACKOFF = 300.0


class GitHubError(Exception):
    """`kind`: rejected (bad/expired token, no permission, wrong repo), rate_limited, unavailable,
    not_configured (no GITHUB_REPOSITORY)."""

    def __init__(self, kind: str, status: int = 0, retry_after: int = 0):
        super().__init__(f"{kind} (HTTP {status})" if status else kind)
        self.kind, self.status, self.retry_after = kind, status, retry_after


_cache: dict[str, tuple[float, dict]] = {}
_blocked_until = 0.0


def reset() -> None:
    """Forget cached reads and any rate-limit pause (tests)."""
    global _blocked_until
    _cache.clear()
    _blocked_until = 0.0


_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


def repository() -> str | None:
    """`owner/name` of the automation repo, or None when it is unset or malformed.

    There is deliberately no default: a customer's dashboard must never start workflows in someone
    else's repository. GitHub Actions sets GITHUB_REPOSITORY itself; the API gets it from its
    environment or the Config page.
    """
    repo = (get_env("GITHUB_REPOSITORY", required=False) or "").strip()
    return repo if _REPO_RE.match(repo) and ".." not in repo else None


def configured() -> bool:
    return bool(get_env("GITHUB_DISPATCH_TOKEN", required=False)) and repository() is not None


def _repo() -> str:
    repo = repository()
    if not repo:
        raise GitHubError("not_configured")
    return repo


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_env('GITHUB_DISPATCH_TOKEN')}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _error(r: requests.Response) -> GitHubError:
    remaining = r.headers.get("x-ratelimit-remaining")
    if r.status_code == 429 or (r.status_code == 403 and (remaining == "0" or r.headers.get("retry-after"))):
        wait = int(r.headers.get("retry-after") or 0)
        if not wait and r.headers.get("x-ratelimit-reset", "").isdigit():
            wait = max(0, int(r.headers["x-ratelimit-reset"]) - int(time.time()))
        return GitHubError("rate_limited", r.status_code, min(max(wait, 30), int(MAX_BACKOFF)))
    if r.status_code in (401, 403, 404, 422):
        return GitHubError("rejected", r.status_code)
    return GitHubError("unavailable", r.status_code)


def dispatch(workflow: str, inputs: dict[str, str], ref: str = "main") -> None:
    """Start a workflow_dispatch run. GitHub answers 204 with no run id (see find_run)."""
    try:
        r = requests.post(f"{API}/repos/{_repo()}/actions/workflows/{workflow}/dispatches", headers=_headers(),
                          json={"ref": ref, "inputs": inputs}, timeout=20)
    except requests.RequestException as e:
        raise GitHubError("unavailable") from e
    if r.status_code != 204:
        log.warning("workflow dispatch failed: HTTP %s", r.status_code)
        raise _error(r)


def _get(path: str, params: dict | None = None) -> dict:
    global _blocked_until
    now = time.monotonic()
    if now < _blocked_until:
        raise GitHubError("rate_limited", 0, int(_blocked_until - now) + 1)
    key = path + repr(sorted((params or {}).items()))
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        r = requests.get(f"{API}/repos/{_repo()}{path}", headers=_headers(), params=params, timeout=20)
    except requests.RequestException as e:
        raise GitHubError("unavailable") from e
    if r.status_code != 200:
        err = _error(r)
        if err.kind == "rate_limited":
            _blocked_until = now + err.retry_after
            log.warning("GitHub rate limit; pausing reads for %ss", err.retry_after)
        raise err
    data = r.json()
    _cache[key] = (now, data)
    return data


def _slim(run: dict) -> dict:
    url = run.get("html_url") or ""
    return {"id": run["id"], "status": run.get("status") or "", "conclusion": run.get("conclusion") or "",
            "name": run.get("display_title") or run.get("name") or "",
            "url": url if url.startswith("https://github.com/") else ""}


def find_run(workflow: str, run_name: str, created_after: datetime) -> dict | None:
    """The workflow_dispatch run whose name is `run_name` (dispatch returns no id, so we match the run-name)."""
    since = (created_after - timedelta(minutes=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = _get(f"/actions/workflows/{workflow}/runs",
                {"event": "workflow_dispatch", "per_page": 20, "created": f">={since}"})
    for run in data.get("workflow_runs", []):
        if run_name in (run.get("display_title"), run.get("name")):
            return _slim(run)
    return None


def get_run(run_id: int) -> dict:
    return _slim(_get(f"/actions/runs/{int(run_id)}"))
