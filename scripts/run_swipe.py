"""Phase 4: Monthly swipe-file runner (ig-viral skill).

Run once a month after manually browsing 8-10 competitor accounts:
  1. Fill data/swipe/YYYY-MM.tsv with account, followers, median, views, hook
  2. Run:  python scripts/run_swipe.py
     (or:  python scripts/run_swipe.py --month 2026-10)
  3. Read the OUTLIERS section — note which formula names appear ≥2x in top third
  4. Update brand/config.yaml  reel.preferred_hook_formulas with those names
  5. Commit both files

The swipe.py script lives in .claude/skills/ig-viral/ and uses hooks.json from
.claude/skills/ig-reel/ to classify each hook into one of 26 named formulas.
The resulting swipe file is also written to ~/.claude/instagram/swipe.md so
ig-reel and ig-plan can read it in Claude chat sessions.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
SWIPE_SCRIPT = ROOT / ".claude" / "skills" / "ig-viral" / "swipe.py"
SWIPE_DIR = ROOT / "data" / "swipe"
CLAUDE_OUT = Path.home() / ".claude" / "instagram" / "swipe.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the ig-viral swipe analysis for a month.")
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"),
                    help="Month to process (default: current). Format: YYYY-MM")
    args = ap.parse_args(argv)

    tsv = SWIPE_DIR / f"{args.month}.tsv"
    md_out = SWIPE_DIR / f"{args.month}-swipe.md"

    if not SWIPE_SCRIPT.exists():
        print(f"ERROR: swipe.py not found at {SWIPE_SCRIPT}", file=sys.stderr)
        return 1

    if not tsv.exists():
        SWIPE_DIR.mkdir(parents=True, exist_ok=True)
        template = (
            "account\tfollowers\tmedian\tviews\thook\n"
            "# Add one row per reel you collected while browsing.\n"
            "# median = that account's typical recent views (the middle of their last 12 reels).\n"
            "# hook = the first line spoken or on screen, verbatim.\n"
            "@example\t48000\t11000\t412000\tnobody tells you your first 30 reels are supposed to flop\n"
        )
        tsv.write_text(template, encoding="utf-8")
        print(f"Created template: {tsv}")
        print("Fill it in with your collected data, then run this script again.")
        return 0

    print(f"Analysing {tsv} ...")
    result = subprocess.run(
        [sys.executable, str(SWIPE_SCRIPT), str(tsv), "--out", str(md_out)],
        cwd=ROOT, capture_output=False,
    )
    if result.returncode != 0:
        return result.returncode

    # Also write to ~/.claude/instagram/swipe.md so ig-reel / ig-plan pick it up
    CLAUDE_OUT.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_OUT.write_text(md_out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Also wrote {CLAUDE_OUT} (for ig-reel / ig-plan Claude sessions)")

    print("\nNext steps:")
    print(f"  1. Read {md_out}")
    print("  2. Note which formula names appear ≥2x in the OUTLIERS section (top third)")
    print("  3. Update brand/config.yaml  reel.preferred_hook_formulas with those names")
    print("  4. git add brand/config.yaml", md_out, "&& git commit -m 'chore: swipe file'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
