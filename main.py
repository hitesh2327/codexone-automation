"""codexonebyhitesh content pipeline.

Commands:
  generate       fetch → rank → write → render carousel + reel → upload → Telegram previews
                 (--topic/--category: write about a chosen topic instead; progress goes to the dashboard's job)
  job-end        close the generation job of a failed/cancelled CI run
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
from datetime import date, datetime
from pathlib import Path

from src import queue_store as q
from src.config import ensure_dirs
from src.generation import LATE_LIMIT_HOURS, slot_state  # shared with the dashboard
from src.logger import get_logger

log = get_logger("main")


def _log_generated(item, regenerated: bool = False) -> None:
    from src import activity
    activity.record("post.regenerated" if regenerated else "post.generated",
                    f"{'Regenerated' if regenerated else 'Generated'} {item.kind} “{item.topic}” (v{item.version}) "
                    "and sent it to Telegram for approval", source="pipeline", actor="system", post_id=item.id)


def _generate_input_error(args) -> str | None:
    """Why these arguments can't be used (the workflow passes user-typed text), else None."""
    from src import approve_bot, generation
    try:
        date.fromisoformat(args.date)
    except (TypeError, ValueError):
        return f"--date {args.date!r} is not YYYY-MM-DD"
    if args.slot and (not generation.valid_slot(args.slot)
                      or args.slot not in {f"{t:%H:%M}" for t in approve_bot.post_times()}):
        return f"--slot {args.slot!r} is not one of the posting slots"
    if args.category and args.category not in generation.CATEGORIES:
        return f"--category {args.category!r} is not one of {', '.join(generation.CATEGORIES)}"
    try:
        args.topic = generation.clean_topic(args.topic)
        args.source_url = generation.clean_source_url(args.source_url)
    except ValueError as e:
        return str(e)
    if args.topic and not args.category:
        return "--topic needs --category"
    if args.source_url and not args.topic:
        return "--source-url needs --topic"
    return None


def cmd_generate(args) -> int:
    from src import approve_bot, generation

    if err := _generate_input_error(args):
        log.error("%s", err)
        return 2
    # Which posting slot is this run for? Explicit --slot (CI passes it per trigger), else the next one.
    publish_at = (approve_bot.slot_at(args.date, args.slot) if args.slot else approve_bot.next_slot())
    log.info("slot: %s IST", f"{publish_at:%a %d %b %H:%M}")
    job = generation.Reporter() if args.dry_run else generation.Reporter.begin(
        args.request_id, slot_at=publish_at, category=args.category, topic=args.topic,
        source_url=args.source_url, force=args.force, allow_duplicate=args.allow_duplicate)
    try:
        return _generate(args, publish_at, job)
    except Exception as e:
        job.failed(e)
        raise


