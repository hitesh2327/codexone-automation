"""Verification library: is each integration's configuration well-formed AND does it actually work?

    from src import verify
    result = verify.run("telegram")                      # the values this process would use
    result = verify.run("gemini", {"GEMINI_API_KEY": k})  # candidate values (verify-before-save)
    result.to_dict()                                     # {status, checks[], error_class, code, message, hint, docs, ...}

CLI (reads the environment / config store; prints statuses, never values):
    python -m src.verify all|gemini|telegram|cloudinary|github|database [--depth format|live|deep] [--json]
See src/verify/base.py for the rules every verifier follows.
"""
from __future__ import annotations

import logging
import os

from src.config_schema import BY_NAME, INTEGRATIONS, fields_of
from src.redact import redact_exc
from src.verify import cloudinary, database, gemini, github, stubs, telegram
from src.verify.base import CODES, DEPTHS, Result, Run

log = logging.getLogger("codexone.verify")

VERIFIERS = {
    "database": database.verify,
    "gemini": gemini.verify,
    "telegram": telegram.verify,
    "cloudinary": cloudinary.verify,
    "github": github.verify,
    "instagram": stubs.make("instagram"),
    "youtube": stubs.make("youtube"),
    "email": stubs.make("email"),
    "google": stubs.make("google"),
}
assert set(VERIFIERS) == {i.name for i in INTEGRATIONS}


def effective_values(integration: str) -> dict[str, str]:
    """What this process would use for each field (environment or store, per src.config.resolve)."""
    from src.config import resolve
    if integration == "database":
        url = (os.environ.get("DATABASE_URL") or "").strip()
        return {"DATABASE_URL": url} if url else {}
    out = {}
    for f in fields_of(integration):
        value, _ = resolve(f.name)
        if value:
            out[f.name] = value
    return out


def run(integration: str, values: dict[str, str] | None = None, depth: str = "live") -> Result:
    """Verify one integration. Never raises: an unexpected crash is reported as status unknown."""
    if integration not in VERIFIERS:
        raise KeyError(integration)
    if depth not in DEPTHS:
        raise ValueError(f"depth must be one of {DEPTHS}")
    vals = effective_values(integration) if values is None else values
    try:
        return VERIFIERS[integration](vals, depth)
    except Exception as e:  # noqa: BLE001
        log.error("verifier %s crashed: %s", integration, redact_exc(e))
        r = Run(integration, depth)
        r.fail("check", "The check ran", "verify.crashed")
        return r.finish()


__all__ = ["BY_NAME", "CODES", "INTEGRATIONS", "Result", "VERIFIERS", "effective_values", "run"]
