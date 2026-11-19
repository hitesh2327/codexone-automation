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

from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
import requests
from starlette.responses import RedirectResponse

from api.app.deps import CurrentUser, current_user
from api.app.ratelimit import RateLimiter
from api.app.settings import settings
from src import activity, approve_bot, db, user_config_store
from src.config import get_env
from src.config_schema import FIELDS_BY_NAME, PER_USER_FIELD_NAMES
from src.db.models import Setting
from src.logger import get_logger
from src.verify import CODES
from src.verify import telegram as tg
from src.verify.base import Unreachable, clean_value

log = get_logger("integrations")

router = APIRouter(prefix="/integrations", tags=["integrations"])
public_router = APIRouter(prefix="/integrations", tags=["integrations"])

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


def _effective_yt_client(user_id: int) -> tuple[str | None, str | None]:
    """Return (client_id, client_secret) for YouTube OAuth."""
    custom_id = user_config_store.lookup("YT_CLIENT_ID", user_id)
    custom_sec = user_config_store.lookup("YT_CLIENT_SECRET", user_id)
    client_id = (
        custom_id
        or get_env("YT_OAUTH_CLIENT_ID", required=False)
        or get_env("GOOGLE_WEB_CLIENT_ID", required=False)
    )
    client_secret = (
        custom_sec
        or get_env("YT_OAUTH_CLIENT_SECRET", required=False)
        or get_env("GOOGLE_WEB_CLIENT_SECRET", required=False)
    )
    return client_id, client_secret


def _sign_oauth_state(user_id: int, provider: str = "youtube") -> str:
    nonce = secrets.token_urlsafe(16)
    ts = int(time.time())
    payload = f"{user_id}:{provider}:{ts}:{nonce}"
    sig = hmac.new(settings().jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    db.set_setting(f"oauth_state:{nonce}", {"user_id": user_id, "provider": provider, "ts": ts})
    return f"{payload}:{sig}"


def _verify_oauth_state(state_str: str, expected_provider: str = "youtube") -> int | None:
    parts = state_str.split(":")
    if len(parts) != 5:
        return None
    user_id_str, provider, ts_str, nonce, sig = parts
    payload = f"{user_id_str}:{provider}:{ts_str}:{nonce}"
    expected_sig = hmac.new(settings().jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected_sig):
        return None
    if provider != expected_provider:
        return None
    try:
        ts = int(ts_str)
        if time.time() - ts > 900:  # 15 min TTL
            return None
    except ValueError:
        return None
    stored = db.get_setting(f"oauth_state:{nonce}")
    if not stored:
        return None
    db.set_setting(f"oauth_state:{nonce}", None)  # Prevent replay attacks
    return int(user_id_str)


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
    token, _ = _effective_tg_token(cu.id)
    bot_name = None
    bot_username = None
    if token and tg.TOKEN_RE.match(token):
        info, _ = tg.get_bot_info(token)
        if isinstance(info, dict) and info.get("username"):
            bot_username = f"@{str(info['username']).lstrip('@')}"
        saved_name = db.get_setting(f"tg_bot_name:{cu.id}")
        if saved_name and isinstance(saved_name, str):
            bot_name = saved_name
        else:
            name, _ = tg.get_bot_name(token)
            if name and "codexonebyhitesh" not in name.lower():
                bot_name = name
            elif isinstance(info, dict) and info.get("first_name") and "codexonebyhitesh" not in str(info.get("first_name")).lower():
                bot_name = info.get("first_name")
            else:
                bot_name = None

    yt_token = data.get("YT_REFRESH_TOKEN")
    yt_channel = db.get_setting(f"yt_channel:{cu.id}") or {}
    if not isinstance(yt_channel, dict):
        yt_channel = {}
    yt_client_id, yt_client_sec = _effective_yt_client(cu.id)
    yt_privacy = data.get("YT_PRIVACY") or "public"

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
            "bot_name": bot_name,
            "bot_username": bot_username,
        },
        "youtube": {
            "connected": bool(yt_token),
            "channel_id": yt_channel.get("id"),
            "channel_title": yt_channel.get("title"),
            "channel_handle": yt_channel.get("handle"),
            "channel_thumb": yt_channel.get("thumb"),
            "privacy": yt_privacy,
            "oauth_configured": bool(yt_client_id and yt_client_sec),
        },
    }



class CreateTelegramLinkBody(BaseModel):
    bot_name: str | None = Field(default=None, max_length=64)


