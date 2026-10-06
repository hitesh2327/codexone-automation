"""Telegram bot token + approval chat.

Source of every rule below: the Bot API reference, https://core.telegram.org/bots/api

    format  token is <digits>:<url-safe characters> (the token goes into the URL path by design:
            https://api.telegram.org/bot<token>/METHOD, so anything else is refused before a request);
            chat id is an integer (negative for groups)
    live    getMe           -> the token is valid; shows the bot's @username
            getWebhookInfo  -> `url` must be empty: getUpdates (how approvals are read) "will not work if
                               an outgoing webhook is set up"
            getChat         -> the bot can see the approval chat
    deep    sendMessage     -> a plain test message, no buttons (explicit click only)

Chat detection (detect_chats) reads getUpdates WITHOUT an offset. Per the docs, an update "is considered
confirmed as soon as getUpdates is called with an offset higher than its update_id", so a call without
an offset confirms nothing and the approval poll still receives every button press. It also never passes
`allowed_updates` (that would change the bot's stored subscription: "If not specified, the previous setting
will be used") and never uses a negative offset ("All previous updates will be forgotten").
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from src.verify.base import Result, Run, Unreachable, body, http

INTEGRATION = "telegram"
API = "https://api.telegram.org"
TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")  # shape from the docs' example; length is not documented
CHAT_RE = re.compile(r"^-?\d{1,20}$")
TEST_TEXT = ("Test message from your content dashboard setup. If you can read this, approval previews will "
             "reach you here. Nothing was published.")


def _url(token: str, method: str) -> str:
    return f"{API}/bot{token}/{method}"


def classify(r) -> str:
    """Error responses are {"ok": false, "error_code": int, "description": str}; error_code "is subject to
    change", so the HTTP status is used first and the description only to separate known cases."""
    desc = str(body(r).get("description") or "").lower()
    s = r.status_code
    if s in (401, 404):  # 401 Unauthorized for a revoked token; 404 for a malformed one (observed, U9)
        return "telegram.token_rejected"
    if s == 409:
        return "telegram.poll_conflict"
    if s == 429:
        return "telegram.rate_limited"
    if s == 403:
        return "telegram.blocked"
    if s == 400 and "chat not found" in desc:
        return "telegram.chat_not_found"
    if s == 400 and ("chat_id" in desc or "peer" in desc):
        return "telegram.chat_not_found"
    return "telegram.unavailable"


def _call(token: str, method: str, **params):
    r = http("POST", _url(token, method), json=params or None)
    data = body(r)
    if r.status_code == 200 and data.get("ok") is True:
        return data.get("result"), None
    return None, classify(r)


def check_format(values: dict[str, str], run: Run, need_chat: bool = True) -> tuple[str, str]:
    token, chat = values.get("TG_BOT_TOKEN") or "", values.get("TG_CHAT_ID") or ""
    if token:
        if TOKEN_RE.match(token):
            run.ok("token_format", "Token looks like a bot token", depth="format")  # no part of it is echoed
        else:
            run.fail("token_format", "Token looks like a bot token", "telegram.token_format", depth="format")
    if chat and need_chat:
        if CHAT_RE.match(chat):
            run.ok("chat_format", "Chat ID is a number", depth="format")
        else:
            run.fail("chat_format", "Chat ID is a number", "telegram.chat_format", depth="format")
    return token, chat


def verify(values: dict[str, str], depth: str = "live") -> Result:
    run = Run(INTEGRATION, depth)
    token, chat = check_format(values, run)
    if not token or not chat:
        if not token and not chat:
            return run.finish(not_set=True)
        run.fail("value", "Bot token and chat ID are both set", "verify.not_set", depth="format")
        return run.finish()
    if run.failed or depth == "format":
        return run.finish()
    try:
        me, err = _call(token, "getMe")
        if err:
            run.fail("token_valid", "Telegram accepts the token", err)
            return run.finish()
        bot = f"@{me.get('username')}" if isinstance(me, dict) and me.get("username") else "your bot"
        run.ok("token_valid", "Telegram accepts the token", bot)
        run.evidence["bot"] = bot

        hook, err = _call(token, "getWebhookInfo")
        if err:
            run.fail("no_webhook", "No webhook blocks approvals", err)
        elif isinstance(hook, dict) and hook.get("url"):
            host = urlsplit(str(hook["url"])).hostname or "another server"  # the path may hold a secret
            run.fail("no_webhook", "No webhook blocks approvals", "telegram.webhook_set", f"webhook points at {host}")
            run.evidence["webhook_host"] = host
        else:
            run.ok("no_webhook", "No webhook blocks approvals", "polling (getUpdates) can work")

        info, err = _call(token, "getChat", chat_id=int(chat))
        if err:
            run.fail("chat_reachable", "The bot can see the approval chat", err)
            return run.finish()
        kind = info.get("type", "chat") if isinstance(info, dict) else "chat"
        title = info.get("title") if isinstance(info, dict) else None
        run.ok("chat_reachable", "The bot can see the approval chat", f"{kind}{f' “{title}”' if title else ''}")
        run.evidence["chat"] = f"{kind}{f' “{title}”' if title else ''}"
    except Unreachable:
        run.fail("reachable", "Telegram is reachable", "telegram.unreachable")
        return run.finish()

    if depth != "deep":
        run.skip("delivery", "A test message arrives", "Not run: use 'Send test message' to check delivery.", depth="deep")
        return run.finish()
    if run.failed:
        return run.finish()
    try:
        _, err = _call(token, "sendMessage", chat_id=int(chat), text=TEST_TEXT, disable_notification=False)
    except Unreachable:
        err = "telegram.unreachable"
    if err:
        run.fail("delivery", "A test message was sent", err, depth="deep")
    else:
        run.ok("delivery", "A test message was sent", "Telegram accepted it; check that it arrived", depth="deep")
    return run.finish()


def detect_chats(token: str) -> tuple[list[dict], str | None]:
    """Chats that recently messaged the bot (newest first), read without confirming any update.

    Returns (chats, error_code). Each chat: {id, type, title}. Never advances the getUpdates offset.
    """
    if not TOKEN_RE.match(token or ""):
        return [], "telegram.token_format"
    try:
        hook, err = _call(token, "getWebhookInfo")
        if err:
            return [], err
        if isinstance(hook, dict) and hook.get("url"):
            return [], "telegram.webhook_set"
        # No `offset` (confirms nothing), no `allowed_updates` (keeps the bot's setting), short poll.
        updates, err = _call(token, "getUpdates", limit=100, timeout=0)
    except Unreachable:
        return [], "telegram.unreachable"
    if err:
        return [], err
    seen: dict[int, dict] = {}
    for u in reversed(updates if isinstance(updates, list) else []):
        msg = (u or {}).get("message") or (u or {}).get("my_chat_member") or {}
        chat = msg.get("chat") if isinstance(msg, dict) else None
        if not isinstance(chat, dict) or not isinstance(chat.get("id"), int) or chat["id"] in seen:
            continue
        name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or None
        seen[chat["id"]] = {"id": str(chat["id"]), "type": chat.get("type") or "chat", "title": name}
    if not seen:
        return [], "telegram.no_chat_found"
    return list(seen.values()), None


def delete_webhook(token: str) -> str | None:
    """Remove a webhook so polling works again (explicit, confirmed click only). Pending updates are kept."""
    if not TOKEN_RE.match(token or ""):
        return "telegram.token_format"
    try:
        _, err = _call(token, "deleteWebhook", drop_pending_updates=False)
    except Unreachable:
        return "telegram.unreachable"
    return err
