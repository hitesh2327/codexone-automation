"""One-time (re-runnable) migration of file state into Postgres.

    data/queue.json      -> posts           (upsert by id)
    data/posted.json     -> posted_topics   (upsert by item id; legacy rows without id kept once)
    brand/config.yaml    -> settings.brand  (only if not set yet; --overwrite-brand to replace)
    data/tg_offset.json  -> settings.tg_offset (only ever moves forward)

Safe to run again at switch-over time to pick up the latest file state. Verifies that
every migrated queue item reads back from the DB identical to the JSON.

Usage:
    DATABASE_URL=... python scripts/migrate_json_to_db.py [--dry-run] [--overwrite-brand]
    (run `cd api && alembic upgrade head` first)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from sqlalchemy import inspect, select  # noqa: E402

from src import db  # noqa: E402
from src import queue_store as q  # noqa: E402
from src.config import BRAND_FILE, DATA_DIR, POSTED_FILE  # noqa: E402
from src.db.models import Post, PostedTopic, Setting  # noqa: E402


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8") or "null") or default if path.exists() else default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("--overwrite-brand", action="store_true",
                    help="replace settings.brand even if it exists (loses dashboard edits)")
    args = ap.parse_args()

    if not db.enabled():
        sys.exit("DATABASE_URL is not set")
    missing = {"posts", "posted_topics", "settings"} - set(inspect(db.engine()).get_table_names())
    if missing:
        sys.exit(f"tables missing: {sorted(missing)} -- run `cd api && alembic upgrade head` first")

    queue = [q.Item.model_validate(x) for x in _read_json(q.QUEUE_FILE, [])]
    posted = _read_json(POSTED_FILE, [])
    brand = yaml.safe_load(BRAND_FILE.read_text(encoding="utf-8"))
    offset = (_read_json(DATA_DIR / "tg_offset.json", {}) or {}).get("offset")

    with db.session() as s:
        existing_posts = set(s.scalars(select(Post.id)))
        existing_posted = {r.item_id: r for r in s.scalars(select(PostedTopic)) if r.item_id}
        legacy_keys = {(r.title, r.kind, r.date) for r in s.scalars(select(PostedTopic)) if not r.item_id}
        brand_row = s.get(Setting, "brand")
        offset_row = s.get(Setting, "tg_offset")

        # posts
        new_posts = sum(1 for i in queue if i.id not in existing_posts)
        for item in queue:
            s.merge(Post(**q._to_row_values(item)))

        # posted_topics
        added_posted = updated_posted = 0
        for e in posted:
            values = dict(item_id=e.get("id"), title=e.get("title", ""), url=e.get("url") or "",
                          category=e.get("category"), kind=e.get("kind"),
                          date=date.fromisoformat(e["date"]) if e.get("date") else None,
                          ig_media_id=e.get("ig_media_id"),
                          published_at=q._parse_ts(e.get("published_at")), platforms=e.get("platforms") or {})
            if values["item_id"] and values["item_id"] in existing_posted:
                row = existing_posted[values["item_id"]]
                for k, v in values.items():
                    setattr(row, k, v)
                updated_posted += 1
            elif values["item_id"] or (values["title"], values["kind"], values["date"]) not in legacy_keys:
                s.add(PostedTopic(**values))
                added_posted += 1

        # settings
        brand_action = "kept existing"
        if brand_row is None:
            s.add(Setting(key="brand", value=brand))
            brand_action = "imported"
        elif args.overwrite_brand:
            brand_row.value = brand
            brand_action = "overwritten"
        offset_action = "none in files"
        if offset is not None:
            current = (offset_row.value or {}).get("offset") if offset_row else None
            if current is None or offset > current:
                if offset_row:
                    offset_row.value = {"offset": offset}
                else:
                    s.add(Setting(key="tg_offset", value={"offset": offset}))
                offset_action = f"set to {offset}"
            else:
                offset_action = f"kept DB value {current} (file has {offset})"

        print(f"posts:         {len(queue)} in file -> {new_posts} new, {len(queue) - new_posts} updated")
        print(f"posted_topics: {len(posted)} in file -> {added_posted} added, {updated_posted} updated")
        print(f"brand:         {brand_action}")
        print(f"tg_offset:     {offset_action}")
        if args.dry_run:
            s.rollback()
            print("dry run: rolled back, nothing written")
            return 0

    # Verify: every file item reads back identically through the DB-backed queue_store.
    by_id = {i.id: i for i in q.load()}
    mismatched = []
    for item in queue:
        got = by_id.get(item.id)
        a, b = item.model_dump(), got.model_dump() if got else None
        if b is None:
            mismatched.append((item.id, "missing"))
            continue
        for f in ("publish_at", *q._TS_FIELDS):  # same instant, possibly different offset notation
            a[f] = q._parse_ts(a[f]) if a[f] else None
            b[f] = q._parse_ts(b[f]) if b[f] else None
        if a != b:
            diff = [k for k in a if a[k] != b[k]]
            mismatched.append((item.id, diff))
    if mismatched:
        print("VERIFY FAILED:", mismatched)
        return 1
    print(f"verified: all {len(queue)} queue items read back identical from the DB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
