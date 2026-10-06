"""Unauthenticated endpoints: health check and the brand theme for the login page."""
from __future__ import annotations

import re

from fastapi import APIRouter
from sqlalchemy import text

from src import db
from src.config import load_brand

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
def health() -> dict:
    ok = True
    try:
        with db.engine().connect() as c:
            c.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        ok = False
    return {"ok": ok, "db": ok}


_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _slot_times(b: dict) -> list[str]:
    """The daily posting slots (post_times_ist, or legacy post_time_ist) as sorted, zero-padded HH:MM.

    Malformed entries are dropped rather than failing the login page, which only uses them as copy.
    """
    raw = b.get("post_times_ist") or ([b["post_time_ist"]] if b.get("post_time_ist") else [])
    out = {f"{int(h):02d}:{m}" for h, m in (str(t).strip().split(":") for t in raw if _HHMM.match(str(t).strip()))}
    return sorted(out)


@router.get("/public/brand")
def brand() -> dict:
    """Only presentation fields (colors, fonts, handle, posting slot times) -- nothing sensitive."""
    b = load_brand()
    return {"handle": b.get("handle", ""), "colors": b.get("colors", {}), "fonts": b.get("fonts", {}),
            "post_times_ist": _slot_times(b)}
