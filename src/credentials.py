"""Resolve a configuration value for a specific user.

Per-user keys (TG_CHAT_ID, IG_*, YT_*) are looked up in user_config_store first,
then fall back to the global config_store / environment. Global keys go straight
to get_env().

active_user_id is a ContextVar set at the top of each publish/preview call so that
approve_bot, publish, and publish_youtube all read the right per-user credentials
without needing user_id threaded through every function signature.  asyncio.run()
copies the current context, so it propagates into async helpers automatically.
"""
from __future__ import annotations

import contextvars

from src.config import get_env
from src.config_schema import PER_USER_FIELD_NAMES

# Set this before calling any pipeline function for a specific item.
active_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "active_user_id", default=None
)


def get_for_user(name: str, user_id: int | None = None) -> str | None:
    """Resolve a setting for a user. Per-user keys check the user store first."""
    uid = user_id if user_id is not None else active_user_id.get()
    if uid and name in PER_USER_FIELD_NAMES:
        from src import user_config_store
        val = user_config_store.lookup(name, uid)
        if val:
            return val
    return get_env(name, required=False)
