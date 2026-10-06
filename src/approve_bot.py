"""Telegram approval flow without a server.

send_preview(): posts the carousel (album + control message) or reel (video) to
TG_CHAT_ID, each with inline buttons Approve / Reject / Regenerate.

poll(): calls getUpdates (no webhook needed), applies button presses to the queue,
and stores text replies to a preview as feedback for Regenerate. Run it on a
schedule (GitHub Actions every 15 min). Only presses from TG_CHAT_ID count.

Usage:
    python -m src.approve_bot preview output/<date>/<slug> [--only carousel|reel] [--dry-run]
    python -m src.approve_bot poll [--dry-run]
    python -m src.approve_bot status
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
import io
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import requests
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut

from src import activity, db
from src import queue_store as q
from src.config import DATA_DIR, ROOT, get_env, load_brand
from src.gen_content import Content
from src.logger import get_logger
from src.redact import redact

log = get_logger("approve_bot")
OFFSET_FILE = DATA_DIR / "tg_offset.json"
IST = timezone(timedelta(hours=5, minutes=30))
ACTIONS = {"approve": "✅ Approve", "reject": "❌ Reject", "regen": "🔄 Regenerate"}


def sync_enabled() -> bool:
    """TELEGRAM_SYNC=false turns off every Telegram call (local dashboard development)."""
    return (get_env("TELEGRAM_SYNC", required=False, default="true") or "true").lower() not in ("0", "false", "no")


def _chat_id() -> int:
    return int(get_env("TG_CHAT_ID"))


def _bot() -> Bot:
    return Bot(get_env("TG_BOT_TOKEN"))


def keyboard(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"{a}:{item_id}")
                                  for a, label in ACTIONS.items()]])


def post_times() -> list[dtime]:
    """Posting slots from brand/config.yaml (post_times_ist, or legacy post_time_ist)."""
    b = load_brand()
    raw = b.get("post_times_ist") or [b.get("post_time_ist", "19:00")]
    return sorted(dtime(*(int(x) for x in t.split(":"))) for t in raw)


def slot_at(day: str, hhmm: str) -> datetime:
    """The given IST slot on `day` (YYYY-MM-DD)."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(datetime.fromisoformat(day).date(), dtime(hh, mm), IST)


def next_slot(now: datetime | None = None, lead: timedelta = timedelta(minutes=30)) -> datetime:
    """First posting slot at least `lead` after now (today or tomorrow)."""
    now = now or datetime.now(IST)
    for days in (0, 1):
        d = (now + timedelta(days=days)).date()
        for t in post_times():
            at = datetime.combine(d, t, IST)
            if at >= now + lead:
                return at
    raise RuntimeError("no posting slot configured")


def item_publish_at(item: q.Item) -> datetime:
    if item.publish_at:
        return datetime.fromisoformat(item.publish_at)
    return datetime.combine(datetime.fromisoformat(item.date).date(), post_times()[-1], IST)


def full_caption(content: Content) -> str:
    return f"{content.caption.strip()}\n\n{' '.join(content.hashtags)}"