def _generate(args, publish_at: datetime, job) -> int:
    from src import approve_bot, fetch_topics, gen_content, generation, rank_topics, render_post, render_reel, upload
    from src.rank_topics import RankedTopic

    day = args.date

    # Two schedulers can fire for the same slot (cron-job.org + GitHub's backup cron): only the
    # first one generates. A trigger arriving long after the slot is skipped as stale.
    # Compare instants, not strings: the DB returns the same slot as UTC ("13:30+00:00").
    taken = bool(q.load_window(publish_at, publish_at))
    now = datetime.now(approve_bot.IST)
    state = "ok" if args.force else slot_state(publish_at, now, taken)
    hours_late = (now - publish_at).total_seconds() / 3600
    if state == "taken":
        log.info("slot %s already has a post queued; nothing to do", f"{publish_at:%d %b %H:%M}")
        job.skipped("taken", f"The {publish_at:%H:%M} slot already has a post.")
        return 0
    if state == "stale":
        log.warning("slot %s passed %.1fh ago (limit %dh); skipping stale run",
                    f"{publish_at:%d %b %H:%M}", hours_late, LATE_LIMIT_HOURS)
        job.skipped("stale", f"The {publish_at:%d %b %H:%M} slot passed {hours_late:.0f}h ago (limit {LATE_LIMIT_HOURS}h).")
        return 0
    if state == "late":
        log.warning("slot %s passed %.1fh ago (the scheduler fired late); generating anyway -- "
                    "this post publishes as soon as it is approved",
                    f"{publish_at:%d %b %H:%M}", hours_late)

    if args.topic:
        # Chosen by the admin: no trending fetch and no ranking, but the same duplicate check, writing
        # and review pass as any other topic.
        if not args.allow_duplicate and (dup := generation.find_duplicate(args.topic)):
            log.warning("topic %r repeats %r (%s); skipping", args.topic, dup[0], dup[1])
            job.skipped("duplicate", f"Looks like \u201c{dup[0]}\u201d ({dup[1]}). Allow duplicates to repeat it.")
            return 0
        topic = RankedTopic(category=args.category, title=args.topic,
                            angle=f"Explain \u201c{args.topic}\u201d accurately for students and junior developers.",
                            source_url=args.source_url or "", evergreen=not args.source_url,
                            why="chosen from the dashboard")
    else:
        job.phase("fetching_topics")
        fetch_topics.main(["--show", "0"] + (["--dry-run"] if args.dry_run else []))
        if args.dry_run and not (Path("data") / f"topics_{day}.json").exists():
            log.info("[dry-run] no saved topics for %s; stopping after fetch", day)
            return 0
        job.phase("ranking")
        topic = rank_topics.rank(day, args.category, seed=f"{day}-{publish_at:%H%M}")
    log.info("topic: [%s] %s", topic.category, topic.title)
    job.phase("writing")
    content = gen_content.generate(topic)
    if args.dry_run:
        log.info("[dry-run] content generated (%d slides); not rendering/uploading/sending",
                 len(content.carousel))
        render_post.render_carousel(content, Path("."), dry_run=True)
        render_reel.render_reel(content, Path("."), dry_run=True)
        return 0

    job.phase("rendering")
    post_dir = gen_content.save(content, day).parent
    render_post.render_carousel(content, post_dir / "carousel")
    voice = ""
    if not args.skip_reel:
        voice = render_reel.pick_voice()
        render_reel.render_reel(content, post_dir, args.music or render_reel._default_music(), voice=voice)
    job.phase("uploading")
    upload.upload_post(post_dir)

    job.phase("sending_previews")
    items = approve_bot.items_from_post(post_dir, source_url=topic.source_url, angle=topic.angle,
                                        publish_at=publish_at, voice=voice)
    for item in items:  # previews only: publishing needs an Approve (Telegram or dashboard)
        approve_bot.send_preview(item)
        _log_generated(item)
    job.succeeded(topic.title, topic.category, items[0].group_id, [i.id for i in items])
    return 0


EXPIRE_HOURS = 36  # Telegram only keeps unread updates for 24h, so older previews are stale
STUCK_PUBLISHING_MINUTES = 30  # longest a real publish should take (IG video processing included)


def expire_stale(dry_run: bool) -> None:
    from datetime import datetime, timedelta, timezone
    from src import activity, approve_bot

    cutoff = datetime.now(timezone.utc) - timedelta(hours=EXPIRE_HOURS)
    # A publisher that claimed an item and then died leaves it in "publishing"; release it.
    # Keyed on the row's own updated_at, so a publish still in flight is never taken away.
    for item_id in q.release_stuck_publishing(STUCK_PUBLISHING_MINUTES, dry_run):
        log.warning("%s was stuck in publishing; released for retry", item_id)
        activity.record("publish.released", "Publishing stalled for 30+ minutes; released for retry", level="warning",
                        source="publisher", post_id=item_id)
    for item in q.load(statuses=("pending",)):
        if item.status == "pending" and datetime.fromisoformat(item.created_at) < cutoff:
            log.info("expiring %s (no decision in %dh)", item.id, EXPIRE_HOURS)
            if dry_run:
                continue
            item.status = "expired"
            if not q.update_if(item, "pending"):  # decided meanwhile (dashboard / Telegram): leave it
                continue
            activity.record("post.expired", f"No decision in {EXPIRE_HOURS}h; {item.kind} “{item.topic}” expired",
                            source="pipeline", actor="system", post_id=item.id)
            approve_bot.notify(f"⌛ No decision in {EXPIRE_HOURS}h — <code>{item.id}</code> expired "
                               "and will not be posted.", item.tg_control_id)


def cmd_poll(args) -> int:
    from src import approve_bot, generation, publish

    approve_bot.poll(args.dry_run)
    expire_stale(args.dry_run)
    if not args.dry_run:
        from src import activity
        activity.prune()
        generation.expire_stuck()
        generation.prune()
    publish.publish_due(args.dry_run, publish.platforms_arg(args.platform))
    return 0


def cmd_job_end(args) -> int:
    """CI's last step after a failed/cancelled generate: close its job if the pipeline never did."""
    from src import generation
    if generation.end_run(args.outcome, args.request_id):
        log.info("generation job closed as %s", args.outcome)
    return 0


