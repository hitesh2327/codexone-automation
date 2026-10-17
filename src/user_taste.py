"""Read the active user's taste/style preferences from the DB, with fallback to brand config.

Uses the same active_user_id ContextVar as credentials.py so pipeline stages
(gen_content, rank_topics, fetch_topics, render_*) can call get_user_taste()
without needing user_id threaded through every function.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.credentials import active_user_id


@dataclass
class UserTaste:
    niche: str
    tone: str
    content_type: str
    aesthetic: str
    template_style: str
    target_audience: str
    prompt_instructions: str
    categories: list[str]

    def is_tech(self) -> bool:
        """Heuristic: is this a software/tech niche that benefits from code demos?"""
        tech_keywords = {
            "software", "engineering", "dev", "ai", "machine learning", "llm",
            "algorithm", "data structure", "dsa", "system design", "cyber",
            "cloud", "fintech", "crypto", "programming", "code", "linux", "os",
        }
        return any(kw in self.niche.lower() for kw in tech_keywords)


_CACHE: dict[int | None, UserTaste] = {}


def get_user_taste(user_id: int | None = None) -> UserTaste:
    """Return taste for the given user_id (or active_user_id if not provided)."""
    uid = user_id if user_id is not None else active_user_id.get()

    if uid in _CACHE:
        return _CACHE[uid]

    taste: dict = {}
    if uid:
        try:
            from src import db
            from src.db.models import User
            with db.session() as ses:
                user = ses.get(User, uid)
                if user and user.taste:
                    taste = dict(user.taste)
        except Exception:  # noqa: BLE001
            pass

    from src.config import load_brand
    brand = load_brand()
    default_cats = list(brand.get("topics_weight", {}).keys())

    result = UserTaste(
        niche=taste.get("niche") or "Software Engineering & Dev",
        tone=taste.get("tone") or "Educational & Insightful",
        content_type=taste.get("content_type") or "Educational & How-To",
        aesthetic=taste.get("aesthetic") or "Dark Minimalist Luxury",
        template_style=taste.get("template_style") or "Technical Dark",
        target_audience=taste.get("target_audience") or "Developers & Tech Founders",
        prompt_instructions=taste.get("prompt_instructions") or "",
        categories=taste.get("categories") or default_cats,
    )
    _CACHE[uid] = result
    return result


def invalidate(user_id: int | None = None) -> None:
    """Call after saving new taste settings so the next pipeline run re-reads from DB."""
    _CACHE.pop(user_id, None)
    _CACHE.pop(None, None)
