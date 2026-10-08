"""What the Config page shows and what "ready to generate" means.

    from src.config_status import readiness
    r = readiness()          # {"ready_to_generate": bool, "conditions": [...], "missing": [...], ...}

A verification result counts only for the exact values it checked: every stored check carries `values_fp`,
a keyed fingerprint (HMAC under the store's data key) of the integration's effective values at the time.
Change any value (on the Config page, or the environment) and its old result stops counting ("stale").

Readiness (spec 7.5) in this release:
  G1 database reachable, schema current, writable, master key opens the store (checked live, every call)
  G2 Gemini, G3 Telegram, G4 Cloudinary, G5 GitHub: latest check of the CURRENT values is valid/warning
  G6 the end-to-end system test: not built yet (spec phase P3); reported, not blocking
  G7 no required value has an unresolved environment/store conflict; GitHub token not expiring within 3 days
  G8 GITHUB_REPOSITORY explicitly set (no owner default)
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

from src.config_schema import BY_NAME, FIELDS_BY_NAME, INTEGRATIONS, TIER1, fields_of

KEEP_CHECKS = 50                 # per integration
EXPIRY_BLOCK = timedelta(days=3)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


def values_fp(values: dict[str, str], *, create: bool = False) -> str | None:
    """Keyed fingerprint of a set of values (None without a usable master key or data key). Only an
    authenticated admin write passes create=True (see config_store.fingerprint)."""
    from src import config_store
    canon = "\n".join(f"{k}={values[k]}" for k in sorted(values)) or "(empty)"
    return config_store.fingerprint(canon, create=create)


# --------------------------------------------------------------------------- #
# Check history
# --------------------------------------------------------------------------- #
def record(result, *, values: dict[str, str], actor: str | None, ran_in: str = "api", fp: str | None = None) -> None:
    from sqlalchemy import delete, select
    from src import config_store, db
    from src.db.models import ConfigCheck
    if not db.enabled():
        return
    d = result.to_dict()
    expires = None
    if d.get("expires_at"):
        try:
            expires = datetime.fromisoformat(d["expires_at"])
        except ValueError:
            expires = None
    with db.session() as s:
        s.add(ConfigCheck(
            integration=result.integration, status=result.status, depth=result.depth,
            error_class=result.error_class, code=result.code, message=result.message,
            result={k: d[k] for k in ("checks", "evidence", "hint", "docs", "latency_ms", "checked_at", "implemented")},
            values_fp=fp if fp is not None else values_fp(values), config_version=config_store.config_version(),
            ran_in=ran_in, duration_ms=result.latency_ms, actor=actor, expires_at=expires))
        s.flush()
        keep = select(ConfigCheck.id).where(ConfigCheck.integration == result.integration) \
            .order_by(ConfigCheck.id.desc()).limit(KEEP_CHECKS)
        s.execute(delete(ConfigCheck).where(ConfigCheck.integration == result.integration,
                                            ConfigCheck.id.not_in(keep.scalar_subquery())))


def _row(c) -> dict:
    return {"id": c.id, "integration": c.integration, "status": c.status, "depth": c.depth,
            "error_class": c.error_class, "code": c.code, "message": c.message, **(c.result or {}),
            "ran_at": _iso(c.ran_at), "ran_in": c.ran_in, "actor": c.actor, "config_version": c.config_version,
            "expires_at": _iso(c.expires_at)}


def history(integration: str, limit: int = 10) -> list[dict]:
    from sqlalchemy import select
    from src import db
    from src.db.models import ConfigCheck
    if not db.enabled():
        return []
    with db.session() as s:
        rows = s.scalars(select(ConfigCheck).where(ConfigCheck.integration == integration)
                         .order_by(ConfigCheck.id.desc()).limit(limit))
        return [_row(c) for c in rows]


def latest(integration: str, fp: str | None) -> tuple[dict | None, dict | None]:
    """(latest check of exactly these values, latest check of any values)."""
    from sqlalchemy import select
    from src import db
    from src.db.models import ConfigCheck
    if not db.enabled():
        return None, None
    with db.session() as s:
        anyrow = s.scalars(select(ConfigCheck).where(ConfigCheck.integration == integration)
                           .order_by(ConfigCheck.id.desc()).limit(1)).first()
        cur = None
        if fp and anyrow:
            # depth "format" proves nothing about the provider, so it never counts as verified
            cur = s.scalars(select(ConfigCheck).where(ConfigCheck.integration == integration,
                                                      ConfigCheck.values_fp == fp, ConfigCheck.depth != "format")
                            .order_by(ConfigCheck.id.desc()).limit(1)).first()
        return (_row(cur) if cur else None), (_row(anyrow) if anyrow else None)


# --------------------------------------------------------------------------- #
# Field and integration state (never a secret value)
# --------------------------------------------------------------------------- #
def _env_value(name: str) -> str | None:
    from src.config import _from_env
    return _from_env(name)


def field_state(name: str, entries: dict) -> dict:
    from src import config_store
    f = FIELDS_BY_NAME[name]
    env = _env_value(name)
    e = entries.get(name)
    stored = bool(e and (e.value or e.fingerprint))
    store_first = (os.getenv("CONFIG_PRECEDENCE") or "env").strip().lower() == "store"
    source = None
    if env and stored:
        source = "store" if store_first else "env"
    elif env:
        source = "env"
    elif stored:
        source = "store"
    conflict = False
    if env and stored:
        if f.secret:
            env_fp = config_store.fingerprint(env)
            conflict = env_fp is None or env_fp != e.fingerprint
        else:
            conflict = env != (e.value or "")
    effective = (e.value if source == "store" else env) if source else None
    return {
        "name": f.name, "label": f.label, "secret": f.secret, "required": f.required, "shape": f.shape,
        "help": f.help, "advanced": f.advanced, "is_set": bool(source),
        "source": source, "in_env": bool(env), "in_store": stored, "overridden": bool(env and stored),
        "conflict": conflict,
        # Non-secret values are shown (repository name, model, chat id); secrets never, not even a part.
        "value": None if f.secret else effective,
        "fingerprint": (e.fingerprint[:8] if (f.secret and e and e.fingerprint) else None),
        "version": e.version if e else 0,
        "updated_at": _iso(e.updated_at) if e else None, "updated_by": e.updated_by if e else None,
        "store_source": e.source if e else None,
        "undecryptable": bool(f.secret and e and e.fingerprint and not e.value),
    }


def integration_state(name: str, *, entries: dict | None = None, checking: bool = False) -> dict:
    from src import config_store
    from src.verify import effective_values
    if entries is None:
        entries, _ = config_store.snapshot()
    integ = BY_NAME[name]
    fields = [field_state(f.name, entries) for f in fields_of(name)]
    values = effective_values(name)
    fp = values_fp(values) if values else None
    current, last = latest(name, fp)
    required_set = all(f["is_set"] for f in fields if f["required"]) if fields else bool(values)
    if checking:
        state = "checking"
    elif not values:
        state = "not_set"
    elif current:
        state = current["status"]
    elif last:
        state = "stale"          # verified before, but a value changed since
    else:
        state = "unverified"
    return {
        "name": integ.name, "title": integ.title, "tier": integ.tier, "blurb": integ.blurb, "minutes": integ.minutes,
        "implemented": integ.implemented, "editable": integ.editable, "state": state,
        "required_set": required_set, "fields": fields, "check": current, "last_check": last,
        "conflict": any(f["conflict"] for f in fields),
    }


# --------------------------------------------------------------------------- #
# Readiness
# --------------------------------------------------------------------------- #
def readiness(states: dict[str, dict] | None = None) -> dict:
    """READY_TO_GENERATE for the current configuration. Cheap enough to call per request
    (one database round-trip set + reads of stored results; no provider calls)."""
    from src import config_store, github_actions
    from src.verify import run
    states = states or {n: integration_state(n) for n in TIER1}
    conds: list[dict] = []

    def add(cid, label, ok, detail, integration=None, blocking=True, code=None):
        conds.append({"id": cid, "label": label, "ok": ok, "blocking": blocking, "detail": detail,
                      "integration": integration, "code": code,
                      "fix": f"/config#{integration}" if integration else None})

    db_result = run("database")  # live, local: connect, schema, rolled-back write, canary
    add("G1", "Database and master key", db_result.status in ("valid", "warning"),
        db_result.message or "Database reachable, schema current, writable; master key opens the store.",
        "database", code=db_result.code)
    runner_ok, runner_detail = config_store.runner_access()
    add("G9", "GitHub Actions can read the saved settings", runner_ok, runner_detail, "github")

    for gid, name in (("G2", "gemini"), ("G3", "telegram"), ("G4", "cloudinary"), ("G5", "github")):
        st = states[name]
        chk = st["check"]
        ok = st["state"] in ("valid", "warning")
        if st["state"] == "not_set":
            detail = "Not set."
        elif st["state"] in ("stale", "unverified"):
            detail = "Changed since it was last verified. Verify it again." if st["state"] == "stale" else "Not verified yet."
        elif chk and not ok:
            detail = chk.get("message") or "The last check failed."
        else:
            detail = f"Verified {chk['ran_at']}." if chk else ""
        add(gid, f"{BY_NAME[name].title} works", ok, detail, name, code=(chk or {}).get("code") if not ok else None)

    add("G6", "End-to-end system test", None,
        "Not available yet: the system test (render a real reel without publishing) arrives in a later release. "
        "Until then a first generation can still fail on rendering or upload problems that no credential check sees.",
        None, blocking=False)

    conflicts = [f["name"] for n in TIER1 for f in states[n]["fields"] if f["required"] and f["conflict"]]
    gh = states["github"]["check"] or {}
    expiring = False
    if gh.get("expires_at"):
        try:
            expiring = datetime.fromisoformat(gh["expires_at"]) - datetime.now(timezone.utc) < EXPIRY_BLOCK
        except ValueError:
            expiring = False
    g7_ok = not conflicts and not expiring
    detail = ("The environment and the Config page hold different values for " + ", ".join(conflicts)
              + "; the environment's is used. Make them match or remove one." if conflicts
              else "The GitHub token expires within 3 days." if expiring else "No conflicts; nothing about to expire.")
    add("G7", "No conflicting or expiring credentials", g7_ok, detail, "github" if expiring else None)

    repo = github_actions.repository()
    add("G8", "Automation repository chosen", repo is not None,
        f"{repo}" if repo else "GITHUB_REPOSITORY isn't set (owner/name). There is no default on purpose.", "github")

    blocking = [c for c in conds if c["blocking"]]
    ready = all(c["ok"] for c in blocking)
    return {
        "ready_to_generate": ready,
        "config_version": config_store.config_version(),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "conditions": conds,
        "missing": [{"id": c["id"], "label": c["label"], "detail": c["detail"], "fix": c["fix"]}
                    for c in blocking if not c["ok"]],
        "not_covered": ["Provider outages", "Gemini's daily quota running out", "Topic sources blocked at that moment",
                        "A token revoked or expiring later", "Instagram rejecting a specific post",
                        "GitHub queue delays", "Rendering/upload failures (until the system test exists)"],
    }


def config_digest() -> str:
    """Opaque digest of which settings are set and from where (no values): lets a client notice changes."""
    from src import config_store
    entries, _ = config_store.snapshot()
    parts = [f"{f.name}:{bool(_env_value(f.name))}:{entries[f.name].version if f.name in entries else 0}"
             for f in FIELDS_BY_NAME.values()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def overview(checking: set[str] | None = None) -> dict:
    from src import config_store
    entries, err = config_store.snapshot()
    states = {i.name: integration_state(i.name, entries=entries, checking=i.name in (checking or set()))
              for i in INTEGRATIONS}
    try:
        key_state = config_store.check_canary()
    except config_store.StoreError as e:
        key_state = e.code
    except Exception:  # noqa: BLE001
        key_state = "database.unreachable"
    return {
        "integrations": [states[i.name] for i in INTEGRATIONS],
        "readiness": readiness(states),
        "precedence": "store" if (os.getenv("CONFIG_PRECEDENCE") or "env").strip().lower() == "store" else "env",
        "master_key": key_state,
        "store_error": err,
        "digest": config_digest(),
    }
