"""Per-user integration config: Telegram 1-click connect/unlink/bot override, Instagram, YouTube.

GET    /api/integrations                  -> list all per-user keys with masked values + telegram metadata
POST   /api/integrations/telegram/link    -> generate 1-click t.me/<bot>?start=<nonce> deep link
POST   /api/integrations/telegram/confirm -> verify /start <nonce> and bind TG_CHAT_ID to current user
PUT    /api/integrations/telegram/bot     -> save & verify a per-user custom TG_BOT_TOKEN override
DELETE /api/integrations/telegram         -> unlink TG_CHAT_ID (and optionally TG_BOT_TOKEN)
PUT    /api/integrations/{key}            -> save one key (body: {value: str})
DELETE /api/integrations/{key}            -> remove one key

Only keys in PER_USER_FIELD_NAMES are accepted.
Mounted under /api (signed in + CSRF on writes).
"""
from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.app.deps import CurrentUser, current_user
from api.app.ratelimit import RateLimiter
from src import approve_bot, db, user_config_store
from src.config import get_env
from src.config_schema import FIELDS_BY_NAME, PER_USER_FIELD_NAMES
from src.db.models import Setting
from src.verify import CODES
from src.verify import telegram as tg
from src.verify.base import Unreachable, clean_value

router = APIRouter(prefix="/integrations", tags=["integrations"])

limiter = RateLimiter()
TG_RATE_LIMIT, TG_RATE_WINDOW = 20, 60
LINK_TTL_SECONDS = 900


def _actor(cu: CurrentUser) -> str:
    return cu.username or cu.email or f"user {cu.id}"


def _mask(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    f = FIELDS_BY_NAME.get(key)
    if f and f.secret:
        return f"***{value[-4:]}" if len(value) > 4 else "****"
    return value


def _link_key(user_id: int) -> str:
    return f"tg_link:{user_id}"


def _bot_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _effective_tg_token(user_id: int) -> tuple[str | None, bool]:
    """Return (bot_token, is_custom) for `user_id`."""
    custom = user_config_store.lookup("TG_BOT_TOKEN", user_id)
    if custom:
        return custom, True
    return get_env("TG_BOT_TOKEN", required=False), False


def _rate(cu: CurrentUser) -> None:
    key = f"tg_int:{cu.id}"
    if wait := limiter.retry_after(key, TG_RATE_LIMIT, TG_RATE_WINDOW):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many Telegram requests. Wait a moment."},
            headers={"Retry-After": str(wait)},
        )
    limiter.hit(key)


@router.get("")
def list_integrations(cu: CurrentUser = Depends(current_user)) -> dict:
    data = user_config_store.snapshot(cu.id)
    default_bot_ok = bool(get_env("TG_BOT_TOKEN", required=False))
    return {
        "values": {
            k: {"set": data.get(k) is not None, "masked": _mask(k, data.get(k))}
            for k in PER_USER_FIELD_NAMES
            if (f := FIELDS_BY_NAME.get(k)) and not f.advanced
        },
        "telegram": {
            "connected": bool(data.get("TG_CHAT_ID")),
            "using_custom_bot": bool(data.get("TG_BOT_TOKEN")),
            "default_bot_configured": default_bot_ok,
        },
    }


@router.post("/telegram/link")
def create_telegram_link(cu: CurrentUser = Depends(current_user)) -> dict:
    """Create a single-use deep link https://t.me/<bot>?start=<nonce> scoped strictly to `cu.id`."""
    _rate(cu)
    token, is_custom = _effective_tg_token(cu.id)
    if not token:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "telegram.not_configured",
                    "message": "No Telegram bot is configured yet. Paste your own BotFather token or ask the owner to set Mintly's bot."},
        )
    if not tg.TOKEN_RE.match(token):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message},
        )
    try:
        me, err = tg._call(token, "getMe")
    except Unreachable:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"code": "telegram.unreachable", "message": CODES["telegram.unreachable"].message},
        ) from None
    if err or not isinstance(me, dict) or not me.get("username"):
        code = err or "telegram.token_rejected"
        info = CODES.get(code)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": code, "message": info.message if info else "Telegram rejected the bot token."},
        )

    nonce = secrets.token_urlsafe(16)
    expires_at = time.time() + LINK_TTL_SECONDS
    db.set_setting(_link_key(cu.id), {
        "nonce": nonce,
        "expires_at": expires_at,
        "bot_hash": _bot_hash(token),
    })
    username = str(me["username"]).lstrip("@")
    return {
        "url": f"https://t.me/{username}?start={nonce}",
        "bot_username": f"@{username}",
        "using_custom_bot": is_custom,
        "expires_in": LINK_TTL_SECONDS,
    }


