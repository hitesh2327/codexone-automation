"""CI gate (stdlib only, runs before pip install): is there anything for the poll job to do?

Active = waiting for a Telegram decision, approved but unpublished, a retryable failed
publish, or a Regenerate request. Reads Postgres via `psql` when DATABASE_URL is set
(preinstalled on GitHub's Ubuntu runners), otherwise data/queue.json.
Writes `work=true|false` to $GITHUB_OUTPUT. When unsure, says true (the job decides).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ACTIVE_SQL = ("select count(*) from posts where status in ('pending','approved','publishing','regenerate') "
              "or (status = 'failed' and attempts < 3)")


def active_from_db(url: str) -> int | None:
    if not shutil.which("psql"):
        return None
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url)  # psql doesn't know +psycopg
    try:
        out = subprocess.run(["psql", url, "-tAc", ACTIVE_SQL], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip().isdigit() else None


def active_from_file() -> int:
    queue = Path(__file__).resolve().parent.parent / "data" / "queue.json"
    items = json.loads(queue.read_text(encoding="utf-8") or "[]") if queue.exists() else []
    return sum(1 for i in items if i["status"] in ("pending", "approved", "publishing", "regenerate")
               or (i["status"] == "failed" and i.get("attempts", 0) < 3))


url = os.getenv("DATABASE_URL")
count = active_from_db(url) if url else active_from_file()
work = count is None or count > 0
print(f"{'unknown (DB check failed)' if count is None else count} active queue item(s)")
if out := os.getenv("GITHUB_OUTPUT"):
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"work={'true' if work else 'false'}\n")
