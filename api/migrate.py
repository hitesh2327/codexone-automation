"""`alembic upgrade head` that tolerates a database AHEAD of this code (QA-M-02).

Migrations are additive, so older code runs fine on a newer schema; but plain `alembic upgrade head`
fails with "Can't locate revision" when the database carries a revision this checkout doesn't know
(a rollback, or GitHub's "Re-run jobs" of a run created before a schema change). That failure used to
stop every poll/generate run, i.e. approved posts stopped publishing.

    python api/migrate.py            # from anywhere; reads DATABASE_URL like alembic does

Exit 0 after upgrading, or after skipping because the database is ahead (with a warning). Any other
problem (database unreachable, a failing migration) still fails the step.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # repo root, so `src` imports work


def _config():
    from alembic.config import Config
    cfg = Config(str(HERE / "alembic.ini"))
    cfg.set_main_option("script_location", str(HERE / "migrations"))
    return cfg


def database_revisions() -> set[str]:
    from sqlalchemy import create_engine, pool
    from alembic.runtime.migration import MigrationContext
    from src.db import database_url
    url = database_url()
    if not url:
        raise SystemExit("DATABASE_URL is not set (see README: Database)")
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            return set(MigrationContext.configure(conn).get_current_heads())
    finally:
        engine.dispose()


def unknown_revisions(current: set[str]) -> set[str]:
    """Revisions in the database that this code's migration scripts don't contain."""
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(_config())
    known = {rev.revision for rev in script.walk_revisions()}
    return {r for r in current if r not in known}


def main() -> int:
    from alembic import command
    current = database_revisions()
    ahead = unknown_revisions(current)
    if ahead:
        msg = (f"database is at revision {', '.join(sorted(ahead))}, newer than this code knows; "
               "skipping migrations (older code runs on the newer, additive schema)")
        print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"WARNING: {msg}", flush=True)
        return 0
    command.upgrade(_config(), "head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
