"""Config: set up and verify the integrations, see what "ready to generate" still needs.

Mounted under /api (signed in + CSRF on writes, see main.py); admin-only via require_admin.

Secrets are write-only: no response ever contains a secret or any part of one (only is_set, source,
a keyed fingerprint, who/when, and verification results whose evidence is non-secret). Saving is
verify-then-store: a value that fails verification is never stored, so a typo can't replace a working
value. Verification calls only fixed provider hosts (no user-supplied URLs).
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from api.app.deps import CurrentUser
from api.app.ratelimit import RateLimiter
from api.app.routes.generate import require_admin
from src import activity, config_status, config_store
from src.config_schema import BY_NAME, FIELDS, FIELDS_BY_NAME, fields_of
from src.verify import CODES, effective_values, run as run_verify
from src.verify import telegram as tg
from src.verify.base import ERROR_CLASSES, clean_value

log = logging.getLogger("codexone.api.config")
router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_admin)])

limiter = RateLimiter()
RATE_LIMIT, RATE_WINDOW = 20, 60     # provider-touching calls per user per minute (spec section 5)
DEDUPE_SECONDS = 10                   # the same values verified again within this window reuse the result
DEEP_COOLDOWN = 60                    # Gemini real request / Telegram test message
MAX_VALUE = 4096

_locks: dict[str, threading.Lock] = {n.name: threading.Lock() for n in BY_NAME.values()}
_recent: dict[tuple[str, str, str], tuple[float, dict]] = {}   # (integration, fp, depth) -> (time, result)
_deep_at: dict[str, float] = {}


def _actor(user: CurrentUser) -> str:
    return user.username or user.email or f"user {user.id}"


def _fail(code: int, error: str, message: str, **extra) -> HTTPException:
    return HTTPException(code, detail={"code": error, "message": message, **extra})


def _integration(name: str):
    integ = BY_NAME.get(name)
    if not integ:
        raise _fail(404, "unknown_integration", "No such integration.")
    return integ


def _rate(user: CurrentUser) -> None:
    if wait := limiter.retry_after(str(user.id), RATE_LIMIT, RATE_WINDOW):
        raise HTTPException(429, detail={"code": "rate_limited", "message": "Too many checks. Wait a moment."},
                            headers={"Retry-After": str(wait)})
    limiter.hit(str(user.id))


class Values(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def _bounded(cls, v: dict[str, str]):
        if len(v) > 10 or any(len(x) > MAX_VALUE for x in v.values()):
            raise ValueError("Too many or too long values")
        return v


class VerifyBody(Values):
    depth: str = Field("live", pattern="^(format|live|deep)$")
    consent: bool = False             # required for depth=deep (uses quota / sends a message)


class SaveBody(Values):
    expected: dict[str, int] = Field(default_factory=dict)   # name -> version the client last saw (0 = new)
    save_unverified: bool = False     # only honoured when the provider couldn't answer (status unknown)


def _clean(integration: str, raw: dict[str, str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    allowed = {f.name for f in fields_of(integration)}
    bad = sorted(set(raw) - allowed)
    if bad:
        raise _fail(422, "unknown_field", f"Not a {BY_NAME[integration].title} setting: {', '.join(bad)}")
    out, notes = {}, {}
    for name, value in raw.items():
        v, n = clean_value(value, name)
        out[name] = v
        if n:
            notes[name] = n
    return out, notes


def _candidate(integration: str, cleaned: dict[str, str]) -> dict[str, str]:
    """What would be in effect after the change: current values, with the submitted ones on top."""
    merged = dict(effective_values(integration))
    for name, v in cleaned.items():
        if v:
            merged[name] = v
        else:
            merged.pop(name, None)
    return merged


def _verify(integration: str, values: dict[str, str], depth: str, actor: str, record: bool = True) -> dict:
    """Run one verification with de-duplication and a per-integration single-flight lock."""
    fp = config_status.values_fp(values) if values else None
    key = (integration, fp or "", depth)
    hit = _recent.get(key)
    if fp and hit and time.monotonic() - hit[0] < DEDUPE_SECONDS and depth != "deep":
        return {**hit[1], "reused": True}
    lock = _locks[integration]
    if not lock.acquire(blocking=False):
        raise _fail(409, "check_running", "A check of this integration is already running. Wait for it to finish.")
    try:
        result = run_verify(integration, values, depth)
        out = result.to_dict()
        if record:
            try:
                config_status.record(result, values=values, actor=actor, fp=fp)
            except Exception as e:  # noqa: BLE001 -- the provider already answered: return that, even if history can't be written
                log.warning("could not record %s check: %s", integration, type(e).__name__)
                out["recorded"] = False
        _recent[key] = (time.monotonic(), out)
        if len(_recent) > 200:
            _recent.clear()
        return out
    finally:
        lock.release()


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
@router.get("")
def overview() -> dict:
    checking = {n for n, lock in _locks.items() if lock.locked()}
    return config_status.overview(checking)


@router.get("/schema")
def schema() -> dict:
    """Static description of the integrations, fields and error codes (for the UI's copy and links)."""
    return {
        "integrations": [{"name": i.name, "title": i.title, "tier": i.tier, "blurb": i.blurb, "minutes": i.minutes,
                          "implemented": i.implemented, "editable": i.editable} for i in BY_NAME.values()],
        "fields": [{"name": f.name, "integration": f.integration, "label": f.label, "secret": f.secret,
                    "required": f.required, "shape": f.shape, "help": f.help, "advanced": f.advanced} for f in FIELDS],
        "error_classes": list(ERROR_CLASSES),
        "codes": {k: {"error_class": c.error_class, "message": c.message, "hint": c.hint} for k, c in CODES.items()},
    }


@router.get("/readiness")
def readiness() -> dict:
    return config_status.readiness()


@router.get("/{integration}/history")
def history(integration: str, limit: int = Query(10, ge=1, le=50)) -> dict:
    _integration(integration)
    return {"checks": config_status.history(integration, limit)}


# --------------------------------------------------------------------------- #
# Verify (with or without candidate values)
# --------------------------------------------------------------------------- #
@router.post("/{integration}/verify")
def verify(integration: str, body: VerifyBody, user: CurrentUser = Depends(require_admin)) -> dict:
    _integration(integration)
    cleaned, notes = _clean(integration, body.values)
    if body.depth == "deep":
        if not body.consent:
            raise _fail(400, "consent_required", "This test uses quota or sends a message. Confirm to run it.")
        wait = DEEP_COOLDOWN - (time.monotonic() - _deep_at.get(integration, -1e9))
        if wait > 0:
            raise HTTPException(429, detail={"code": "cooldown", "message": f"Wait {int(wait) + 1}s before running this test again."},
                                headers={"Retry-After": str(int(wait) + 1)})
    if body.depth != "format":
        _rate(user)
    values = _candidate(integration, cleaned)
    if body.depth == "deep":
        _deep_at[integration] = time.monotonic()
    result = _verify(integration, values, body.depth, _actor(user), record=body.depth != "format")
    if body.depth != "format":
        ok = result["status"] in ("valid", "warning")
        activity.record("config.verified" if ok else "config.verify_failed",
                        f"{BY_NAME[integration].title} check: {result['status']}"
                        + (f" ({result['code']})" if result.get("code") else ""),
                        level="info" if ok else "warning", source="config", actor=_actor(user),
                        detail={"integration": integration, "status": result["status"], "code": result.get("code"),
                                "depth": body.depth, "fields": sorted(cleaned)})
    return {"result": result, "cleaned": notes}


# --------------------------------------------------------------------------- #
# Save: verify first, store only what works
# --------------------------------------------------------------------------- #
@router.put("/{integration}")
def save(integration: str, body: SaveBody, user: CurrentUser = Depends(require_admin)) -> dict:
    integ = _integration(integration)
    if not integ.editable:
        raise _fail(400, "not_editable", f"{integ.title} can't be changed from the dashboard yet.")
    cleaned, notes = _clean(integration, body.values)
    if not cleaned:
        raise _fail(422, "nothing_to_save", "Enter at least one value.")
    to_store = {k: v for k, v in cleaned.items() if v}
    to_clear = [k for k, v in cleaned.items() if not v]
    if any(FIELDS_BY_NAME[k].required for k in to_clear):
        raise _fail(422, "required_field", "A required value can't be empty. Use Remove if you really want to delete it.")
    if set(cleaned) - set(body.expected):
        # optimistic concurrency: two admins editing the same setting must not silently overwrite each other
        raise _fail(422, "expected_versions", "Send the version you last saw for every field you change (0 if new).")
    _rate(user)
    values = _candidate(integration, cleaned)
    result = _verify(integration, values, "live", _actor(user))
    status = result["status"]
    saved_unverified = False
    if status == "unknown" and body.save_unverified:
        saved_unverified = True
    elif status not in ("valid", "warning"):
        activity.record("config.save_rejected", f"{integ.title} not saved: the check said {status}"
                        + (f" ({result['code']})" if result.get("code") else ""),
                        level="warning", source="config", actor=_actor(user),
                        detail={"integration": integration, "status": status, "code": result.get("code"),
                                "fields": sorted(cleaned)})
        if status == "unknown":
            raise _fail(409, "verify_unknown", "The provider couldn't be reached, so the value wasn't checked. "
                        "Nothing was saved. Try again, or save it unverified.", result=result, cleaned=notes, can_force=True)
        raise _fail(422, "verify_failed", result.get("message") or "The check failed. Nothing was saved.",
                    result=result, cleaned=notes)

    required = {f.name for f in FIELDS if f.required}
    try:
        if to_store:
            config_store.save(to_store, actor=_actor(user), source="ui", required=required,
                              expected={k: body.expected[k] for k in to_store})
        for name in to_clear:
            config_store.delete(name, expected=body.expected[name], required=required)
    except config_store.StoreError as e:
        if e.code == "conflict":
            raise _fail(409, "conflict", "Someone changed this setting since you opened the page. Reload and try again.",
                        fields=e.fields) from None
        info = CODES.get(e.code)
        raise _fail(503, e.code, info.message if info else "The settings store isn't available.",
                    hint=info.hint if info else None) from None

    activity.record("config.saved", f"Saved {integ.title} settings: {', '.join(sorted(cleaned))}"
                    + (" (unverified: provider unreachable)" if saved_unverified else ""),
                    level="warning" if saved_unverified else "info", source="config", actor=_actor(user),
                    detail={"integration": integration, "fields": sorted(cleaned), "status": status,
                            "unverified": saved_unverified})
    # The check above was recorded for `values`; the env may still override a saved field (shown in the state).
    return {"result": result, "cleaned": notes, "integration": config_status.integration_state(integration),
            "readiness": config_status.readiness()}


@router.delete("/{integration}/{field}")
def remove(integration: str, field: str, version: int = Query(..., ge=0),
           user: CurrentUser = Depends(require_admin)) -> Response:
    integ = _integration(integration)
    f = FIELDS_BY_NAME.get(field)
    if not integ.editable or not f or f.integration != integration:
        raise _fail(404, "unknown_field", "No such setting.")
    try:
        gone = config_store.delete(field, expected=version, required={x.name for x in FIELDS if x.required})
    except config_store.StoreError as e:
        if e.code == "conflict":
            raise _fail(409, "conflict", "Someone changed this setting since you opened the page. Reload and try again.") from None
        raise _fail(503, e.code, "The settings store isn't available.") from None
    if gone:
        activity.record("config.removed", f"Removed {integ.title} setting {field}", level="warning", source="config",
                        actor=_actor(user), detail={"integration": integration, "fields": [field]})
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Telegram helpers
# --------------------------------------------------------------------------- #
class TokenBody(BaseModel):
    token: str | None = Field(None, max_length=MAX_VALUE)   # a just-typed token; else the configured one
    confirm: bool = False


def _token(body: TokenBody) -> str:
    if body.token:
        return clean_value(body.token, "TG_BOT_TOKEN")[0]
    return effective_values("telegram").get("TG_BOT_TOKEN", "")


@router.post("/telegram/detect")
def detect_chat(body: TokenBody, user: CurrentUser = Depends(require_admin)) -> dict:
    """Chats that messaged the bot recently. Reads without confirming any update, so approvals still arrive."""
    _rate(user)
    token = _token(body)
    if not token:
        raise _fail(422, "verify.not_set", "Enter the bot token first.")
    if not _locks["telegram"].acquire(blocking=False):
        raise _fail(409, "check_running", "A Telegram check is already running.")
    try:
        chats, code = tg.detect_chats(token)
    finally:
        _locks["telegram"].release()
    if code:
        info = CODES[code]
        return {"chats": [], "code": code, "message": info.message, "hint": info.hint,
                "docs": f"/config/guide/errors#{code.replace('.', '-')}"}
    return {"chats": chats, "code": None}


@router.post("/telegram/delete-webhook")
def delete_webhook(body: TokenBody, user: CurrentUser = Depends(require_admin)) -> dict:
    if not body.confirm:
        raise _fail(400, "confirm_required", "Confirm removing the webhook.")
    _rate(user)
    token = _token(body)
    if not token:
        raise _fail(422, "verify.not_set", "Enter the bot token first.")
    code = tg.delete_webhook(token)
    activity.record("config.webhook_removed" if not code else "config.webhook_remove_failed",
                    "Removed the Telegram webhook so approvals can be read" if not code
                    else f"Couldn't remove the Telegram webhook ({code})",
                    level="warning", source="config", actor=_actor(user), detail={"integration": "telegram", "code": code})
    if code:
        raise _fail(502, code, CODES[code].message, hint=CODES[code].hint)
    return {"ok": True}
