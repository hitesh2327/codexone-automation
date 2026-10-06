"""Encrypted config store: settings saved on the dashboard's Config page, readable by the API and by
GitHub Actions jobs (both already have DATABASE_URL; both get CONFIG_MASTER_KEY).

Crypto (envelope encryption, `cryptography`'s AES-256-GCM):
  * a random 256-bit data key (DEK) encrypts each secret with a fresh 96-bit nonce; the associated data is
    "<name>|<row version>" so a ciphertext can't be moved to another setting or replayed as an older version;
  * the DEK is stored only wrapped (encrypted) by the master key CONFIG_MASTER_KEY (32 random bytes,
    base64), which lives outside the database (SSM on the Lambda, a GitHub secret on the runner);
  * a canary (known text under the DEK) proves at start-up that this process holds the right master key;
  * fingerprints are HMAC-SHA256 under a key derived from the DEK, so even a low-entropy value (a chat id)
    can't be brute-forced from its fingerprint.
Rotating the master key re-wraps one row (rotate_master_key); values are untouched.

Nothing here logs or returns a value. Non-secret settings (repository name, model, chat id) are stored in
plain text (`value_plain`) and are shown to the admin.

    python -m src.config_store generate-key            # print a new master key (store it, don't commit it)
    python -m src.config_store status                  # names, sources, canary: never values
    python -m src.config_store import-env [--apply]    # copy settings from the environment into the store
    python -m src.config_store rotate                  # CONFIG_MASTER_KEY=<old> CONFIG_MASTER_KEY_NEW=<new>
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from src.redact import register

log = logging.getLogger("codexone.config_store")

MASTER_ENV = "CONFIG_MASTER_KEY"
CACHE_TTL = 60.0              # seconds a process trusts its snapshot (writes invalidate it immediately)
_CANARY = b"codexone-config-canary-v1"
_DEK_AAD = b"codexone-config-dek|%d"


class StoreError(RuntimeError):
    """`code` is a catalogue code from src.verify.base (database.master_key_missing, ...) or `conflict`."""

    def __init__(self, code: str, message: str = "", fields: list[str] | None = None):
        super().__init__(message or code)
        self.code, self.fields = code, fields or []


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #
def generate_master_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


def master_key(raw: str | None = None) -> bytes:
    """The 32-byte master key from CONFIG_MASTER_KEY (standard or URL-safe base64, padding optional)."""
    raw = (os.environ.get(MASTER_ENV) if raw is None else raw) or ""
    raw = raw.strip()
    if not raw:
        raise StoreError("database.master_key_missing")
    try:
        padded = raw + "=" * (-len(raw) % 4)
        key = base64.urlsafe_b64decode(padded.replace("+", "-").replace("/", "_"))
    except (binascii.Error, ValueError):
        raise StoreError("database.master_key_invalid") from None
    if len(key) != 32:
        raise StoreError("database.master_key_invalid")
    return key


def _kek_id(kek: bytes) -> str:
    return hmac.new(kek, b"codexone-kek-id", hashlib.sha256).hexdigest()[:16]


def _aead(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # lazy: not needed in file mode
    return AESGCM(key)


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    return nonce, _aead(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    from cryptography.exceptions import InvalidTag
    try:
        return _aead(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise StoreError("database.key_mismatch") from None


def _value_aad(name: str, version: int) -> bytes:
    return f"{name}|{version}".encode()


@dataclass
class _Dek:
    version: int
    key: bytes

    def fingerprint(self, value: str) -> str:
        fp_key = hmac.new(self.key, b"codexone-fingerprint", hashlib.sha256).digest()
        return hmac.new(fp_key, value.encode(), hashlib.sha256).hexdigest()[:12]


_dek_cache: dict[tuple[str, int], bytes] = {}


def _load_dek(s, kek: bytes, create: bool = False) -> _Dek | None:
    from sqlalchemy import select
    from src.db.models import ConfigKey, ConfigMeta, utcnow
    row = s.scalars(select(ConfigKey).order_by(ConfigKey.version.desc()).limit(1)).first()
    if row is None:
        if not create:
            return None
        dek = secrets.token_bytes(32)
        nonce, wrapped = _seal(kek, dek, _DEK_AAD % 1)
        s.add(ConfigKey(version=1, wrapped_dek=wrapped, nonce=nonce, kek_id=_kek_id(kek)))
        meta = s.get(ConfigMeta, 1) or ConfigMeta(id=1, config_version=0)
        meta.canary_nonce, meta.canary = _seal(dek, _CANARY, b"canary")
        meta.updated_at = utcnow()
        s.add(meta)
        s.flush()
        _dek_cache[(_kek_id(kek), 1)] = dek
        return _Dek(1, dek)
    cache_key = (_kek_id(kek), row.version)
    if cache_key not in _dek_cache:
        _dek_cache[cache_key] = _open(kek, row.nonce, row.wrapped_dek, _DEK_AAD % row.version)
    return _Dek(row.version, _dek_cache[cache_key])


def check_canary(s=None) -> str:
    """'ok' | 'empty' (nothing encrypted yet) | raises StoreError (missing/invalid key, key_mismatch)."""
    from src import db
    from src.db.models import ConfigMeta
    kek = master_key()
    if s is None:
        with db.session() as s2:
            return check_canary(s2)
    dek = _load_dek(s, kek)
    if dek is None:
        return "empty"
    meta = s.get(ConfigMeta, 1)
    if not meta or not meta.canary:
        return "ok"
    if _open(dek.key, meta.canary_nonce, meta.canary, b"canary") != _CANARY:
        raise StoreError("database.key_mismatch")
    return "ok"


# --------------------------------------------------------------------------- #
# Reading: a per-process snapshot with a short TTL
# --------------------------------------------------------------------------- #
@dataclass
class Entry:
    value: str | None           # None when it's a secret we couldn't decrypt (no/incorrect master key)
    is_secret: bool
    version: int
    fingerprint: str | None
    source: str
    updated_at: datetime | None
    updated_by: str | None


_lock = threading.Lock()
_snapshot: dict[str, Entry] = {}
_snapshot_at = -1e9
_snapshot_error: str | None = None
_masked: set[str] = set()


def invalidate() -> None:
    global _snapshot_at
    with _lock:
        _snapshot_at = -1e9


def _load() -> tuple[dict[str, Entry], str | None]:
    from sqlalchemy import select
    from src import db
    from src.db.models import ConfigValue
    out: dict[str, Entry] = {}
    error = None
    with db.session() as s:
        rows = list(s.scalars(select(ConfigValue)))
        dek = None
        if any(r.is_secret for r in rows):
            try:
                kek = master_key()
                dek = _load_dek(s, kek)
            except StoreError as e:
                error = e.code
        for r in rows:
            value = r.value_plain
            if r.is_secret:
                value = None
                if dek and r.ciphertext and r.nonce:
                    try:
                        value = _open(dek.key, r.nonce, r.ciphertext, _value_aad(r.key, r.version)).decode()
                    except StoreError as e:
                        error = e.code
            out[r.key] = Entry(value, r.is_secret, r.version, r.fingerprint, r.source, r.updated_at, r.updated_by)
    return out, error


def snapshot(force: bool = False) -> tuple[dict[str, Entry], str | None]:
    """All stored settings (secrets decrypted in memory), refreshed at most every CACHE_TTL seconds.
    Never raises: a missing table, an unreachable database or a wrong key yields ({}, error-code)."""
    global _snapshot, _snapshot_at, _snapshot_error
    from src import db
    if not db.enabled():
        return {}, None
    now = time.monotonic()
    with _lock:
        if not force and now - _snapshot_at < CACHE_TTL:
            return _snapshot, _snapshot_error
        try:
            _snapshot, _snapshot_error = _load()
        except Exception as e:  # noqa: BLE001 -- the store must never break a caller of get_env
            _snapshot, _snapshot_error = {}, "database.unreachable"
            log.warning("config store unavailable (%s); using environment values only", type(e).__name__)
        _snapshot_at = now
        return _snapshot, _snapshot_error


def lookup(name: str) -> str | None:
    """The stored value of one setting (None if unset or undecryptable). Used by src.config.get_env."""
    entries, _ = snapshot()
    e = entries.get(name)
    if not e or not e.value:
        return None
    if e.is_secret:
        register(e.value)  # scrub it from every log line from now on
        if os.environ.get("GITHUB_ACTIONS") == "true" and name not in _masked:
            # GitHub masks only values it knows as secrets; a store value must be announced before use.
            print(f"::add-mask::{e.value}", flush=True)
            _masked.add(name)
    return e.value


# --------------------------------------------------------------------------- #
# Writing (one transaction per call: values + version bump, never partial)
# --------------------------------------------------------------------------- #
def save(values: dict[str, str], *, actor: str | None, source: str = "ui",
         expected: dict[str, int] | None = None, required: set[str] | frozenset[str] = frozenset()) -> dict[str, int]:
    """Store settings atomically. `expected` maps name -> the version the caller last saw (0 = "should not
    exist yet"); a mismatch raises StoreError('conflict') and nothing is written. Returns new versions.
    `required`: names whose change bumps config_version (readiness is bound to it)."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from src import db
    from src.config_schema import FIELDS_BY_NAME
    from src.db.models import ConfigMeta, ConfigValue, utcnow
    if not db.enabled():
        raise StoreError("database.not_set")
    unknown = [n for n in values if n not in FIELDS_BY_NAME]
    if unknown:
        raise ValueError(f"not a configurable setting: {', '.join(sorted(unknown))}")
    needs_key = any(FIELDS_BY_NAME[n].secret for n in values)
    kek = master_key() if needs_key else None
    out: dict[str, int] = {}
    try:
        with db.session() as s:
            dek = _load_dek(s, kek, create=True) if kek else None
            rows = {r.key: r for r in s.scalars(select(ConfigValue).where(ConfigValue.key.in_(list(values)))
                                                 .with_for_update())}
            if expected is not None:
                stale = [n for n in values if (rows[n].version if n in rows else 0) != expected.get(n, -1)]
                if stale:
                    raise StoreError("conflict", "changed by someone else", stale)
            bump = False
            for name, value in values.items():
                secret = FIELDS_BY_NAME[name].secret
                row = rows.get(name)
                version = (row.version + 1) if row else 1
                fp = dek.fingerprint(value) if (secret and dek) else hashlib.sha256(value.encode()).hexdigest()[:12]
                if row is None:
                    row = ConfigValue(key=name)
                    s.add(row)
                elif row.fingerprint != fp and name in required:
                    bump = True
                if row.fingerprint is None and name in required:
                    bump = True
                row.is_secret, row.version, row.fingerprint, row.source = secret, version, fp, source
                row.updated_at, row.updated_by = utcnow(), actor
                if secret:
                    row.nonce, row.ciphertext = _seal(dek.key, value.encode(), _value_aad(name, version))
                    row.value_plain, row.dek_version = None, dek.version
                else:
                    row.value_plain, row.nonce, row.ciphertext, row.dek_version = value, None, None, None
                out[name] = version
            if bump:
                meta = s.get(ConfigMeta, 1) or ConfigMeta(id=1, config_version=0)
                meta.config_version = (meta.config_version or 0) + 1
                meta.updated_at = utcnow()
                s.add(meta)
    except IntegrityError:  # two first-time saves of the same name raced
        raise StoreError("conflict", "changed by someone else", list(values)) from None
    finally:
        invalidate()
    for name, value in values.items():
        if FIELDS_BY_NAME[name].secret:
            register(value)
    return out


def delete(name: str, *, expected: int | None = None, required: set[str] | frozenset[str] = frozenset()) -> bool:
    from src import db
    from src.db.models import ConfigMeta, ConfigValue, utcnow
    try:
        with db.session() as s:
            row = s.get(ConfigValue, name, with_for_update=True)
            if row is None:
                return False
            if expected is not None and row.version != expected:
                raise StoreError("conflict", "changed by someone else", [name])
            s.delete(row)
            if name in required:
                meta = s.get(ConfigMeta, 1) or ConfigMeta(id=1, config_version=0)
                meta.config_version = (meta.config_version or 0) + 1
                meta.updated_at = utcnow()
                s.add(meta)
            return True
    finally:
        invalidate()


def config_version() -> int:
    from src import db
    from src.db.models import ConfigMeta
    if not db.enabled():
        return 0
    try:
        with db.session() as s:
            meta = s.get(ConfigMeta, 1)
            return int(meta.config_version) if meta else 0
    except Exception:  # noqa: BLE001
        return 0


def fingerprint(value: str) -> str | None:
    """Keyed fingerprint of any value (env or store) so the two can be compared without revealing either.
    None when there is no usable master key."""
    from src import db
    try:
        kek = master_key()
        with db.session() as s:
            dek = _load_dek(s, kek, create=True)
            return dek.fingerprint(value) if dek else None
    except Exception:  # noqa: BLE001
        return None


def rotate_master_key(old: str, new: str) -> int:
    """Re-wrap the data key under a new master key. Values are untouched. Returns the DEK version."""
    from sqlalchemy import select
    from src import db
    from src.db.models import ConfigKey, utcnow
    old_k, new_k = master_key(old), master_key(new)
    if old_k == new_k:
        raise ValueError("the new master key is the same as the old one")
    with db.session() as s:
        rows = list(s.scalars(select(ConfigKey).with_for_update()))
        if not rows:
            raise StoreError("database.not_set", "nothing to rotate: the store has no data key yet")
        for row in rows:
            dek = _open(old_k, row.nonce, row.wrapped_dek, _DEK_AAD % row.version)
            row.nonce, row.wrapped_dek = _seal(new_k, dek, _DEK_AAD % row.version)
            row.kek_id, row.rewrapped_at = _kek_id(new_k), utcnow()
        version = max(r.version for r in rows)
    _dek_cache.clear()
    invalidate()
    return version


# --------------------------------------------------------------------------- #
# CLI (prints names, counts and statuses only)
# --------------------------------------------------------------------------- #
def _env_value(name: str) -> str | None:
    from src.config import _ALIASES
    for key in _ALIASES.get(name, (name,)):
        v = os.environ.get(key)
        if v and v.strip():
            return v.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    from src import db
    from src.config_schema import FIELDS
    ap = argparse.ArgumentParser(prog="python -m src.config_store", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate-key", help="print a new random master key")
    sub.add_parser("status", help="which settings are stored (names only) and whether the master key matches")
    imp = sub.add_parser("import-env", help="copy configurable settings from the environment into the store")
    imp.add_argument("--apply", action="store_true", help="write (default: dry run, lists names only)")
    sub.add_parser("rotate", help="re-wrap the data key: CONFIG_MASTER_KEY=old, CONFIG_MASTER_KEY_NEW=new")
    args = ap.parse_args(argv)

    if args.cmd == "generate-key":
        print(generate_master_key())
        print("Store this as CONFIG_MASTER_KEY on the server (SSM) and as a GitHub Actions secret. "
              "Keep a copy in a password manager: without it, saved secrets can't be recovered.", file=sys.stderr)
        return 0
    if not db.enabled():
        print("DATABASE_URL is not set")
        return 1
    if args.cmd == "status":
        try:
            print("master key:", check_canary())
        except StoreError as e:
            print("master key:", e.code)
        entries, err = snapshot(force=True)
        for name in sorted(entries):
            e = entries[name]
            print(f"  {name:<26} {'secret' if e.is_secret else 'plain ':<6} v{e.version} source={e.source}"
                  f"{'' if e.value or not e.is_secret else '  (cannot decrypt)'}")
        print(f"{len(entries)} stored; config_version={config_version()}" + (f"; error={err}" if err else ""))
        return 0
    if args.cmd == "import-env":
        found = {f.name: v for f in FIELDS if (v := _env_value(f.name))}
        print(f"{'Importing' if args.apply else 'Would import'} {len(found)} settings (names only):")
        for name in sorted(found):
            print("  ", name)
        if args.apply and found:
            save(found, actor="import-env", source="import", required={f.name for f in FIELDS if f.required})
            print("Done. Verify them with: python -m src.verify all")
        return 0
    if args.cmd == "rotate":
        new = os.environ.get("CONFIG_MASTER_KEY_NEW", "")
        version = rotate_master_key(os.environ.get(MASTER_ENV, ""), new)
        print(f"Data key v{version} re-wrapped. Now set CONFIG_MASTER_KEY to the new key everywhere "
              "(server and GitHub secret) and remove CONFIG_MASTER_KEY_NEW.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
