"""Resolve a configuration value for a specific user.

Per-user keys (TG_CHAT_ID, IG_*, YT_*) are looked up in user_config_store first,
then fall back to the global config_store / environment. Global keys go straight
to get_env().
"""
from __future__ import annotations

from src.config import get_env
from src.config_schema import PER_USER_FIELD_NAMES


def get_for_user(name: str, user_id: int | None = None) -> str | None:
    """Resolve a setting for a user. Per-user keys check the user store first."""
    if user_id and name in PER_USER_FIELD_NAMES:
        from src import user_config_store
        val = user_config_store.lookup(name, user_id)
        if val:
            return val
    return get_env(name, required=False)
