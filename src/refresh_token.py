"""Refresh the long-lived Instagram token (valid 60 days; refreshable once it is 24h+ old).

Where the new token goes:
  * GitHub Actions: updates the IG_ACCESS_TOKEN repo secret via `gh secret set`
    (needs a GH_PAT secret with permission to write Actions secrets).
  * Locally: rewrites IG_ACCESS_TOKEN in .env.
The token itself is never logged.

Usage:
    python -m src.refresh_token [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

import requests

from src.config import ROOT, get_env
from src.logger import get_logger
from src.redact import redact, redact_exc, register

log = get_logger("refresh_token")
URL = "https://graph.instagram.com/refresh_access_token"


def refresh() -> tuple[str, int]:
    # Meta documents the token only as a query parameter here, so the URL carries it: a network error's
    # text is scrubbed and the original exception (whose repr holds the URL) is not chained.
    try:
        r = requests.get(URL, params={"grant_type": "ig_refresh_token",
                                      "access_token": get_env("IG_ACCESS_TOKEN")}, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"token refresh failed: {redact_exc(e, 300)}") from None
    if not r.ok:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"token refresh failed (HTTP {r.status_code}): {redact(msg)}")
    data = r.json()
    register(data["access_token"])  # the new token is not in the environment yet: scrub it from now on
    return data["access_token"], int(data.get("expires_in", 0))


def save_token(token: str) -> str:
    if os.getenv("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}")  # never show it in Actions logs
        repo = os.environ["GITHUB_REPOSITORY"]
        env = {**os.environ, "GH_TOKEN": get_env("GH_PAT")}
        try:
            subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo, "--body", token],
                           check=True, env=env, capture_output=True)
        except subprocess.CalledProcessError as e:  # its text quotes the command line, token included
            raise RuntimeError(f"gh secret set failed (exit {e.returncode}): "
                               f"{redact((e.stderr or b'').decode(errors='replace'))[:300]}") from None
        return f"GitHub secret IG_ACCESS_TOKEN ({repo})"
    env_file = ROOT / ".env"
    text = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    line = f"IG_ACCESS_TOKEN={token}"
    text = (re.sub(r"(?m)^IG_ACCESS_TOKEN=.*$", lambda _: line, text) if "IG_ACCESS_TOKEN=" in text
            else text.rstrip("\n") + "\n" + line + "\n")
    env_file.write_text(text, encoding="utf-8")
    return str(env_file)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the Instagram long-lived token")
    ap.add_argument("--dry-run", action="store_true", help="validate the current token only")
    args = ap.parse_args(argv)

    if args.dry_run:
        from src.publish import check
        check()
        log.info("[dry-run] current token is valid; not refreshing")
        return 0
    token, expires_in = refresh()
    where = save_token(token)
    log.info("token refreshed; valid for %d days; saved to %s", expires_in // 86400, where)
    return 0


if __name__ == "__main__":
    sys.exit(main())
