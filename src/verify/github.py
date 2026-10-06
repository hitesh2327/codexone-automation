"""GitHub automation: the repository (owner/name) and a fine-grained token that can start its workflows.

Sources: REST "Workflows" https://docs.github.com/en/rest/actions/workflows ("Get a workflow" needs the
fine-grained permission "Actions" repository permissions (read); "Create a workflow dispatch event" needs
"Actions" (write)); the workflow `state` enum (active, deleted, disabled_fork, disabled_inactivity,
disabled_manually) from GitHub's OpenAPI description (github/rest-api-description); "Troubleshooting the
REST API": a private resource requested without access answers 404, not 403, and a fine-grained token
lacking a permission gets "Resource not accessible by personal access token".

    format  repository matches owner/name; token has no whitespace
    live    GET /repos/{repo}                                  -> token can see the repo; archived? default branch
            GET /repos/{repo}/actions/workflows/{file} (x2)    -> Actions: read, workflow exists, state == active
            GitHub-Authentication-Token-Expiration header      -> expiry date when GitHub sends it
    (not provable without side effects) Actions: write. Only a real dispatch proves it; it is reported as
    "not exercised" and confirmed by the first dashboard generation.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from src.verify.base import Result, Run, Unreachable, body, has_bad_chars, http

INTEGRATION = "github"
API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")  # same rule as src.github_actions
WORKFLOWS = ("daily-generate.yml", "poll-approvals.yml")  # what the dashboard starts (generation, publish/regenerate)
WARN_DAYS = 14


def classify(r) -> str:
    s = r.status_code
    remaining = r.headers.get("x-ratelimit-remaining")
    if s == 429 or (s == 403 and (remaining == "0" or r.headers.get("retry-after"))):
        return "github.rate_limited"
    if s == 401:
        return "github.token_rejected"
    if s == 403:
        return "github.forbidden"
    if s == 404:
        return "github.not_found"
    return "github.unavailable"


def _expiry(r) -> datetime | None:
    """`GitHub-Authentication-Token-Expiration: 2026-12-01 10:00:00 UTC` (tokens with an expiry only)."""
    raw = (r.headers.get("github-authentication-token-expiration") or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M:%S %z"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def verify(values: dict[str, str], depth: str = "live", now: datetime | None = None) -> Result:
    run = Run(INTEGRATION, depth)
    repo, token = values.get("GITHUB_REPOSITORY") or "", values.get("GITHUB_DISPATCH_TOKEN") or ""
    if not repo and not token:
        return run.finish(not_set=True)
    if repo:
        if REPO_RE.match(repo) and ".." not in repo:
            run.ok("repo_format", "Repository is owner/name", repo, depth="format")
        else:
            run.fail("repo_format", "Repository is owner/name", "github.repo_format", depth="format")
    if token:
        if has_bad_chars(token):
            run.fail("token_format", "Token has no spaces or line breaks", "github.token_format", depth="format")
        else:
            run.ok("token_format", "Token has no spaces or line breaks", depth="format")
            if token.startswith("ghp_"):  # prefixes: docs.github.com "GitHub's token formats"
                run.warn("token_kind", "Fine-grained token (this repository only)", "github.classic_token", depth="format")
    if not repo or not token:
        run.fail("value", "Repository and token are both set", "verify.not_set", depth="format")
        return run.finish()
    if run.failed or depth == "format":
        return run.finish()

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    owner, name = repo.split("/", 1)
    base = f"{API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    try:
        r = http("GET", base, headers=headers)
        if r.status_code != 200:
            run.fail("repo_visible", "The token can see the repository", classify(r))
            return run.finish()
        info = body(r)
        run.ok("repo_visible", "The token can see the repository",
               f"{info.get('full_name') or repo} ({'private' if info.get('private') else 'public'})")
        run.evidence["repository"] = info.get("full_name") or repo
        run.evidence["private"] = bool(info.get("private"))
        if info.get("archived"):
            run.warn("not_archived", "Repository is not archived", "github.archived")  # effect on dispatch: U (S10)
        branch = info.get("default_branch")
        if branch and branch != "main":
            run.warn("branch", "Workflows run on the main branch", "github.branch", f"default branch is {branch}")

        exp = _expiry(r)
        if exp:
            run.expires_at = exp.isoformat(timespec="seconds")
            left = exp - (now or datetime.now(timezone.utc))
            if left < timedelta(days=WARN_DAYS):
                run.warn("token_expiry", "Token isn't about to expire", "github.token_expiring",
                         f"expires {exp:%d %b %Y} ({max(left.days, 0)} days)")
            else:
                run.ok("token_expiry", "Token isn't about to expire", f"expires {exp:%d %b %Y}")
        else:
            run.skip("token_expiry", "Token isn't about to expire", "GitHub didn't report an expiry date for this token.")

        for wf in WORKFLOWS:
            r = http("GET", f"{base}/actions/workflows/{wf}", headers=headers)
            label = f"Workflow {wf} is enabled"
            if r.status_code == 404:
                run.fail(f"workflow:{wf}", label, "github.workflow_missing")
                continue
            if r.status_code != 200:
                run.fail(f"workflow:{wf}", label, classify(r))
                continue
            state = str(body(r).get("state") or "")
            if state == "active":
                run.ok(f"workflow:{wf}", label, "active (Actions: read confirmed)")
            else:
                run.fail(f"workflow:{wf}", label, "github.workflow_disabled", f"state: {state or 'unknown'}")
    except Unreachable:
        run.fail("reachable", "GitHub is reachable", "github.unreachable")
        return run.finish()

    run.skip("actions_write", "The token can start workflows (Actions: write)",
             "Can't be proven without starting a workflow; confirmed by the first dashboard generation.",
             code="github.write_unconfirmed")
    return run.finish()
