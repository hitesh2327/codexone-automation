"""Verify one CI secret group against its real service. Never prints secret values.

Usage (one check per call so each shows as its own pass/fail step in Actions):
    python scripts/check_secrets.py telegram|gemini|cloudinary|instagram|gh_pat

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


CHECKS = {"telegram": telegram, "gemini": gemini, "cloudinary": cloudinary_check,
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
