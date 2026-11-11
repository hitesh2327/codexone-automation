"""TTL-cached emergency kill-switches, DB-backed feature flags, and per-tenant bonus quotas.

Stored inside the existing `settings` table (no schema migration required) and cached
in-process for 30 seconds with immediate invalidation on writes.
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any

from src import db

CACHE_TTL = 30.0
KILL_SWITCHES_KEY = "kill_switches"
FEATURE_FLAGS_KEY = "feature_flags"
BONUS_QUOTAS_KEY = "tenant_bonus_quotas"

DEFAULT_KILL_SWITCHES: dict[str, Any] = {
    "generation": False,
    "publishing": False,
    "signups": False,
    "reason": "",
    "updated_at": None,
    "updated_by": None,
}

DEFAULT_FEATURE_FLAGS: list[dict[str, Any]] = [
    {
        "key": "phase_a_tg_deeplink",
        "enabled": True,
        "rollout_pct": 100,
        "description": "1-click Telegram bot deep-link onboarding",
        "allow_user_ids": [],
        "allow_tiers": [],
        "updated_at": None,
    },
    {
        "key": "phase_b_ig_oauth",
        "enabled": False,
        "rollout_pct": 0,
        "description": "Central Instagram OAuth connect flow",
        "allow_user_ids": [],
        "allow_tiers": [],
        "updated_at": None,
    },
    {
        "key": "phase_b_yt_oauth",
        "enabled": False,
        "rollout_pct": 0,
        "description": "Central YouTube OAuth connect flow",
        "allow_user_ids": [],
        "allow_tiers": [],
        "updated_at": None,
    },
    {
        "key": "dynamic_categories_v2",
        "enabled": True,
        "rollout_pct": 100,
        "description": "Creator-defined niche categories and prompt instructions",
        "allow_user_ids": [],
        "allow_tiers": [],
        "updated_at": None,
    },
    {
        "key": "web_download_mode",
        "enabled": True,
        "rollout_pct": 100,
        "description": "Allow downloading rendered carousels and reels from the web desk",
        "allow_user_ids": [],
        "allow_tiers": [],
        "updated_at": None,
    },
]

_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def invalidate(key: str | None = None) -> None:
    """Clear one or all cached flag entries immediately after a write."""
    with _lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def reset() -> None:
    """Clear all in-process caches (used in tests)."""
    invalidate(None)


def _cached_setting(key: str, default: Any) -> Any:
    if not db.enabled():
        return default
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    val = db.get_setting(key, None)
    result = default if val is None else val
    with _lock:
        _cache[key] = (now, result)
    return result


# --------------------------------------------------------------------------- #
# Emergency kill-switches
# --------------------------------------------------------------------------- #
def get_kill_switches() -> dict[str, Any]:
    raw = _cached_setting(KILL_SWITCHES_KEY, None)
    out = dict(DEFAULT_KILL_SWITCHES)
    if isinstance(raw, dict):
        for k in ("generation", "publishing", "signups"):
            if k in raw:
                out[k] = bool(raw[k])
        if "reason" in raw:
            out["reason"] = str(raw.get("reason") or "")
        out["updated_at"] = raw.get("updated_at")
        out["updated_by"] = raw.get("updated_by")
    return out


def is_kill_switch_active(name: str) -> bool:
    if not db.enabled():
        return False
    return bool(get_kill_switches().get(name, False))


def set_kill_switches(updates: dict[str, Any], actor: str | None = None) -> dict[str, Any]:
    current = get_kill_switches()
    for k in ("generation", "publishing", "signups"):
        if k in updates and updates[k] is not None:
            current[k] = bool(updates[k])
    if "reason" in updates and updates["reason"] is not None:
        current["reason"] = str(updates["reason"])[:300]
    current["updated_at"] = _now_iso()
    current["updated_by"] = actor
    if db.enabled():
        db.set_setting(KILL_SWITCHES_KEY, current)
    invalidate(KILL_SWITCHES_KEY)
    return current


# --------------------------------------------------------------------------- #
# Feature flags
# --------------------------------------------------------------------------- #
def _normalize_flag(item: dict[str, Any]) -> dict[str, Any]:
    pct = int(item.get("rollout_pct", 0) or 0)
    pct = max(0, min(100, pct))
    return {
        "key": str(item["key"]).strip(),
        "enabled": bool(item.get("enabled", False)),
        "rollout_pct": pct,
        "description": str(item.get("description") or "")[:300],
        "allow_user_ids": [int(x) for x in (item.get("allow_user_ids") or []) if str(x).isdigit()],
        "allow_tiers": [str(x).lower() for x in (item.get("allow_tiers") or []) if x],
        "updated_at": item.get("updated_at"),
    }


def get_feature_flags() -> list[dict[str, Any]]:
    raw = _cached_setting(FEATURE_FLAGS_KEY, None)
    if isinstance(raw, list):
        return [_normalize_flag(x) for x in raw if isinstance(x, dict) and x.get("key")]
    if isinstance(raw, dict):
        return [_normalize_flag({"key": k, **v}) for k, v in raw.items() if isinstance(v, dict)]
    return [dict(f) for f in DEFAULT_FEATURE_FLAGS]


def set_feature_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _now_iso()
    dedup: dict[str, dict[str, Any]] = {}
    for item in flags:
        norm = _normalize_flag(item)
        if not norm["key"]:
            continue
        norm["updated_at"] = now
        dedup[norm["key"]] = norm
    out = list(dedup.values())
    if db.enabled():
        db.set_setting(FEATURE_FLAGS_KEY, out)
    invalidate(FEATURE_FLAGS_KEY)
    return out


def upsert_feature_flag(flag: dict[str, Any]) -> list[dict[str, Any]]:
    current = {f["key"]: f for f in get_feature_flags()}
    norm = _normalize_flag(flag)
    norm["updated_at"] = _now_iso()
    current[norm["key"]] = norm
    return set_feature_flags(list(current.values()))


def delete_feature_flag(key: str) -> list[dict[str, Any]]:
    current = [f for f in get_feature_flags() if f["key"] != key]
    return set_feature_flags(current)


def is_enabled(flag_key: str, user: Any = None) -> bool:
    """Evaluate a feature flag for a given user (with deterministic rollout bucketing)."""
    flag = next((f for f in get_feature_flags() if f["key"] == flag_key), None)
    if not flag or not flag["enabled"]:
        return False
    uid = getattr(user, "id", None) if user is not None else None
    tier = (getattr(user, "subscription_tier", "") or "").lower() if user is not None else ""
    if uid is not None and uid in flag.get("allow_user_ids", []):
        return True
    if tier and tier in flag.get("allow_tiers", []):
        return True
    pct = int(flag.get("rollout_pct", 0))
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    if uid is None:
        return False
    digest = hashlib.sha256(f"{flag_key}:{uid}".encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") % 100
    return bucket < pct


# --------------------------------------------------------------------------- #
# Per-tenant bonus / override quotas
# --------------------------------------------------------------------------- #
def all_bonus_quotas() -> dict[str, dict[str, Any]]:
    raw = _cached_setting(BONUS_QUOTAS_KEY, None)
    return dict(raw) if isinstance(raw, dict) else {}


def get_bonus_quota(user_id: int) -> dict[str, int]:
    entry = all_bonus_quotas().get(str(user_id))
    if not isinstance(entry, dict):
        return {"reels": 0, "carousels": 0}
    return {
        "reels": max(0, int(entry.get("reels", 0) or 0)),
        "carousels": max(0, int(entry.get("carousels", 0) or 0)),
    }


def set_bonus_quota(
    user_id: int,
    reels: int,
    carousels: int,
    *,
    mode: str = "add",
    actor: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    all_q = all_bonus_quotas()
    cur = get_bonus_quota(user_id)
    if mode == "set":
        new_reels = max(0, int(reels))
        new_carousels = max(0, int(carousels))
    else:
        new_reels = max(0, cur["reels"] + int(reels))
        new_carousels = max(0, cur["carousels"] + int(carousels))
    entry = {
        "reels": new_reels,
        "carousels": new_carousels,
        "updated_at": _now_iso(),
        "updated_by": actor,
        "reason": (reason or "")[:300],
    }
    all_q[str(user_id)] = entry
    if db.enabled():
        db.set_setting(BONUS_QUOTAS_KEY, all_q)
    invalidate(BONUS_QUOTAS_KEY)
    return entry
