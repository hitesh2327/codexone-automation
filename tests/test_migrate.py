"""QA-M-02: the workflows' migration step must not fail when the database is AHEAD of the code
(a rollback, or "Re-run jobs" of a run created before a schema change).

The migrations are Postgres-only, so this uses a throwaway database `fix_migrate_test` in the local
docker Postgres (docker compose up db; port 5433). Skipped when that isn't running. Never Neon."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

import migrate  # noqa: E402


LOCAL = os.environ.get("LOCAL_PG_URL", "postgresql+psycopg://codexone:codexone@localhost:5433")
SCRATCH = "fix_migrate_test"


@pytest.fixture
def scratch_db(monkeypatch):
    assert "localhost" in LOCAL or "127.0.0.1" in LOCAL, "only ever a local database"
    try:
        admin = create_engine(f"{LOCAL}/postgres", isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
        with admin.connect() as c:
            c.execute(text(f"drop database if exists {SCRATCH} with (force)"))
            c.execute(text(f"create database {SCRATCH}"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local docker Postgres not available ({type(e).__name__})")
    from src import db
    url = f"{LOCAL}/{SCRATCH}"
    monkeypatch.setenv("DATABASE_URL", url)
    _reset_engine(db)
    yield url
    _reset_engine(db)                     # never leave the session's engine pointing at the scratch database
    monkeypatch.undo()                    # the session's DATABASE_URL again
    _reset_engine(db)
    with admin.connect() as c:
        c.execute(text(f"drop database if exists {SCRATCH} with (force)"))
    admin.dispose()


def _reset_engine(db) -> None:
    for fn in (db.engine, db._sessionmaker):
        fn.cache_clear()


def _version(url: str) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as c:
        out = {r[0] for r in c.execute(text("select version_num from alembic_version"))}
    engine.dispose()
    return out


def test_upgrades_an_empty_database_to_head(scratch_db):
    from alembic.script import ScriptDirectory
    assert migrate.main() == 0
    assert _version(scratch_db) == set(ScriptDirectory.from_config(migrate._config()).get_heads())
    assert migrate.main() == 0                                   # idempotent


def test_database_ahead_of_the_code_is_skipped_not_failed(scratch_db, capsys):
    from alembic import command
    from alembic.util import CommandError
    assert migrate.main() == 0
    engine = create_engine(scratch_db)
    with engine.begin() as c:                                     # a revision from newer code
        c.execute(text("update alembic_version set version_num = 'ffff00000000'"))
    engine.dispose()
    with pytest.raises(CommandError):                             # what the workflow step used to do
        command.upgrade(migrate._config(), "head")
    assert migrate.main() == 0
    assert "newer than this code" in capsys.readouterr().out
    assert _version(scratch_db) == {"ffff00000000"}               # untouched


def test_verifier_reports_a_database_ahead_as_a_warning_not_behind(scratch_db, monkeypatch):
    from src.verify import database as verifier
    assert migrate.main() == 0
    engine = create_engine(scratch_db)
    with engine.begin() as c:
        c.execute(text("update alembic_version set version_num = 'ffff00000000'"))
    engine.dispose()
    r = verifier.verify({"DATABASE_URL": scratch_db})       # db.engine() follows DATABASE_URL (caches reset)
    mig = next(c for c in r.checks if c.name == "migrations")
    assert mig.code == "database.schema_ahead" and "newer than this app" in mig.evidence
    assert not any(c.code == "database.schema_behind" for c in r.checks)