@router.post("/telegram/link")
def create_telegram_link(body: CreateTelegramLinkBody | None = Body(default=None), cu: CurrentUser = Depends(current_user)) -> dict:
    """Create a single-use deep link https://t.me/<bot>?start=<nonce> scoped strictly to `cu.id`."""
    _rate(cu)
    token, is_custom = _effective_tg_token(cu.id)
    if not token:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.not_configured",
                    "message": "No Telegram bot is configured yet. Paste your own BotFather token or ask the owner to set Mintly's bot."},
        )
    if not tg.TOKEN_RE.match(token):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message},
        )
    if body and body.bot_name and body.bot_name.strip():
        clean_name = body.bot_name.strip()
        try:
            tg.set_bot_name(token, clean_name)
            db.set_setting(f"tg_bot_name:{cu.id}", clean_name)
        except Exception as set_err:
            log.warning("failed to set bot name on link creation: %s", set_err)
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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status.HTTP_422_UNPROCESSABLE_CONTENT if err == "telegram.webhook_set" else status.HTTP_502_BAD_GATEWAY,
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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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


class TelegramNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


@router.put("/telegram/name")
def update_telegram_bot_name(body: TelegramNameRequest, cu: CurrentUser = Depends(current_user)) -> dict:
    """Change the Telegram bot display name via setMyName."""
    _rate(cu)
    token, is_custom = _effective_tg_token(cu.id)
    if not is_custom and cu.role not in ("owner", "admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Only administrators can change the shared platform bot name."},
        )
    if not token:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.not_configured",
                    "message": "No Telegram bot is configured yet. Paste your own BotFather token or ask the owner to set Mintly's bot."},
        )
    if not tg.TOKEN_RE.match(token):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message},
        )
    clean_name = body.name.strip()
    if not clean_name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.invalid_name", "message": "Bot name cannot be empty."},
        )
    if len(clean_name) > 64:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "telegram.invalid_name", "message": "Bot name cannot exceed 64 characters."},
        )

    ok, err = tg.set_bot_name(token, clean_name)
    if not ok or err:
        code = err or "telegram.unavailable"
        if code == "telegram.unreachable":
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail={"code": code, "message": CODES["telegram.unreachable"].message},
            )
        info = CODES.get(code)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": code, "message": info.message if info else f"Telegram rejected the bot name: {code}"},
        )

    db.set_setting(f"tg_bot_name:{cu.id}", clean_name)
    return {
        "ok": True,
        "bot_name": clean_name,
        "message": f"Telegram bot name updated to '{clean_name}'",
    }


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram(include_bot: bool = Query(False), cu: CurrentUser = Depends(current_user)) -> None:
    """Unlink Telegram chat (and optionally remove custom TG_BOT_TOKEN override) for `cu.id`."""
    user_config_store.delete(cu.id, "TG_CHAT_ID")
    if include_bot:
        user_config_store.delete(cu.id, "TG_BOT_TOKEN")
    db.set_setting(f"tg_bot_name:{cu.id}", None)
    with db.session() as s:
        if row := s.get(Setting, _link_key(cu.id)):
            s.delete(row)


# --------------------------------------------------------------------------- #
# YouTube 1-Click OAuth Connect, Callback, and Disconnect
# --------------------------------------------------------------------------- #
@router.post("/youtube/link")
def create_youtube_link(cu: CurrentUser = Depends(current_user)) -> dict:
    """Generate a 1-click Google OAuth URL to link the user's YouTube channel."""
    client_id, client_secret = _effective_yt_client(cu.id)
    if not client_id or not client_secret:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "youtube.not_configured",
                "message": "YouTube OAuth is not configured on the server. Please contact an administrator or provide custom credentials.",
            },
        )
    pub_url = settings().public_url.rstrip("/")
    redirect_uri = f"{pub_url}/api/integrations/youtube/callback"
    state = _sign_oauth_state(cu.id, "youtube")
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": auth_url, "expires_in": 900}


