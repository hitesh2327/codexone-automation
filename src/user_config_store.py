"""Per-user encrypted config store: TG chat ID, Instagram and YouTube credentials.

Uses the same AES-256-GCM envelope encryption as src.config_store (same DEK in config_keys table),
so CONFIG_MASTER_KEY must be set. Non-secret values (TG_CHAT_ID, IG_USER_ID) are stored in plain text.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

log = logging.getLogger("codexone.user_config_store")

CACHE_TTL = 60.0
_lock = threading.Lock()
_cache: dict[int, tuple[float, dict[str, str | None]]] = {}  # user_id -> (loaded_at, {key: value})


def _decrypt_row(row, dek) -> str | None:
    """Decrypt one UserConfigValue row using the store's shared DEK."""
    if not row.is_secret:
        return row.value_plain
    if not dek or not row.ciphertext or not row.nonce:
        return None
    from src.config_store import _open, _value_aad, StoreError
    try:
        return _open(dek.key, row.nonce, row.ciphertext, _value_aad(row.key, row.version)).decode()
    except StoreError:
        return None


def _load_user(user_id: int) -> dict[str, str | None]:
    from sqlalchemy import select
    from src import db
    from src.db.models import UserConfigValue
    from src.config_store import master_key, _load_dek, StoreError
    out: dict[str, str | None] = {}
    with db.session() as s:
        rows = list(s.scalars(select(UserConfigValue).where(UserConfigValue.user_id == user_id)))
        dek = None
        if any(r.is_secret for r in rows):
            try:
                dek = _load_dek(s, master_key())
            except StoreError:
                pass
        for r in rows:
            out[r.key] = _decrypt_row(r, dek)
    return out


def snapshot(user_id: int, force: bool = False) -> dict[str, str | None]:
    """Cached per-user values. Returns {} on any error."""
    from src import db
    if not db.enabled():
        return {}
    now = time.monotonic()
    with _lock:
        cached_at, data = _cache.get(user_id, (-1e9, {}))
        if not force and now - cached_at < CACHE_TTL:
            return data
    try:
        data = _load_user(user_id)
    except Exception as e:  # noqa: BLE001
        log.warning("user_config_store unavailable for user %d (%s)", user_id, type(e).__name__)
        data = {}
    with _lock:
        _cache[user_id] = (time.monotonic(), data)
    return data


def lookup(key: str, user_id: int) -> str | None:
    """The stored value for one key for one user. None if unset or undecryptable."""
    from src.redact import register
    from src.config_schema import FIELDS_BY_NAME
    val = snapshot(user_id).get(key)
    f = FIELDS_BY_NAME.get(key)
    if val and f and f.secret:
        register(val)
    return val


def invalidate(user_id: int) -> None:
    with _lock:
        _cache.pop(user_id, None)


def save(user_id: int, values: dict[str, str], *, actor: str | None) -> dict[str, int]:
    """Store per-user settings. Returns {key: new_version}."""
    from sqlalchemy import select
    from src import db
    from src.db.models import UserConfigValue, utcnow
    from src.config_schema import FIELDS_BY_NAME, PER_USER_FIELD_NAMES
    from src.config_store import master_key, _load_dek, _seal, _value_aad, StoreError
    from src.redact import register

    unknown = [n for n in values if n not in PER_USER_FIELD_NAMES]
    if unknown:
        raise ValueError(f"not a per-user setting: {', '.join(sorted(unknown))}")

    needs_key = any(FIELDS_BY_NAME[n].secret for n in values)
    kek = master_key() if needs_key else None
    out: dict[str, int] = {}
    with db.session() as s:
        dek = _load_dek(s, kek, create=True) if kek else None
        existing = {r.key: r for r in s.scalars(
            select(UserConfigValue).where(
                UserConfigValue.user_id == user_id,
                UserConfigValue.key.in_(list(values)),
            ).with_for_update()
        )}
        for name, value in values.items():
            secret = FIELDS_BY_NAME[name].secret
            row = existing.get(name)
            version = (row.version + 1) if row else 1
            if row is None:
                row = UserConfigValue(user_id=user_id, key=name)
                s.add(row)
            row.is_secret = secret
            row.version = version
            row.source = "ui"
            row.updated_at = utcnow()
            row.updated_by = actor
            if secret and dek:
                row.nonce, row.ciphertext = _seal(dek.key, value.encode(), _value_aad(name, version))
                row.value_plain = None
                row.dek_version = dek.version
                row.fingerprint = dek.fingerprint(value)
                register(value)
            else:
                import hashlib
                row.value_plain = value
                row.ciphertext = row.nonce = None
                row.dek_version = None
                row.fingerprint = hashlib.sha256(value.encode()).hexdigest()[:12]
            out[name] = version
    invalidate(user_id)
    return out


def delete(user_id: int, key: str) -> bool:
    """Remove one per-user setting. Returns True if it existed."""
    from src import db
    from src.db.models import UserConfigValue
    with db.session() as s:
        row = s.scalars(
            __import__('sqlalchemy', fromlist=['select']).select(UserConfigValue).where(
                UserConfigValue.user_id == user_id,
                UserConfigValue.key == key,
            ).with_for_update()
        ).first()
        if row is None:
            return False
        s.delete(row)
    invalidate(user_id)
    return True