@router.post("/telegram/confirm")
def confirm_telegram_link(cu: CurrentUser = Depends(current_user)) -> dict:
    """Poll the bot for `/start <nonce>` issued to `cu.id` and bind TG_CHAT_ID to `cu.id` only."""
    _rate(cu)
    pending = db.get_setting(_link_key(cu.id))
    if not isinstance(pending, dict) or float(pending.get("expires_at") or 0) < time.time():
        with db.session() as s:
            if row := s.get(Setting, _link_key(cu.id)):
                s.delete(row)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "telegram.link_expired", "message": "Telegram link session expired. Click Connect Telegram again."},
        )

    # Background poll() may have already bound this user's /start <nonce>.
    if bound := pending.get("bound_chat_id"):
        with db.session() as s:
            if row := s.get(Setting, _link_key(cu.id)):
                s.delete(row)
        return {"connected": True, "chat_id": str(bound), "chat_title": None}

    token, _ = _effective_tg_token(cu.id)
    if not token or (pending.get("bot_hash") and pending.get("bot_hash") != _bot_hash(token)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "telegram.bot_changed", "message": "Bot changed during setup. Click Connect Telegram again."},
        )

    chat, err = approve_bot.find_start_chat(token, str(pending["nonce"]))
    if err:
        info = CODES.get(err)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY if err == "telegram.webhook_set" else status.HTTP_502_BAD_GATEWAY,
            detail={"code": err, "message": info.message if info else "Couldn't check Telegram updates."},
        )
    if not chat:
        return {"connected": False}

    user_config_store.save(cu.id, {"TG_CHAT_ID": chat["id"]}, actor=_actor(cu))
    with db.session() as s:
        if row := s.get(Setting, _link_key(cu.id)):
            s.delete(row)
    return {"connected": True, "chat_id": chat["id"], "chat_title": chat.get("title")}


class BotBody(BaseModel):
    token: str = Field(min_length=1, max_length=2000)


@router.put("/telegram/bot")
def set_custom_telegram_bot(body: BotBody, cu: CurrentUser = Depends(current_user)) -> dict:
    """Validate and save a per-user custom TG_BOT_TOKEN override."""
    _rate(cu)
    token = clean_value(body.token, "TG_BOT_TOKEN")[0]
    if not tg.TOKEN_RE.match(token):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message},
        )
    try:
        me, err = tg._call(token, "getMe")
    except Unreachable:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"code": "telegram.unreachable", "message": CODES["telegram.unreachable"].message},
        ) from None
    if err or not isinstance(me, dict) or not me.get("username"):
        code = err or "telegram.token_rejected"
        info = CODES.get(code)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": code, "message": info.message if info else "Telegram rejected that bot token."},
        )

    user_config_store.save(cu.id, {"TG_BOT_TOKEN": token}, actor=_actor(cu))
    with db.session() as s:
        if row := s.get(Setting, _link_key(cu.id)):
            s.delete(row)
    return {
        "ok": True,
        "bot_username": f"@{str(me['username']).lstrip('@')}",
        "masked": _mask("TG_BOT_TOKEN", token),
    }


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram(include_bot: bool = Query(False), cu: CurrentUser = Depends(current_user)) -> None:
    """Unlink Telegram chat (and optionally remove custom TG_BOT_TOKEN override) for `cu.id`."""
    user_config_store.delete(cu.id, "TG_CHAT_ID")
    if include_bot:
        user_config_store.delete(cu.id, "TG_BOT_TOKEN")
    with db.session() as s:
        if row := s.get(Setting, _link_key(cu.id)):
            s.delete(row)


class PutBody(BaseModel):
    value: str = Field(min_length=1, max_length=2000)


@router.put("/{key}")
def put_integration(key: str, body: PutBody, cu: CurrentUser = Depends(current_user)) -> dict:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    val = clean_value(body.value, key)[0]
    if key == "TG_BOT_TOKEN" and not tg.TOKEN_RE.match(val):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message})
    if key == "TG_CHAT_ID" and not tg.CHAT_RE.match(val):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "telegram.chat_format", "message": CODES["telegram.chat_format"].message})
    versions = user_config_store.save(cu.id, {key: val}, actor=_actor(cu))
    return {"key": key, "version": versions[key]}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(key: str, cu: CurrentUser = Depends(current_user)) -> None:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    user_config_store.delete(cu.id, key)
