"""python -m src.verify <integration|all> [--depth format|live|deep] [--json]

Verifies the values this machine would use (environment first, then the Config store) against the real
providers and prints one line per check. Never prints a value. Exit code 0 = everything verified is
valid or warning; 1 = something is invalid, unknown or not set.

    python -m src.verify all                  # Tier 1 + database, live checks (nothing published; Cloudinary
                                              # uploads one 633-byte test image and deletes it)
    python -m src.verify gemini --depth deep  # also one real Gemini request (uses 1 request of quota)
    python -m src.verify telegram --depth deep  # also sends ONE plain test message (no buttons)
"""
from __future__ import annotations

import argparse
import json
import sys

from src import redact
from src.config_schema import TIER1
from src.verify import VERIFIERS, run

ICON = {"valid": "OK  ", "warning": "WARN", "invalid": "FAIL", "unknown": "????", "not_set": "----"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.verify", description="Verify configured integrations.")
    ap.add_argument("integration", choices=["all", *VERIFIERS])
    ap.add_argument("--depth", choices=["format", "live", "deep"], default="live")
    ap.add_argument("--json", action="store_true", help="print the structured results")
    args = ap.parse_args(argv)
    redact.install()

    names = list(TIER1) if args.integration == "all" else [args.integration]
    results = [run(n, depth=args.depth) for n in names]
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        for r in results:
            print(f"[{ICON.get(r.status, r.status)}] {r.integration:<11} {r.status}"
                  + (f"  ({r.code}) {r.message}" if r.code else "") + f"  {r.latency_ms} ms")
            for c in r.checks:
                mark = "ok  " if c.ok else "fail" if c.ok is False else "skip"
                print(f"        {mark} {c.label}" + (f" - {c.evidence}" if c.evidence else "")
                      + (f" [{c.code}]" if c.code and c.ok is not True else ""))
            if r.hint and r.status not in ("valid",):
                print(f"        next: {r.hint}")
    return 0 if all(r.status in ("valid", "warning") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