# --------------------------------------------------------------------------- #
# Build queue items from a rendered + uploaded post
# --------------------------------------------------------------------------- #
def items_from_post(post_dir: Path, only: str | None = None, source_url: str = "",
                    angle: str = "", day: str | None = None, slug: str | None = None,
                    version: int = 1, publish_at: datetime | None = None,
                    voice: str = "") -> list[q.Item]:
    content = Content.model_validate_json((post_dir / "content.json").read_text(encoding="utf-8"))
    media = json.loads((post_dir / "media.json").read_text(encoding="utf-8"))
    day = day or post_dir.parent.name
    slug = slug or post_dir.name
    out = []
    for kind in ("carousel", "reel"):
        if only and kind != only:
            continue
        if kind == "carousel" and not media.get("carousel"):
            continue
        if kind == "reel" and not media.get("reel"):
            continue
        out.append(q.Item(
            id=q.make_id(day, kind, slug, version), kind=kind, date=day,
            topic=content.topic, category=content.category, source_url=source_url, angle=angle,
            post_dir=post_dir.resolve().relative_to(ROOT).as_posix(),
            caption=full_caption(content), version=version,
            publish_at=publish_at.isoformat() if publish_at else None,
            voice=voice if kind == "reel" else "",
            media={k: v for k, v in media.items()
                   if (kind == "carousel" and k == "carousel") or (kind == "reel" and k in ("reel", "cover"))},
        ))
    return out


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def _control_text(item: q.Item, max_caption: int = 3500) -> str:
    """HTML text for the control message. Truncate BEFORE escaping so tags stay intact.

    Video captions are limited to 1024 chars, so reels pass a smaller max_caption.
    """
    kind = "🖼 CAROUSEL" if item.kind == "carousel" else "🎬 REEL"
    ver = f" · v{item.version}" if item.version > 1 else ""
    cap = item.caption if len(item.caption) <= max_caption else item.caption[:max_caption].rstrip() + "…"
    at = item_publish_at(item)
    when = (f"🕒 Posts as soon as you approve (the {at:%H:%M} IST slot has passed)\n"
            if datetime.now(IST) > at else
            f"🕒 Posts {at:%a %d %b, %H:%M} IST after approval\n")
    if item.voice:  # e.g. en-US-AndrewMultilingualNeural -> Andrew
        name = item.voice.split("-")[2].replace("Multilingual", "").replace("Neural", "")
        when += f"🎙 Voice: {name}\n"
    if item.version > 1 and item.feedback:
        when += f"📝 Applied feedback: {html.escape(item.feedback[:300])}\n"
    return (f"<b>{kind} · {html.escape(item.category)}{ver}</b>\n"
            f"<b>{html.escape(item.topic)}</b>\n{when}\n{html.escape(cap)}\n\n"
            f"<i>Reply to this message with feedback, then tap Regenerate to apply it.</i>\n"
            f"<code>{item.id}</code>")


def _download(url: str) -> io.BytesIO:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    buf = io.BytesIO(r.content)
    buf.name = url.rsplit("/", 1)[-1].split("?")[0] or "media"
    return buf


async def _with_upload_fallback(send, url: str):
    """Send media by URL; if Telegram can't fetch it (webpage_curl_failed, >20MB, slow host),
    download it ourselves and upload the bytes instead."""
    try:
        return await send(url)
    except BadRequest as e:
        log.warning("Telegram could not fetch %s (%s); uploading the file instead", url, e)
        data = await asyncio.to_thread(_download, url)
        return await send(data)


async def _send_preview(item: q.Item) -> q.Item:
    chat = _chat_id()
    async with _bot() as bot:
        ids: list[int] = []
        if item.kind == "carousel":
            urls = item.media["carousel"][:10]

            async def send_album(media):
                return await bot.send_media_group(chat, [InputMediaPhoto(m) for m in media])

            try:
                msgs = await send_album(urls)
            except BadRequest as e:
                log.warning("Telegram could not fetch the carousel URLs (%s); uploading files instead", e)
                files = [await asyncio.to_thread(_download, u) for u in urls]
                msgs = await send_album(files)
            ids += [m.message_id for m in msgs]
            ctrl = await bot.send_message(chat, _control_text(item), parse_mode=ParseMode.HTML,
                                          reply_markup=keyboard(item.id))
        else:
            async def send_reel(video):
                return await bot.send_video(chat, video, supports_streaming=True,
                                            caption=_control_text(item, max_caption=600),
                                            parse_mode=ParseMode.HTML, reply_markup=keyboard(item.id))

            ctrl = await _with_upload_fallback(send_reel, item.media["reel"])
        ids.append(ctrl.message_id)
        item.tg_message_ids, item.tg_control_id = ids, ctrl.message_id
    return item


def send_preview(item: q.Item, dry_run: bool = False) -> q.Item:
    if dry_run:
        log.info("[dry-run] would send %s preview %s: %s", item.kind, item.id, item.topic)
        return item
    item = asyncio.run(_send_preview(item))
    q.upsert(item)
    log.info("sent %s preview %s (message %s)", item.kind, item.id, item.tg_control_id)
    return item


