"""CI gate (stdlib only, runs before pip install): is there anything for the poll job to do?

Active = waiting for a Telegram decision, approved but unpublished, a retryable failed
publish, or a Regenerate request. Writes `work=true|false` to $GITHUB_OUTPUT.
"""
import json
import os
from pathlib import Path

queue = Path(__file__).resolve().parent.parent / "data" / "queue.json"
items = json.loads(queue.read_text(encoding="utf-8") or "[]") if queue.exists() else []
active = [i for i in items
          if i["status"] in ("pending", "approved", "regenerate")
          or (i["status"] == "failed" and i.get("attempts", 0) < 3)]
print(f"{len(active)} active queue item(s)")
if out := os.getenv("GITHUB_OUTPUT"):
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"work={'true' if active else 'false'}\n")
