"""Scrub secrets out of text before it is logged, stored in the activity log, or sent to Telegram.

Two layers, both always on:
  1. Known values: every secret the process knows (the secret environment variables below, plus any
     value resolved from the encrypted config store via register()) is replaced wherever it appears,
     including its URL-encoded form (a token inside a request URL is percent-encoded).
  2. Shapes: credentials that look like credentials even when we never saw the value: `access_token=...`
     and `key=...` query parameters, `bot<id>:<secret>` Telegram URL paths, `cloudinary://key:secret@cloud`,
     `scheme://user:password@host` URLs, Authorization headers, and well-known token prefixes.

    from src.redact import redact, redact_exc
    log.warning("upload failed: %s", e)          # the logging filter scrubs this automatically
    notify(f"failed: {redact_exc(e)}")          # explicit, for text that leaves the process

The logging filter is installed by src.logger (and api.app.main for the API's root handlers).
"""
from __future__ import annotations

import logging
import os
import re
import threading
from urllib.parse import quote, unquote, urlsplit

MASK = "[REDACTED]"
_MIN_LEN = 6  # shorter "secrets" (e.g. an empty or test value) would shred ordinary text

# Environment variables whose values are secret. Names only; values are read at redaction time so a
# value set later (tests, Lambda cold start) is still covered.
SECRET_ENV_NAMES: tuple[str, ...] = (
    "TG_BOT_TOKEN", "GEMINI_API_KEY", "CLOUDINARY_URL", "COUDNARY_API_ENV_VAR", "CLOUDINARY_API_ENV_VAR",
    "IG_ACCESS_TOKEN", "IG_APP_SECRET", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN", "GITHUB_DISPATCH_TOKEN",
    "GH_PAT", "GITHUB_TOKEN", "DATABASE_URL", "DATABASE_URL_POOLED", "JWT_SECRET", "SESSION_SECRET",
    "ADMIN_PASSWORD", "GOOGLE_WEB_CLIENT_SECRET", "SMTP_PASS", "SMTP_PASSWORD", "CONFIG_MASTER_KEY", "ORIGIN_VERIFY",
)

_registered: set[str] = set()
_lock = threading.Lock()

_QUERY_KEYS = r"access_token|refresh_token|id_token|client_secret|api_key|apikey|api_secret|key|token|signature|password|passwd|secret|code"
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Telegram bot API paths: https://api.telegram.org/bot<id>:<secret>/getMe
    (re.compile(r"bot\d{3,}(?::|%3A)[A-Za-z0-9_-]{10,}", re.I), "bot" + MASK),
    # A bare Telegram token (<digits>:<35-ish chars>)
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"), MASK),
    # cloudinary://<key>:<secret>@<cloud>
    (re.compile(r"cloudinary://[^\s:@/]+:[^\s@/]+@", re.I), "cloudinary://" + MASK + "@"),
    # any scheme://user:password@host (database URLs, basic-auth URLs)
    (re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s:@/]+:[^\s@/]+@", re.I), r"\1" + MASK + "@"),
    # ?access_token=...&key=... in URLs and form bodies
    (re.compile(rf"([?&;](?:{_QUERY_KEYS})=)[^&\s\"'#<>]+", re.I), r"\1" + MASK),
    # Authorization: Bearer xxx / Basic xxx / OAuth xxx / token xxx (headers, curl lines, reprs)
    (re.compile(r"(authorization['\"]?\s*[:=]\s*['\"]?)(?:(?:bearer|basic|oauth|token)\s+)?[^\s'\",}]+", re.I), r"\1" + MASK),
    (re.compile(r"\b(Bearer|Basic|OAuth)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + MASK),
    # password=..., {"api_key": "..."}, 'x-goog-api-key': '...' -- but not prose such as "Password: hashing 101"
    (re.compile(r"((?:x-goog-api-key|api[_-]?key|api[_-]?secret|client[_-]?secret|refresh[_-]?token|access[_-]?token|"
                r"password|passwd|secret)(?:['\"]?\s*=\s*['\"]?|['\"]\s*:\s*['\"]|:\s*['\"]))[^\s'\",}&]{6,}", re.I),
     r"\1" + MASK),
    # Well-known token prefixes
    (re.compile(r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), MASK),            # Google API keys
    (re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{10,}"), MASK),           # Google OAuth client secrets
    (re.compile(r"\b1//[0-9A-Za-z_-]{20,}"), MASK),               # Google refresh tokens
    (re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}"), MASK),           # Google access tokens
    (re.compile(r"\b(?:IG|EAA)[A-Za-z0-9]{40,}\b"), MASK),        # Meta / Instagram user tokens
)


def _expand(value: str) -> set[str]:
    """A secret plus the forms it takes inside URLs, and the parts of composite secrets."""
    out = {value, quote(value, safe=""), quote(value, safe="/:@")}
    if "://" in value:  # cloudinary://key:secret@cloud, postgres://user:password@host/db
        try:
            parts = urlsplit(value)
            for p in (parts.password, parts.username if parts.scheme.startswith("cloudinary") else None):
                if p:
                    out |= {p, unquote(p), quote(unquote(p), safe="")}
        except ValueError:
            pass
    return {v for v in out if v and len(v) >= _MIN_LEN}


def register(value: str | None) -> None:
    """Remember a secret value resolved at runtime (e.g. from the config store) so it is always scrubbed."""
    if not value or len(value) < _MIN_LEN:
        return
    with _lock:
        _registered.update(_expand(value.strip()))


def _known() -> list[str]:
    vals: set[str] = set()
    for name in SECRET_ENV_NAMES:
        v = os.environ.get(name)
        if v and len(v.strip()) >= _MIN_LEN:
            vals |= _expand(v.strip())
    with _lock:
        vals |= _registered
    return sorted(vals, key=len, reverse=True)  # longest first: a URL before the password inside it


def redact(text: object) -> str:
    """`text` as a string with every known secret and credential-shaped substring replaced."""
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    if not s:
        return s
    for v in _known():
        if v in s:
            s = s.replace(v, MASK)
    for pattern, repl in _PATTERNS:
        s = pattern.sub(repl, s)
    return s


def redact_exc(e: BaseException, limit: int = 400) -> str:
    """`TypeName: message` of an exception, scrubbed and shortened (requests errors carry the URL)."""
    return redact(f"{type(e).__name__}: {e}")[:limit]


def redact_obj(obj):
    """Recursively scrub strings inside dicts/lists (activity-log `detail`)."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj


class RedactingFilter(logging.Filter):
    """Logging filter: formats the record once, scrubs message, traceback and stack, then freezes it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 -- a bad format string must not lose the record
            msg = str(record.msg)
        record.msg, record.args = redact(msg), None
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            except Exception:  # noqa: BLE001
                record.exc_text = ""
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


_FILTER = RedactingFilter()


def install(*loggers: logging.Logger) -> None:
    """Attach the filter to every handler of the given loggers (default: root and `codexone`). Idempotent."""
    handlers = [h for lg in (loggers or (logging.getLogger(), logging.getLogger("codexone"))) for h in lg.handlers]
    if logging.lastResort is not None:  # prints WARNING+ from loggers that have no handler at all
        handlers.append(logging.lastResort)
    for h in handlers:
        if not any(isinstance(f, RedactingFilter) for f in h.filters):
            h.addFilter(_FILTER)