async def _notify(text: str, reply_to: int | None = None) -> None:
    async with _bot() as bot:
        await bot.send_message(_chat_id(), text, parse_mode=ParseMode.HTML,
                               reply_to_message_id=reply_to, disable_web_page_preview=True)


def notify(text: str, reply_to: int | None = None, dry_run: bool = False) -> None:
    text = redact(text)  # callers forward exception text, which can carry a token-bearing URL
    if dry_run or not sync_enabled():
        log.info("[%s] would notify: %s", "dry-run" if dry_run else "telegram sync off", text)
        return
    try:
        asyncio.run(_notify(text, reply_to))
    except TelegramError as e:
        log.error("Telegram notify failed: %s", e)


# --------------------------------------------------------------------------- #
# Keeping Telegram in sync with decisions made in the dashboard
# --------------------------------------------------------------------------- #
async def _mark_decided(item: q.Item, note: str) -> None:
    async with _bot() as bot:
        await _safe(bot.edit_message_reply_markup(_chat_id(), item.tg_control_id, reply_markup=None))
        await _safe(bot.send_message(_chat_id(), note, reply_to_message_id=item.tg_control_id))


def mark_decided(item: q.Item, note: str) -> None:
    """Remove the preview's buttons and reply with what happened (e.g. approved in the dashboard)."""
    if not item.tg_control_id or not sync_enabled():
        return
    try:
        asyncio.run(_mark_decided(item, note))
    except TelegramError as e:
        log.warning("Telegram sync failed for %s: %s", item.id, e)


async def _refresh_preview(item: q.Item) -> None:
    async with _bot() as bot:
        markup = keyboard(item.id) if item.status == "pending" else None
        if item.kind == "carousel":
            await _safe(bot.edit_message_text(_control_text(item), _chat_id(), item.tg_control_id,
                                              parse_mode=ParseMode.HTML, reply_markup=markup))
        else:
            await _safe(bot.edit_message_caption(_chat_id(), item.tg_control_id,
                                                 caption=_control_text(item, max_caption=600),
                                                 parse_mode=ParseMode.HTML, reply_markup=markup))


def refresh_preview(item: q.Item) -> None:
    """Re-render the preview's text after an edit (caption, schedule...), keeping the buttons."""
    if not item.tg_control_id or not sync_enabled():
        return
    try:
        asyncio.run(_refresh_preview(item))
    except TelegramError as e:
        log.warning("Telegram preview refresh failed for %s: %s", item.id, e)


def decision_note(action: str, item: q.Item, source: str = "") -> str:
    return _decision_note(action, item) + (f" ({source})" if source else "")


