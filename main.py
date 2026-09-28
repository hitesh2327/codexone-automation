"""codexonebyhitesh content pipeline.

Commands:
  generate       fetch → rank → write → render carousel + reel → upload → Telegram previews
  poll           apply Telegram button presses, then publish approved items that are due
  regenerate     rebuild items whose Regenerate button was pressed (sends new previews)
  needs-regen    print "true"/"false" (used by CI to skip installing Chromium when not needed)
  refresh-token  refresh the Instagram long-lived token
  status         print the approval queue

Every command accepts --dry-run (no files written, nothing sent or published).
Nothing is ever published without an Approve press in Telegram.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src import queue_store as q
from src.config import ensure_dirs
from src.logger import get_logger

log = get_logger("main")


LATE_LIMIT_HOURS = 2  # don't generate for a slot that passed longer ago than this


def cmd_generate(args) -> int:
    from src import approve_bot, fetch_topics, gen_content, rank_topics, render_post, render_reel, upload

    day = args.date
    # Which posting slot is this run for? Explicit --slot (CI passes it per trigger), else the next one.
    publish_at = (approve_bot.slot_at(day, args.slot) if args.slot else approve_bot.next_slot())
    log.info("slot: %s IST", f"{publish_at:%a %d %b %H:%M}")

    # Two schedulers can fire for the same slot (cron-job.org + GitHub's backup cron): only the
    # first one generates. A trigger arriving long after the slot is skipped as stale.
    # Compare instants, not strings: the DB returns the same slot as UTC ("13:30+00:00").
    if any(i.publish_at and datetime.fromisoformat(i.publish_at) == publish_at for i in q.load()) \
            and not args.force:
        log.info("slot %s already has a post queued; nothing to do", f"{publish_at:%d %b %H:%M}")
        return 0
    late = datetime.now(approve_bot.IST) - publish_at
    if late > timedelta(hours=LATE_LIMIT_HOURS) and not args.force:
        log.warning("slot %s passed %.1fh ago (limit %dh); skipping stale run",
                    f"{publish_at:%d %b %H:%M}", late.total_seconds() / 3600, LATE_LIMIT_HOURS)
        return 0

    fetch_topics.main(["--show", "0"] + (["--dry-run"] if args.dry_run else []))
    if args.dry_run and not (Path("data") / f"topics_{day}.json").exists():
        log.info("[dry-run] no saved topics for %s; stopping after fetch", day)
        return 0

    topic = rank_topics.rank(day, args.category, seed=f"{day}-{publish_at:%H%M}")
    log.info("topic: [%s] %s", topic.category, topic.title)
    content = gen_content.generate(topic)
    if args.dry_run:
        log.info("[dry-run] content generated (%d slides); not rendering/uploading/sending",
                 len(content.carousel))
        render_post.render_carousel(content, Path("."), dry_run=True)
        render_reel.render_reel(content, Path("."), dry_run=True)
        return 0

    post_dir = gen_content.save(content, day).parent
    render_post.render_carousel(content, post_dir / "carousel")
    voice = ""
    if not args.skip_reel:
        voice = render_reel.pick_voice()
        render_reel.render_reel(content, post_dir, args.music or render_reel._default_music(), voice=voice)
    upload.upload_post(post_dir)

    for item in approve_bot.items_from_post(post_dir, source_url=topic.source_url, angle=topic.angle,
                                            publish_at=publish_at, voice=voice):
        approve_bot.send_preview(item)
    return 0


EXPIRE_HOURS = 36  # Telegram only keeps unread updates for 24h, so older previews are stale


def expire_stale(dry_run: bool) -> None:
    from datetime import datetime, timedelta, timezone
    from src import approve_bot

    cutoff = datetime.now(timezone.utc) - timedelta(hours=EXPIRE_HOURS)
    for item in q.load():
        if item.status == "pending" and datetime.fromisoformat(item.created_at) < cutoff:
            log.info("expiring %s (no decision in %dh)", item.id, EXPIRE_HOURS)
            if dry_run:
                continue
            item.status = "expired"
            q.upsert(item)
            approve_bot.notify(f"⌛ No decision in {EXPIRE_HOURS}h — <code>{item.id}</code> expired "
                               "and will not be posted.", item.tg_control_id)


def cmd_poll(args) -> int:
    from src import approve_bot, publish

    approve_bot.poll(args.dry_run)
    expire_stale(args.dry_run)
    publish.publish_due(args.dry_run, publish.platforms_arg(args.platform))
    return 0


def cmd_regenerate(args) -> int:
    from src import approve_bot, gen_content, render_post, render_reel, upload
    from src.rank_topics import RankedTopic

    todo = [i for i in q.load() if i.status == "regenerate"]
    if not todo:
        log.info("nothing to regenerate")
        return 0
    for old in todo:
        version = old.version + 1
        log.info("regenerating %s (%s) as v%d", old.id, old.kind, version)
        if args.dry_run:
            continue
        topic = RankedTopic(category=old.category, title=old.topic, angle=old.angle or old.topic,
                            source_url=old.source_url, evergreen=not old.source_url, why="regenerate")
        feedback = "Write a clearly different version (new hook, examples and structure)."
        if old.feedback:
            feedback += f"\nReviewer feedback to apply: {old.feedback}"
        try:
            content = gen_content.generate(topic, feedback)
            slug = gen_content.slugify(old.topic)
            # per kind: carousel and reel regenerate separately and must not share content.json
            post_dir = gen_content.post_dir(old.date, old.topic) / f"v{version}-{old.kind}"
            post_dir.mkdir(parents=True, exist_ok=True)
            (post_dir / "content.json").write_text(content.model_dump_json(indent=2), encoding="utf-8")
            if old.kind == "carousel":
                render_post.render_carousel(content, post_dir / "carousel")
            else:
                voice = render_reel.voice_from_feedback(old.feedback) or render_reel.pick_voice()
                render_reel.render_reel(content, post_dir, render_reel._default_music(), voice=voice)
            upload.upload_post(post_dir, only=old.kind)
            new_items = approve_bot.items_from_post(post_dir, only=old.kind, source_url=old.source_url,
                                              angle=old.angle, day=old.date, slug=slug, version=version,
                                              publish_at=approve_bot.item_publish_at(old),
                                              voice=voice if old.kind == "reel" else "")
            new = new_items[0]
            new.feedback = old.feedback  # shown on the new preview as "Applied feedback"
            approve_bot.send_preview(new)
            old.status = "replaced"
            q.upsert(old)
        except Exception as e:  # keep status=regenerate so the next run retries
            log.exception("regenerate %s failed", old.id)
            approve_bot.notify(f"⚠️ Regenerate failed for <code>{old.id}</code>: {e}", old.tg_control_id)
    return 0


def cmd_needs_regen(args) -> int:
    needed = any(i.status == "regenerate" for i in q.load())
    print("true" if needed else "false")
    if out := os.getenv("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"needed={'true' if needed else 'false'}\n")
    return 0


def cmd_refresh(args) -> int:
    from src import refresh_token
    return refresh_token.main(["--dry-run"] if args.dry_run else [])


def cmd_status(args) -> int:
    for i in q.load():
        print(f"{i.id}  {i.kind:<8} {i.status:<10} {i.date}  {i.topic}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="codexonebyhitesh content pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create today's post and send Telegram previews")
    g.add_argument("--date", default=date.today().isoformat())
    g.add_argument("--category", help="force a category (AI, SystemDesign, DSA, Interview, OS, Dev)")
    g.add_argument("--slot", help="posting slot HH:MM IST this post is for (default: next slot)")
    g.add_argument("--force", action="store_true",
                   help="generate even if the slot already has a post or has long passed")
    g.add_argument("--skip-reel", action="store_true")
    g.add_argument("--music", type=Path)
    g.set_defaults(fn=cmd_generate)

    pl = sub.add_parser("poll", help="apply approvals and publish due items (Instagram, then YouTube)")
    pl.add_argument("--platform", choices=["ig", "yt", "all"], default="all",
                    help="where approved posts go (default: all)")
    pl.set_defaults(fn=cmd_poll)
    for name, fn, hlp in [("regenerate", cmd_regenerate, "rebuild items marked Regenerate"),
                          ("needs-regen", cmd_needs_regen, "print whether regeneration is pending"),
                          ("refresh-token", cmd_refresh, "refresh the Instagram token"),
                          ("status", cmd_status, "print the approval queue")]:
        sub.add_parser(name, help=hlp).set_defaults(fn=fn)

    for p in sub.choices.values():
        p.add_argument("--dry-run", action="store_true", help="write/send/publish nothing")

    args = ap.parse_args(argv)
    ensure_dirs()
    log.info("=== %s%s ===", args.cmd, " (dry-run)" if args.dry_run else "")
    try:
        return args.fn(args)
    except Exception:
        log.exception("%s failed", args.cmd)
        try:
            from src.approve_bot import notify
            notify(f"⚠️ <b>{args.cmd}</b> failed — check the logs.", dry_run=args.dry_run)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
