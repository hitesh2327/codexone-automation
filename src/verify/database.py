"""Database (bootstrap: DATABASE_URL is set at install and is read-only on the Config page) and the
config store's master key.

    format  postgres:// (or sqlite:// for development); warns on Neon's pooled host ("-pooler", which Neon
            puts in the connection string by default: neon.com/docs/connect/connect-from-any-app)
    live    connect + `select 1` (one retry: Neon scales to zero after 5 idle minutes and "reactivates
            automatically within a few hundred milliseconds", neon.com/docs/introduction/scale-to-zero);
            tables present and alembic_version at the head of api/migrations; a write that is rolled back
            (proves write permission, changes nothing); CONFIG_MASTER_KEY present and the canary decrypts
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from src.verify.base import Result, Run

INTEGRATION = "database"
VERSIONS_DIR = Path(__file__).resolve().parents[2] / "api" / "migrations" / "versions"
REQUIRED_TABLES = {"posts", "settings", "activity_log", "generation_jobs", "config_values", "config_keys",
                   "config_checks", "config_meta"}
_REV = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"]([0-9a-f]+)['\"]", re.M)
_DOWN = re.compile(r"^down_revision[^=]*=\s*(.+)$", re.M)


def migration_heads(versions_dir: Path = VERSIONS_DIR) -> set[str] | None:
    """Head revision(s) of the migration files, or None if they aren't packaged with this build."""
    if not versions_dir.is_dir():
        return None
    revs, downs = set(), set()
    for f in versions_dir.glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="replace")
        if m := _REV.search(text):
            revs.add(m.group(1))
        if d := _DOWN.search(text):
            downs |= set(re.findall(r"['\"]([0-9a-f]+)['\"]", d.group(1)))
    return (revs - downs) or None


def _connect(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    for attempt in (1, 2):
        try:
            t0 = time.monotonic()
            with engine.connect() as c:
                c.execute(text("select 1"))
            return int((time.monotonic() - t0) * 1000), None
        except OperationalError as e:
            if "password authentication failed" in str(e).lower() or "authentication failed" in str(e).lower():
                return 0, "database.rejected"
            if attempt == 2:
                return 0, "database.unreachable"
            time.sleep(2)  # Neon waking up
    return 0, "database.unreachable"


def verify(values: dict[str, str], depth: str = "live") -> Result:
    run = Run(INTEGRATION, depth)
    url = values.get("DATABASE_URL") or ""
    if not url:
        return run.finish(not_set=True, code="database.not_set")
    try:
        parts = urlsplit(url)
        scheme, host = parts.scheme.lower(), (parts.hostname or "")
    except ValueError:
        scheme, host = "", ""
    if scheme not in ("postgres", "postgresql", "postgresql+psycopg", "sqlite"):
        run.fail("format", "Connection string is postgres://", "database.format", depth="format")
        return run.finish()
    run.ok("format", "Connection string is postgres://", "development SQLite" if scheme == "sqlite" else host, depth="format")
    if "-pooler." in host:
        run.warn("direct", "Uses the direct (not pooled) connection", "database.pooled_url", host, depth="format")
    if depth == "format":
        return run.finish()

    from sqlalchemy import inspect, text
    from src import config_store, db
    try:
        engine = db.engine()
    except Exception:  # noqa: BLE001
        run.fail("connect", "The database answers", "database.unreachable")
        return run.finish()
    ms, err = _connect(engine)
    if err:
        run.fail("connect", "The database answers", err)
        return run.finish()
    run.ok("connect", "The database answers", f"{ms} ms")
    run.evidence["latency_ms"] = ms

    try:
        tables = set(inspect(engine).get_table_names())
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            run.fail("schema", "Schema is up to date", "database.schema_behind", f"missing tables: {', '.join(missing)}")
        else:
            run.ok("schema", "Schema is up to date", "all tables present")
        heads = migration_heads()
        if "alembic_version" not in tables:
            run.skip("migrations", "Migrations are at the latest version", "No alembic_version table (a development database).")
        elif heads is None:
            run.skip("migrations", "Migrations are at the latest version", "Migration files aren't packaged with this build.")
        else:
            with engine.connect() as c:
                current = c.execute(text("select version_num from alembic_version")).scalar()
            if current in heads:
                run.ok("migrations", "Migrations are at the latest version", f"at {current}")
            else:
                run.fail("migrations", "Migrations are at the latest version", "database.schema_behind",
                         f"database at {current}, this app expects {', '.join(sorted(heads))}")
        run.evidence["schema"] = "ok" if not missing else "behind"
    except Exception:  # noqa: BLE001
        run.fail("schema", "Schema is up to date", "database.unreachable")
        return run.finish()

    if "config_meta" in tables:
        try:  # touches no row, then rolls back: Postgres still checks the UPDATE privilege
            with engine.connect() as c:
                tx = c.begin()
                c.execute(text("update config_meta set config_version = config_version where id = -1"))
                tx.rollback()
            run.ok("write", "The app can write (tested, rolled back)")
        except Exception:  # noqa: BLE001
            run.fail("write", "The app can write (tested, rolled back)", "database.read_only")

        try:
            state = config_store.check_canary()
            run.ok("master_key", "Master key opens the saved settings",
                   "no secrets saved yet" if state == "empty" else "canary decrypted")
        except config_store.StoreError as e:
            run.fail("master_key", "Master key opens the saved settings", e.code)
        except Exception:  # noqa: BLE001
            run.fail("master_key", "Master key opens the saved settings", "database.unreachable")
    return run.finish()