# --------------------------------------------------------------------------- #
# Polling for decisions
# --------------------------------------------------------------------------- #
def _load_offset() -> int | None:
    if db.enabled():
        return (db.get_setting("tg_offset") or {}).get("offset")
    try:
        return json.loads(OFFSET_FILE.read_text(encoding="utf-8"))["offset"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def _save_offset(offset: int) -> None:
    if db.enabled():
        db.set_setting("tg_offset", {"offset": offset})
        return
    OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def _decision_note(action: str, item: q.Item) -> str:
    if action == "approve":
        at = item_publish_at(item)
        when = f"at {at:%H:%M} IST ({at:%a %d %b})" if datetime.now(IST) < at else "within ~20 minutes"
        return f"✅ Approved — will publish {when}."
    if action == "reject":
        return "❌ Rejected — will not be published."
    return "🔄 Regenerating — a new preview will follow."


async def _poll(dry_run: bool) -> list[tuple[str, str]]:
    chat = _chat_id()
    applied: list[tuple[str, str]] = []
    changed: dict[str, q.Item] = {}
    items = {i.id: i for i in q.load()}
    by_msg = {mid: i for i in items.values() for mid in i.tg_message_ids}
    offset = _load_offset()

    async with _bot() as bot:
        updates = await bot.get_updates(offset=offset, timeout=0,
                                        allowed_updates=["callback_query", "message"])
        for u in updates:
            offset = u.update_id + 1
            cq, msg = u.callback_query, u.message

            if cq and cq.data and cq.message and cq.message.chat.id == chat:
                action, _, item_id = cq.data.partition(":")
                item = items.get(item_id)
                if not item or action not in ACTIONS:
                    continue
                if item.status != "pending":  # e.g. already decided in the dashboard
                    await _safe(bot.answer_callback_query(cq.id, f"Already {item.status}."))
                    continue
                q.apply_decision(item, action)
                changed[item.id] = item
                applied.append((item.id, item.status))
                log.info("%s → %s", item.id, item.status)
                if not dry_run:
                    activity.record("post." + {"approve": "approved", "reject": "rejected", "regen": "regenerate"}[action],
                                    f"{ACTIONS[action][2:]} chosen in Telegram for {item.kind} “{item.topic}”",
                                    source="telegram", actor="telegram", post_id=item.id)
                    await _safe(bot.answer_callback_query(cq.id, item.status.capitalize()))
                    await _safe(bot.edit_message_reply_markup(chat, cq.message.message_id, reply_markup=None))
                    await _safe(bot.send_message(chat, _decision_note(action, item),
                                                 reply_to_message_id=cq.message.message_id))

            elif msg and msg.chat.id == chat and msg.text and msg.reply_to_message:
                item = by_msg.get(msg.reply_to_message.message_id)
                if item and item.status == "pending":
                    item.feedback = (item.feedback + "\n" + msg.text).strip()
                    changed[item.id] = item
                    applied.append((item.id, "feedback"))
                    log.info("%s feedback: %s", item.id, msg.text)
                    if not dry_run:
                        activity.record("post.feedback", f"Feedback added in Telegram for {item.kind} “{item.topic}”",
                                        source="telegram", actor="telegram", post_id=item.id)
                    if not dry_run:
                        await _safe(bot.send_message(chat, "📝 Noted. Tap 🔄 Regenerate to apply it.",
                                                     reply_to_message_id=msg.message_id))

    if dry_run:
        log.info("[dry-run] %d updates seen, %d changes not saved", len(updates), len(applied))
        return applied
    if offset is not None:
        _save_offset(offset)
    if changed:  # only what this poll changed: never overwrite concurrent dashboard edits
        q.save(list(changed.values()))
    return applied


async def _safe(coro) -> None:
    """Non-critical Telegram calls (old callbacks can't be answered, etc.)."""
    try:
        await coro
    except BadRequest as e:
        log.debug("telegram: %s", e)


def poll(dry_run: bool = False, retries: int = 3) -> list[tuple[str, str]]:
    if not sync_enabled():
        log.info("TELEGRAM_SYNC is off: not reading Telegram")
        return []
    for attempt in range(1, retries + 1):
        try:
            applied = asyncio.run(_poll(dry_run))
            break
        except (TimedOut, NetworkError) as e:  # flaky network: safe to retry, offset not advanced
            if attempt == retries:
                raise
            log.warning("Telegram poll failed (%s); retrying (%d/%d)", e, attempt, retries)
            time.sleep(5 * attempt)
    log.info("poll: %d change(s)", len(applied))
    return applied


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Telegram approval bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("preview", help="queue a rendered+uploaded post and send its previews")
    p1.add_argument("post_dir", type=Path)
    p1.add_argument("--only", choices=["carousel", "reel"])
    p1.add_argument("--dry-run", action="store_true")
    p2 = sub.add_parser("poll", help="apply button presses / replies to the queue")
    p2.add_argument("--dry-run", action="store_true")
    sub.add_parser("status", help="print the queue")
    args = ap.parse_args(argv)

    if args.cmd == "preview":
        for item in items_from_post(args.post_dir, args.only):
            existing = q.get(item.id)
            if existing and existing.status != "pending":
                log.warning("%s already %s; not re-sending", item.id, existing.status)
                continue
            send_preview(item, args.dry_run)
    elif args.cmd == "poll":
        poll(args.dry_run)
    else:
        for i in q.load():
            print(f"{i.id}  {i.kind:<8} {i.status:<10} {i.topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