@public_router.get("/youtube/callback")
def youtube_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google OAuth callback: exchanges authorization code for refresh token and retrieves channel snippet."""
    pub_url = settings().public_url.rstrip("/")
    if error:
        log.warning("youtube oauth user error: %s", error)
        return RedirectResponse(f"{pub_url}/config?error=youtube_{quote(str(error))}", status_code=303)
    if not code or not state:
        return RedirectResponse(f"{pub_url}/config?error=youtube_invalid_callback", status_code=303)

    user_id = _verify_oauth_state(state, "youtube")
    if not user_id:
        return RedirectResponse(f"{pub_url}/config?error=youtube_state_expired", status_code=303)

    client_id, client_secret = _effective_yt_client(user_id)
    if not client_id or not client_secret:
        return RedirectResponse(f"{pub_url}/config?error=youtube_not_configured", status_code=303)

    redirect_uri = f"{pub_url}/api/integrations/youtube/callback"
    token_url = "https://oauth2.googleapis.com/token"
    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    try:
        resp = requests.post(token_url, data=token_payload, timeout=15)
        token_data = resp.json()
    except Exception as e:
        log.error("youtube oauth token exchange network error: %s", e)
        return RedirectResponse(f"{pub_url}/config?error=youtube_network_error", status_code=303)

    if resp.status_code != 200 or "access_token" not in token_data:
        log.error("youtube oauth token exchange failed: %s %s", resp.status_code, token_data)
        return RedirectResponse(f"{pub_url}/config?error=youtube_auth_failed", status_code=303)

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    if not refresh_token:
        existing_ref = user_config_store.lookup("YT_REFRESH_TOKEN", user_id)
        if existing_ref:
            refresh_token = existing_ref

    if not refresh_token:
        log.error("youtube oauth did not return refresh_token and none was stored for user %s", user_id)
        return RedirectResponse(f"{pub_url}/config?error=youtube_missing_refresh_token", status_code=303)

    # Fetch YouTube channel info
    channel_id = ""
    channel_title = ""
    channel_handle = ""
    channel_thumb = ""
    try:
        ch_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if ch_resp.status_code == 200:
            items = ch_resp.json().get("items") or []
            if not items:
                return RedirectResponse(f"{pub_url}/config?error=no_youtube_channel", status_code=303)
            first = items[0]
            channel_id = first.get("id") or ""
            snip = first.get("snippet") or {}
            channel_title = snip.get("title") or ""
            channel_handle = snip.get("customUrl") or ""
            channel_thumb = snip.get("thumbnails", {}).get("default", {}).get("url") or ""
    except Exception as e:
        log.warning("failed to fetch youtube channel metadata: %s", e)

    # Persist credentials and metadata
    user_config_store.save(user_id, {"YT_REFRESH_TOKEN": refresh_token}, actor=f"user {user_id}")
    db.set_setting(f"yt_channel:{user_id}", {
        "id": channel_id,
        "title": channel_title,
        "handle": channel_handle,
        "thumb": channel_thumb,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    })
    activity.record(
        "integration.youtube.connected",
        f"Connected YouTube channel '{channel_title}' ({channel_handle or channel_id})",
        source="integrations",
        actor=f"user {user_id}",
    )
    return RedirectResponse(f"{pub_url}/config?connected=youtube", status_code=303)


@router.delete("/youtube", status_code=status.HTTP_204_NO_CONTENT)
def unlink_youtube(cu: CurrentUser = Depends(current_user)) -> None:
    """Unlink YouTube channel and revoke stored refresh token."""
    token = user_config_store.lookup("YT_REFRESH_TOKEN", cu.id)
    user_config_store.delete(cu.id, "YT_REFRESH_TOKEN")
    db.set_setting(f"yt_channel:{cu.id}", None)
    if token:
        try:
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=5)
        except Exception:
            pass
    activity.record("integration.youtube.unlinked", "Unlinked YouTube channel", source="integrations", actor=_actor(cu))


class PutBody(BaseModel):
    value: str = Field(min_length=1, max_length=2000)


@router.put("/{key}")
def put_integration(key: str, body: PutBody, cu: CurrentUser = Depends(current_user)) -> dict:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    if key == "TG_CHAT_ID":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "telegram.direct_bind_disallowed",
                "message": "TG_CHAT_ID cannot be set directly. Connect Telegram via 1-click verification (/telegram/link).",
            },
        )
    val = clean_value(body.value, key)[0]
    if key == "TG_BOT_TOKEN" and not tg.TOKEN_RE.match(val):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={"code": "telegram.token_format", "message": CODES["telegram.token_format"].message})
    versions = user_config_store.save(cu.id, {key: val}, actor=_actor(cu))
    return {"key": key, "version": versions[key]}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(key: str, cu: CurrentUser = Depends(current_user)) -> None:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    user_config_store.delete(cu.id, key)
