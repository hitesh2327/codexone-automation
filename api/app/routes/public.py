"""Unauthenticated endpoints: health check and the brand theme for the login page."""
from __future__ import annotations

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


@router.get("/public/brand")
def brand() -> dict:
    """Only presentation fields (colors, fonts, handle) -- nothing sensitive."""
    b = load_brand()
    return {"handle": b.get("handle", ""), "colors": b.get("colors", {}), "fonts": b.get("fonts", {})}
