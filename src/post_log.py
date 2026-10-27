"""Log per-post generation metadata for ig-audit: hook formula, score, humanness, caption stats.

Written to data/post_log.jsonl (one JSON object per line). After ~30 posts this
file is the evidence ig-audit needs to identify which hook formulas are working.

Convert to the ig-audit-compatible ~/.claude/instagram/log.md with:
  python -m src.post_log export
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_DIR
from src.logger import get_logger

log = get_logger("post_log")
LOG_FILE = DATA_DIR / "post_log.jsonl"


def record(
    *,
    post_id: str,
    kind: str,
    topic: str,
    category: str,
    hook: str,
    hook_formula: str | None = None,
    hook_score: float | None = None,
    humanness_verdict: str | None = None,
    caption_len: int = 0,
    hashtag_count: int = 0,
) -> None:
    """Append one entry to data/post_log.jsonl. Never raises."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "id": post_id,
            "kind": kind,
            "topic": topic,
            "category": category,
            "hook": hook,
            "hook_formula": hook_formula,
            "hook_score": round(hook_score, 1) if hook_score is not None else None,
            "humanness": humanness_verdict,
            "caption_len": caption_len,
            "hashtags": hashtag_count,
        }
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        log.exception("post_log.record failed silently")


def export_to_markdown(out_path: Path | None = None) -> Path:
    """Convert post_log.jsonl to ~/.claude/instagram/log.md for ig-audit."""
    out = out_path or Path.home() / ".claude" / "instagram" / "log.md"
    if not LOG_FILE.exists():
        log.error("No post_log.jsonl found — generate some posts first")
        return out
    entries = [json.loads(line) for line in LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [
        "# Post Log\n",
        f"Generated from data/post_log.jsonl — {len(entries)} entries\n\n",
        "| Date | Kind | Category | Formula | Score | Hook |\n",
        "|---|---|---|---|---|---|\n",
    ]
    for e in entries:
        date = e["ts"][:10]
        formula = e.get("hook_formula") or "—"
        score = f"{e['hook_score']:.0f}" if e.get("hook_score") is not None else "—"
        hook = (e.get("hook") or "")[:80]
        lines.append(f"| {date} | {e['kind']} | {e['category']} | {formula} | {score} | {hook} |\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    log.info("wrote %d entries to %s", len(entries), out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Post log utilities")
    ap.add_argument("cmd", choices=["export"], help="export: write log.md for ig-audit")
    ap.add_argument("--out", help="output path (default ~/.claude/instagram/log.md)")
    args = ap.parse_args(argv)
    if args.cmd == "export":
        export_to_markdown(Path(args.out) if args.out else None)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