def cmd_regenerate(args) -> int:
    """Rebuild items marked "regenerate". Both formats of one topic flagged together (the
    dashboard's "Regenerate content") share one new script; otherwise each format alone."""
    from src import approve_bot, gen_content, render_post, render_reel, upload
    from src.rank_topics import RankedTopic

    todo = q.load(statuses=("regenerate",))
    if not todo:
        log.info("nothing to regenerate")
        return 0
    groups: dict[str, list[q.Item]] = {}
    for item in todo:
        groups.setdefault(item.group_id, []).append(item)

    for group_id, olds in groups.items():
        kinds = sorted({o.kind for o in olds})
        version = max(o.version for o in olds) + 1
        first = olds[0]
        log.info("regenerating %s [%s] as v%d", group_id, "+".join(kinds), version)
        if args.dry_run:
            continue
        notes = list(dict.fromkeys(o.feedback for o in olds if o.feedback))
        feedback = "Write a clearly different version (new hook, examples and structure)."
        if notes:
            feedback += "\nReviewer feedback to apply: " + "\n".join(notes)
        topic = RankedTopic(category=first.category, title=first.topic, angle=first.angle or first.topic,
                            source_url=first.source_url, evergreen=not first.source_url, why="regenerate")
        try:
            content = gen_content.generate(topic, feedback)
            slug = gen_content.slugify(first.topic)
            # one format alone gets its own folder so it never overwrites the other's content.json
            suffix = f"v{version}" if len(kinds) == 2 else f"v{version}-{kinds[0]}"
            post_dir = gen_content.post_dir(first.date, first.topic) / suffix
            post_dir.mkdir(parents=True, exist_ok=True)
            (post_dir / "content.json").write_text(content.model_dump_json(indent=2), encoding="utf-8")
            voice = ""
            if "carousel" in kinds:
                render_post.render_carousel(content, post_dir / "carousel")
            if "reel" in kinds:
                voice = render_reel.voice_from_feedback("\n".join(notes)) or render_reel.pick_voice()
                render_reel.render_reel(content, post_dir, render_reel._default_music(), voice=voice)
            upload.upload_post(post_dir, only=None if len(kinds) == 2 else kinds[0])
            by_kind = {o.kind: o for o in olds}
            for new in approve_bot.items_from_post(post_dir, only=None if len(kinds) == 2 else kinds[0],
                                                   source_url=first.source_url, angle=first.angle,
                                                   day=first.date, slug=slug, version=version,
                                                   publish_at=approve_bot.item_publish_at(first), voice=voice):
                old = by_kind[new.kind]
                new.feedback = old.feedback        # shown on the new preview as "Applied feedback"
                new.targets = old.targets          # keep the platforms chosen in the dashboard
                new.yt_title, new.yt_description = old.yt_title, old.yt_description
                approve_bot.send_preview(new)
                _log_generated(new, regenerated=True)
            for old in olds:
                old.status = "replaced"
                q.update_if(old, "regenerate")
        except Exception as e:  # keep status=regenerate so the next run retries
            log.exception("regenerate %s failed", group_id)
            approve_bot.notify(f"⚠️ Regenerate failed for <code>{group_id}</code>: {e}", first.tg_control_id)
    return 0


def cmd_needs_regen(args) -> int:
    needed = bool(q.load(statuses=("regenerate",)))
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
    g.add_argument("--topic", help="write about this instead of ranking a trending topic (needs --category)")
    g.add_argument("--source-url", help="https link to cite for --topic (the page is not read)")
    g.add_argument("--allow-duplicate", action="store_true", help="allow --topic to repeat a recent topic")
    g.add_argument("--request-id", help="dashboard request id: progress is reported to that generation job")
    g.add_argument("--skip-reel", action="store_true")
    g.add_argument("--music", type=Path)
    g.set_defaults(fn=cmd_generate)

    je = sub.add_parser("job-end", help="close the generation job of a failed/cancelled run")
    je.add_argument("--outcome", choices=["failure", "cancelled"], default="failure")
    je.add_argument("--request-id", help="dashboard request id (default: the job of this GitHub run)")
    je.set_defaults(fn=cmd_job_end)

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
    if os.getenv("GITHUB_ACTIONS") == "true" and args.cmd in ("generate", "poll", "regenerate") and not args.dry_run:
        from src import config_store  # tells the Config page whether this runner can read saved secrets
        config_store.report_runner()
    try:
        return args.fn(args)
    except Exception as e:
        log.exception("%s failed", args.cmd)
        try:
            import html as _html

            from src.approve_bot import notify
            run = os.getenv("GITHUB_RUN_ID")
            repo = os.getenv("GITHUB_REPOSITORY", "")  # set by GitHub Actions itself
            where = f"\n{'https://github.com/%s/actions/runs/%s' % (repo, run)}" if run and repo else ""
            notify(f"⚠️ <b>{args.cmd}</b> failed: {_html.escape(f'{type(e).__name__}: {e}'[:400])}{where}",
                   dry_run=args.dry_run)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
