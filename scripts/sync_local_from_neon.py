"""One-way snapshot: Neon posts -> local Docker DB (read-only on Neon).

Run after the local DB is migrated:  .venv/Scripts/python scripts/sync_local_from_neon.py
"""
import os
from sqlalchemy import create_engine, text, inspect
from dotenv import dotenv_values

env = dotenv_values(str(__import__("pathlib").Path(__file__).resolve().parent.parent / ".env"))
src = create_engine(env["DATABASE_URL"])
dst = create_engine("postgresql+psycopg://codexone:codexone@localhost:5433/codexone")

cols = [c["name"] for c in inspect(src).get_columns("posts")]
dcols = {c["name"] for c in inspect(dst).get_columns("posts")}
cols = [c for c in cols if c in dcols]
missing_group = "group_id" not in cols
print("copying columns:", len(cols))

with src.connect() as s:
    rows = s.execute(text(f"select {','.join(cols)} from posts")).mappings().all()

extra = [] if "group_id" in cols else ["group_id"]   # older sources predate the column
col_list = ",".join(cols + extra)
vals = ",".join([f":{c}" for c in cols] + ["''" for _ in extra])
upd = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
from sqlalchemy.types import JSON
import json
with dst.begin() as d:
    for r in rows:
        p = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()}
        d.execute(text(f"insert into posts ({col_list}) values ({vals}) on conflict (id) do update set {upd}"), p)
    d.execute(text("""UPDATE posts SET group_id = COALESCE(substring(replace(post_dir, '', '/') from 'output/([^/]+/[^/]+)'),
                     to_char(date, 'YYYY-MM-DD') || '/' || id) WHERE group_id = ''"""))
print("upserted", len(rows), "posts")
with dst.connect() as d:
    for r in d.execute(text("select id,kind,status from posts order by created_at desc limit 5")):
        print(" ", tuple(r))
