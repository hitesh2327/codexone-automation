"""Shared pieces of the verifiers: the result shape, the error catalogue, the paste cleaner, and a
redacting HTTP helper.

A verifier answers "is this configuration well-formed AND does it actually work?" at one of three depths:

    format  local rules only (instant, no network)
    live    read-only provider calls that prove the credential works (seconds)
    deep    explicit, opt-in actions with a visible effect or a cost (a Telegram test message, one Gemini
            generation request). Never run unless the caller passed depth="deep".

Rules every verifier follows (spec section 5 "Never in a check"):
  * never publish, never create queue items, never send Telegram messages with buttons, never call
    Instagram media_publish or YouTube videos.insert, never advance the Telegram getUpdates offset;
  * never spend generation quota unless depth="deep";
  * never echo, log or return a secret: evidence is non-secret (a bot @username, a cloud name);
  * only fixed provider hosts; user-supplied parts (cloud name, repo, model id) are validated by a
    strict pattern and URL-quoted before they reach a URL; redirects are not followed;
  * a provider outage is `unknown`, never `invalid`, so nobody throws away a good key because Google
    had a bad minute.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from src.redact import redact, redact_exc

TIMEOUT = 10  # seconds per provider call; the Lambda allows 30 s per request (infra/template.yaml)

# --------------------------------------------------------------------------- #
# Statuses and error classes
# --------------------------------------------------------------------------- #
STATUSES = ("not_set", "checking", "valid", "warning", "invalid", "unknown")
DEPTHS = ("format", "live", "deep")
ERROR_CLASSES = ("not_set", "format", "rejected", "forbidden", "expired", "quota", "rate_limited", "mismatch",
                 "not_found", "unreachable", "misconfigured", "unknown", "not_implemented")
# A failure of one of these classes means "the provider (or the network) didn't answer properly",
# not "your value is wrong".
PROVIDER_SIDE = {"unreachable", "unknown", "rate_limited"}
# Works, but with a caveat the user should know about.
SOFT = {"quota"}


@dataclass(frozen=True)
class Code:
    error_class: str
    message: str      # what happened, in plain words
    hint: str         # the exact next step


def docs_link(code: str | None, integration: str) -> str:
    """Where the Config page sends the user for this result (a troubleshooting entry or the guide)."""
    if code:
        return f"/config/guide/errors#{code.replace('.', '-')}"
    return f"/config/guide/{integration}"


# Every code a verifier can return. web/src/lib/config-guides.ts must have a troubleshooting entry for each
# one (tests/test_verify_catalogue.py fails otherwise).
CODES: dict[str, Code] = {
    # generic
    "verify.not_set": Code("not_set", "Not set yet.", "Open the setup step and paste the value."),
    "verify.not_implemented": Code("not_implemented", "This integration can't be verified from the dashboard yet.",
                                   "Its live check arrives in a later release. Until then it is not verified."),
    "verify.crashed": Code("unknown", "The check itself failed unexpectedly. Your value was not changed.",
                           "Try again in a minute. If it keeps happening, check the server log."),
    # Gemini
    "gemini.format": Code("format", "That doesn't look like an API key (it is empty or contains spaces or line breaks).",
                          "Copy the key again from Google AI Studio > API keys and paste only the key."),
    "gemini.model_format": Code("format", "That model name isn't valid (letters, digits, dots and dashes only).",
                                "Clear the model field to use the default, or copy a name from the Gemini models page."),
    "gemini.key_rejected": Code("rejected", "Gemini rejected this key.",
                                "Re-copy it from Google AI Studio > API keys (no spaces, no quotes), or create a new key."),
    "gemini.key_blocked": Code("rejected", "Google has blocked this key (reported as leaked or dormant).",
                               "Create a new key in Google AI Studio > API keys and paste it here."),
    "gemini.forbidden": Code("forbidden", "The key is valid but isn't allowed to call the Gemini API.",
                             "In Google Cloud > Credentials, check the key's API restrictions include the Generative Language API."),
    "gemini.billing": Code("quota", "Gemini says the project's prepaid credit is used up.",
                           "Add credit or switch the project's billing in Google AI Studio, then verify again."),
    "gemini.model_not_found": Code("not_found", "That Gemini model isn't available for this key.",
                                   "Clear the model field to use the default, or pick a model listed for your key."),
    "gemini.rate_limited": Code("rate_limited", "Gemini is rate-limiting this key right now.",
                                "Wait a minute and verify again. This is not a problem with the key."),
    "gemini.quota": Code("quota", "The key works, but today's free quota is used up.",
                         "Free quota resets at midnight Pacific time. Generation will work again after that."),
    "gemini.unavailable": Code("unknown", "Gemini didn't answer properly (server busy or down).",
                               "Try again in a few minutes. Your key may be fine."),
    "gemini.unreachable": Code("unreachable", "Couldn't reach Gemini from the server.",
                               "Check the server's internet access and try again."),
    "gemini.generation_empty": Code("misconfigured", "Gemini accepted the test request but returned no usable JSON.",
                                    "Try another model in Advanced, or verify again later."),
    # Telegram
    "telegram.token_format": Code("format", "That doesn't look like a bot token (expected digits, a colon, then letters).",
                                  "Send /mybots to @BotFather, choose your bot and copy its token again."),
    "telegram.chat_format": Code("format", "The chat ID must be a whole number (groups start with a minus sign).",
                                 "Use 'Detect my chat' instead of typing it."),
    "telegram.token_rejected": Code("rejected", "Telegram doesn't recognise this bot token.",
                                    "Send /mybots to @BotFather, choose your bot and copy its current token."),
    "telegram.webhook_set": Code("misconfigured", "A webhook is set on this bot, which blocks approvals (polling can't work).",
                                 "Remove the webhook (button on this card), unless another app really needs this bot."),
    "telegram.chat_not_found": Code("not_found", "The bot can't see that chat.",
                                    "Open your bot in Telegram and press Start (or add it to the group), then click Detect my chat."),
    "telegram.blocked": Code("forbidden", "The bot isn't allowed to post in that chat (blocked, or removed from the group).",
                             "Unblock the bot or add it back to the group, then verify again."),
    "telegram.no_chat_found": Code("not_found", "No message to the bot was found yet.",
                                   "In Telegram, open your bot, press Start (or send /start), then click Detect my chat again."),
    "telegram.poll_conflict": Code("rate_limited", "Another program is reading this bot's updates right now.",
                                   "Wait a minute and try again. Make sure no other app uses the same bot token."),
    "telegram.rate_limited": Code("rate_limited", "Telegram is rate-limiting this bot.",
                                  "Wait a minute and try again."),
    "telegram.unavailable": Code("unknown", "Telegram didn't answer properly.", "Try again in a few minutes."),
    "telegram.unreachable": Code("unreachable", "Couldn't reach Telegram from the server.",
                                 "Check the server's internet access and try again."),
    # Cloudinary
    "cloudinary.format": Code("format", "That isn't a Cloudinary API environment variable.",
                              "Copy the whole value that starts with cloudinary:// from Cloudinary > Settings > API Keys."),
    "cloudinary.placeholder": Code("format", "The value still contains the <your_api_key> / <your_api_secret> placeholders.",
                                   "On Cloudinary's API Keys page, replace the placeholders with your key and secret (shown on the same page), then paste again."),
    "cloudinary.rejected": Code("rejected", "Cloudinary rejected the API key, secret or cloud name.",
                                "Copy the whole 'API environment variable' again from Settings > API Keys."),
    "cloudinary.forbidden": Code("forbidden", "This Cloudinary key isn't allowed to upload or manage assets.",
                                 "Use a key with full access, or check its permissions under Settings > API Keys."),
    "cloudinary.not_found": Code("not_found", "Cloudinary doesn't know that cloud name.",
                                 "Copy the whole 'API environment variable' again; the cloud name is the part after @."),
    "cloudinary.rate_limited": Code("rate_limited", "Cloudinary is rate-limiting this account's admin requests.",
                                    "Wait a few minutes and verify again (the free plan allows 500 admin calls per hour)."),
    "cloudinary.upload_failed": Code("misconfigured", "Cloudinary accepted the key but refused a tiny test upload.",
                                     "Check the account isn't over its storage or credit limit in the Cloudinary console."),
    "cloudinary.delivery_failed": Code("misconfigured", "The test image uploaded but isn't publicly reachable.",
                                       "Instagram and Telegram fetch media from these links. Check the account's delivery or access settings."),
    "cloudinary.cleanup_failed": Code("unknown", "The check passed, but the test image couldn't be deleted.",
                                      "Delete it by hand in the Media Library (folder codexone/_selftest)."),
    "cloudinary.unavailable": Code("unknown", "Cloudinary didn't answer properly.", "Try again in a few minutes."),
    "cloudinary.unreachable": Code("unreachable", "Couldn't reach Cloudinary from the server.",
                                   "Check the server's internet access and try again."),
    # GitHub
    "github.repo_format": Code("format", "The repository must be written as owner/name.",
                               "Copy it from the repository's GitHub address, e.g. github.com/owner/name."),
    "github.token_format": Code("format", "That doesn't look like a GitHub token (it is empty or contains spaces).",
                                "Copy the token again right after generating it on GitHub."),
    "github.token_rejected": Code("rejected", "GitHub doesn't accept this token (mistyped, expired or deleted).",
                                  "Generate a new fine-grained token (this repository only, Actions: Read and write)."),
    "github.not_found": Code("not_found", "The repository wasn't found, or this token can't see it.",
                             "Check owner/name, and that the token's 'Repository access' includes this repository."),
    "github.forbidden": Code("forbidden", "The token can see the repository but lacks the Actions permission.",
                             "Edit the token: Repository permissions > Actions > Read and write."),
    "github.workflow_missing": Code("not_found", "A workflow this app needs isn't in the repository.",
                                    "Make sure the repository was created from the template and its .github/workflows folder is intact."),
    "github.workflow_disabled": Code("misconfigured", "A workflow this app needs is disabled in GitHub.",
                                     "Open the repository's Actions tab, choose the workflow and click Enable workflow."),
    "github.archived": Code("misconfigured", "The repository is archived (read-only), which is likely to stop workflows.",
                            "Unarchive it in the repository's Settings > General > Danger zone."),
    "github.branch": Code("misconfigured", "The repository's default branch isn't 'main', which the app starts workflows on.",
                          "Rename the default branch to main, or make sure a main branch with the workflows exists."),
    "github.classic_token": Code("misconfigured", "This is a classic token (ghp_), which can reach every repository you can.",
                                 "Create a fine-grained token (github_pat_) limited to this repository, Actions: Read and write."),
    "github.token_expiring": Code("expired", "The GitHub token expires soon.",
                                  "Generate a new token before it expires and paste it here."),
    "github.write_unconfirmed": Code("unknown", "Starting workflows (Actions: write) can only be proven by starting one.",
                                     "It is confirmed the first time a generation is started from the dashboard."),
    "github.rate_limited": Code("rate_limited", "GitHub is rate-limiting this token.", "Wait a few minutes and verify again."),
    "github.unavailable": Code("unknown", "GitHub didn't answer properly.", "Try again in a few minutes."),
    "github.unreachable": Code("unreachable", "Couldn't reach GitHub from the server.",
                               "Check the server's internet access and try again."),
    # Database
    "database.not_set": Code("not_set", "No database is configured (DATABASE_URL is empty).",
                             "DATABASE_URL is set when the app is deployed. Ask whoever installed it."),
    "database.format": Code("format", "DATABASE_URL isn't a postgres:// connection string.",
                            "Copy the connection string from the Neon console (Connect > Connection string)."),
    "database.unreachable": Code("unreachable", "Couldn't connect to the database.",
                                 "Neon sleeps after a few idle minutes; try again. If it persists, check the connection string."),
    "database.rejected": Code("rejected", "The database refused the username or password.",
                              "Copy a fresh connection string from the Neon console and update DATABASE_URL."),
    "database.schema_behind": Code("misconfigured", "The database schema is older than this version of the app.",
                                   "Run the database migration (the poll-approvals workflow runs 'alembic upgrade head')."),
    "database.read_only": Code("forbidden", "The database user can read but not write.",
                               "Use a connection string for a role that owns the database."),
    "database.pooled_url": Code("misconfigured", "DATABASE_URL points at Neon's connection pooler.",
                                "The API needs the direct connection string (host without '-pooler')."),
    "database.master_key_missing": Code("not_set", "CONFIG_MASTER_KEY isn't set, so saved secrets can't be encrypted or read.",
                                        "Generate one with 'python -m src.config_store generate-key' and set it on the server and in GitHub secrets."),
    "database.master_key_invalid": Code("format", "CONFIG_MASTER_KEY isn't a valid key (it must be 32 random bytes, base64).",
                                        "Generate one with 'python -m src.config_store generate-key'."),
    "database.key_mismatch": Code("mismatch", "CONFIG_MASTER_KEY doesn't match the key the saved settings were encrypted with.",
                                  "Set the same CONFIG_MASTER_KEY everywhere (server and GitHub secrets). If it is lost, re-enter the values."),
}


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    name: str
    label: str
    ok: bool | None             # None = not exercised at this depth / not provable
    depth: str = "live"
    evidence: str = ""          # non-secret
    code: str | None = None
    soft: bool = False          # a warning, not a failure


@dataclass
class Result:
    integration: str
    status: str
    depth: str
    checks: list[Check] = field(default_factory=list)
    error_class: str | None = None
    code: str | None = None
    message: str = ""
    hint: str = ""
    docs: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    checked_at: str = ""
    expires_at: str | None = None
    config_version: int | None = None
    implemented: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        # belt and braces: nothing a verifier returns may carry a secret
        d["message"], d["hint"] = redact(d["message"]), redact(d["hint"])
        for c in d["checks"]:
            c["evidence"] = redact(c["evidence"])
        d["evidence"] = {k: redact(v) if isinstance(v, str) else v for k, v in d["evidence"].items()}
        return d


class Run:
    """Collects checks for one verification and turns them into a Result."""

    def __init__(self, integration: str, depth: str):
        self.integration, self.depth = integration, depth
        self.checks: list[Check] = []
        self.evidence: dict[str, Any] = {}
        self.expires_at: str | None = None
        self._t0 = time.monotonic()

    def ok(self, name: str, label: str, evidence: str = "", depth: str = "live") -> None:
        self.checks.append(Check(name, label, True, depth, evidence))

    def fail(self, name: str, label: str, code: str, evidence: str = "", depth: str = "live") -> None:
        self.checks.append(Check(name, label, False, depth, evidence, code))

    def warn(self, name: str, label: str, code: str, evidence: str = "", depth: str = "live") -> None:
        self.checks.append(Check(name, label, True, depth, evidence, code, soft=True))

    def skip(self, name: str, label: str, why: str, depth: str = "live", code: str | None = None) -> None:
        self.checks.append(Check(name, label, None, depth, why, code))

    @property
    def failed(self) -> bool:
        return any(c.ok is False for c in self.checks)

    def finish(self, not_set: bool = False, code: str = "verify.not_set") -> Result:
        def cls(c: Check) -> str:
            return CODES[c.code].error_class if c.code in CODES else "unknown"
        # A quota failure means "the credential works, today's budget is spent": a warning, not invalid.
        hard = [c for c in self.checks if c.ok is False and cls(c) not in SOFT]
        soft = [c for c in self.checks if c.code and (c.soft or (c.ok is False and cls(c) in SOFT))]
        if not_set:
            status, lead = "not_set", Check("value", "Value", False, "format", "", code)
        elif hard:
            status = "unknown" if all(cls(c) in PROVIDER_SIDE for c in hard) else "invalid"
            # lead with the real problem, not an outage that happened alongside it
            lead = hard[0] if status == "unknown" else next(c for c in hard if cls(c) not in PROVIDER_SIDE)
        elif soft:
            status, lead = "warning", soft[0]
        else:
            status, lead = "valid", None
        code = lead.code if lead else None
        info = CODES.get(code) if code else None
        return Result(
            integration=self.integration, status=status, depth=self.depth, checks=self.checks,
            error_class=info.error_class if info else None, code=code,
            message=info.message if info else "", hint=info.hint if info else "",
            docs=docs_link(code, self.integration), evidence=self.evidence,
            latency_ms=int((time.monotonic() - self._t0) * 1000),
            checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), expires_at=self.expires_at,
        )


# --------------------------------------------------------------------------- #
# Paste cleaner (the server is authoritative; the web app mirrors it for instant feedback)
# --------------------------------------------------------------------------- #
_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"}  # zero-width / BOM / soft hyphen


def clean_value(raw: str | None, name: str = "") -> tuple[str, list[str]]:
    """Strip what copy/paste adds: whitespace, newlines, zero-width characters, wrapping quotes, a
    leading `NAME=` or `export NAME=`. Returns (value, notes) where notes say what was removed (never
    the value itself)."""
    if raw is None:
        return "", []
    notes: list[str] = []
    v = unicodedata.normalize("NFC", raw)
    if any(ch in v for ch in _INVISIBLE):
        v = "".join(ch for ch in v if ch not in _INVISIBLE)
        notes.append("removed invisible characters")
    for _ in range(3):  # layers come in any order: "NAME=value", NAME="value", export NAME='value'
        before = v
        stripped = v.strip()
        if stripped != v and "removed surrounding spaces or line breaks" not in notes:
            notes.append("removed surrounding spaces or line breaks")
        v = stripped
        if v.lower().startswith("export "):
            v = v[len("export "):].lstrip()
        if name:
            for n in {name, *_aliases(name)}:
                if v.upper().startswith(n.upper() + "="):
                    v = v[len(n) + 1:].strip()
                    notes.append(f"removed the leading {n}=")
                    break
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'`":
            v = v[1:-1]
            if "removed the quotes" not in notes:
                notes.append("removed the quotes")
        if v == before:
            break
    if name == "GITHUB_REPOSITORY":  # a pasted repository link -> owner/name
        m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s?#]+?)(?:\.git)?/?(?:[?#].*)?$", v, re.I)
        if m:
            v = f"{m.group(1)}/{m.group(2)}"
            notes.append("used owner/name from the link")
    return v, notes


def _aliases(name: str) -> tuple[str, ...]:
    from src.config import _ALIASES
    return _ALIASES.get(name, ())


def has_bad_chars(v: str) -> bool:
    """Whitespace or control characters inside a token-like value."""
    return any(ch.isspace() or unicodedata.category(ch).startswith("C") for ch in v)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Unreachable(Exception):
    """Network-level failure (DNS, TLS, timeout). Message is already scrubbed."""


def http(method: str, url: str, *, timeout: float = TIMEOUT, **kw) -> requests.Response:
    """One provider call: no redirects (a redirect could carry credentials to another host), a hard
    timeout, and any network error turned into Unreachable with the URL scrubbed out of its text."""
    try:
        return requests.request(method, url, timeout=timeout, allow_redirects=False, **kw)
    except requests.RequestException as e:
        raise Unreachable(redact_exc(e)) from None


def body(r: requests.Response) -> dict:
    """The JSON object in a response, or {} (never raises: providers sometimes answer HTML)."""
    try:
        data = r.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"_list": data}


Verify = Callable[[dict[str, str], str], Result]
