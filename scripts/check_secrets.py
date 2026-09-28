"""Verify one CI secret group against its real service. Never prints secret values.

Usage (one check per call so each shows as its own pass/fail step in Actions):
    python scripts/check_secrets.py telegram|gemini|cloudinary|instagram|youtube|gh_pat

Optional non-secret expectations (compare CI secrets to what works locally):
    EXPECTED_BOT_ID   Telegram bot id the token must belong to
    EXPECTED_IG_ID    numeric Instagram user id
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.config import get_env  # noqa: E402


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def telegram() -> None:
    from telegram import Bot

    chat_raw = get_env("TG_CHAT_ID")
    if not chat_raw.lstrip("-").isdigit():
        fail("TG_CHAT_ID must be a number (no quotes/spaces)")

    async def run():
        async with Bot(get_env("TG_BOT_TOKEN")) as bot:
            me = await bot.get_me()
            expected = os.getenv("EXPECTED_BOT_ID")
            if expected and str(me.id) != expected:
                fail(f"TG_BOT_TOKEN belongs to @{me.username} (id {me.id}), expected bot id {expected}")
            chat = await bot.get_chat(int(chat_raw))
            webhook = await bot.get_webhook_info()
            if webhook.url:
                fail("a webhook is set on this bot; getUpdates polling cannot work")
            print(f"OK: token is @{me.username} (id {me.id}); chat reachable ({chat.type})")
    asyncio.run(run())


def gemini() -> None:
    from google import genai
    client = genai.Client(api_key=get_env("GEMINI_API_KEY"))  # keep a reference: the pager lazily fetches
    try:
        models = [m.name for m in client.models.list()]
    except Exception as e:  # noqa: BLE001
        fail(f"GEMINI_API_KEY rejected: {type(e).__name__}")
    print(f"OK: Gemini key works ({len(models)} models visible)")


def cloudinary_check() -> None:
    from src.upload import _configure
    import cloudinary.api
    try:
        _configure()
        cloudinary.api.ping()
    except Exception as e:  # noqa: BLE001
        fail(f"CLOUDINARY_URL invalid: {type(e).__name__}: {str(e)[:120]}")
    print(f"OK: Cloudinary reachable (cloud '{cloudinary.config().cloud_name}')")


def instagram() -> None:
    uid = get_env("IG_USER_ID")
    if not uid.isdigit():
        fail("IG_USER_ID must be the numeric id (e.g. 17841475010536333), not the username")
    r = requests.get("https://graph.instagram.com/v21.0/me",
                     params={"fields": "user_id,username", "access_token": get_env("IG_ACCESS_TOKEN")},
                     timeout=30)
    if not r.ok:
        fail(f"IG_ACCESS_TOKEN rejected (HTTP {r.status_code}): "
             f"{r.json().get('error', {}).get('message', '')[:150]}")
    me = r.json()
    if str(me.get("user_id")) != uid:
        fail(f"IG_USER_ID {uid} does not match the token's account {me.get('user_id')} (@{me.get('username')})")
    expected = os.getenv("EXPECTED_IG_ID")
    if expected and uid != expected:
        fail(f"IG_USER_ID is {uid}, expected {expected}")
    print(f"OK: Instagram token works for @{me.get('username')}")


def gh_pat() -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "hitesh2327/codexone-automation")
    r = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                     headers={"Authorization": f"Bearer {get_env('GH_PAT')}",
                              "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code in (401, 403, 404):
        fail(f"GH_PAT cannot access this repo's Actions secrets (HTTP {r.status_code}); "
             "needs repository access to codexone-automation with 'Secrets: Read and write'")
    r.raise_for_status()
    print("OK: GH_PAT can manage this repo's Actions secrets (token refresh will work)")


def youtube() -> None:
    from src.publish_youtube import YTError, credentials, privacy
    try:
        mode = privacy()          # also validates the optional YT_PRIVACY variable
        credentials()
    except YTError as e:
        fail(str(e)[:200])
    print(f"OK: YouTube refresh token works (upload scope); uploads will be {mode}")


YT_FORMAT = {  # (expected prefix/suffix, hint) -- lets a bad paste be named without printing it
    "YT_CLIENT_ID": (lambda v: v.endswith(".apps.googleusercontent.com"), "should end with .apps.googleusercontent.com"),
    "YT_CLIENT_SECRET": (lambda v: v.startswith("GOCSPX-"), "should start with GOCSPX-"),
    "YT_REFRESH_TOKEN": (lambda v: v.startswith("1//"), "should start with 1//"),
}


def yt_value(name: str) -> None:
    """One YouTube secret: present, well-formed, and identical to the local .env value.

    EXPECTED_FP_<NAME> is the first 8 hex chars of sha256(value) computed locally -- enough to
    detect a mismatch, useless for recovering the secret.
    """
    import hashlib
    raw = os.getenv(name)
    if raw is None or raw == "":
        fail(f"{name} is missing -- add it under Settings → Secrets and variables → Actions → "
             "Secrets → Repository secrets (not Variables, not an Environment)")
    v = raw.strip()
    if raw != v:
        print(f"note: {name} has leading/trailing whitespace (stripped at runtime)")
    if v.startswith(f"{name}=") or v[:1] in "\"'" or v[-1:] in "\"'":
        fail(f"{name} value includes the '{name}=' prefix or quotes -- paste only the value")
    ok, hint = YT_FORMAT[name]
    if not ok(v):
        fail(f"{name} does not look right: {hint} (length {len(v)})")
    expected = os.getenv(f"EXPECTED_FP_{name}")
    fp = hashlib.sha256(v.encode()).hexdigest()[:8]
    if expected and fp != expected:
        fail(f"{name} differs from the working local value (length {len(v)}); re-copy it from .env")
    print(f"OK: {name} present, well-formed{', matches local' if expected else ''} (length {len(v)})")


def database() -> None:
    from sqlalchemy import text
    from src import db
    if not db.enabled():
        fail("DATABASE_URL is missing")
    heads = {f.stem.split("_")[1] for f in (Path(__file__).resolve().parent.parent / "api" / "migrations" / "versions").glob("*.py")}
    try:
        with db.engine().connect() as c:
            current = c.execute(text("select version_num from alembic_version")).scalar()
            posts = c.execute(text("select count(*) from posts")).scalar()
    except Exception as e:  # noqa: BLE001
        fail(f"cannot use the database: {type(e).__name__}: {str(e).splitlines()[0][:150]}")
    if current not in heads:
        fail(f"schema revision {current} not found in api/migrations (run alembic upgrade head)")
    print(f"OK: database reachable, schema at {current}, {posts} posts")


CHECKS = {"database": database, "yt_client_id": lambda: yt_value("YT_CLIENT_ID"),
          "yt_client_secret": lambda: yt_value("YT_CLIENT_SECRET"),
          "yt_refresh_token": lambda: yt_value("YT_REFRESH_TOKEN"),
          "youtube": youtube, "telegram": telegram, "gemini": gemini, "cloudinary": cloudinary_check,
          "instagram": instagram, "gh_pat": gh_pat}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        sys.exit(f"usage: check_secrets.py {'|'.join(CHECKS)}")
    try:
        CHECKS[sys.argv[1]]()
    except SystemExit:
        raise
    except Exception as e:  # missing secret etc. -- message never includes values
        fail(f"{type(e).__name__}: {e}")
