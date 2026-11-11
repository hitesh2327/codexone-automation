"""Read the active user's taste/style preferences from the DB, with fallback to brand config.

Uses the same active_user_id ContextVar as credentials.py so pipeline stages
(gen_content, rank_topics, fetch_topics, render_*) can call get_user_taste()
without needing user_id threaded through every function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.credentials import active_user_id

_CAT_INVALID_RE = re.compile(r"[\x00-\x1f\x7f<>{}\[\]\\;\"`$]")
_TECH_NICHE_RE = re.compile(
    r"\b(?:software|engineering|dev(?:eloper|ops)?|ai|artificial intelligence|machine learning|ml|"
    r"llm|llms|algorithm\w*|data structure\w*|dsa|system design|cyber\w*|cloud|programming|"
    r"coding|linux|operating system\w*|web dev|backend|frontend|full[- ]?stack|tech(?:nology)?|fintech|crypto)\b",
    re.IGNORECASE,
)
DEFAULT_CATEGORY_WEIGHT = 20
MAX_CATEGORIES = 12


def is_tech_niche(niche: str | None) -> bool:
    """Return True when the creator's niche is software/tech/AI/dev."""
    if not niche or not niche.strip():
        return True
    return bool(_TECH_NICHE_RE.search(niche))


def clean_category_name(value: Any) -> str:
    """Validate and normalize a category name (1..64 Unicode chars, no control or markup metachars)."""
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError("Category name cannot be empty")
    if len(text) > 64:
        raise ValueError("Category name must be at most 64 characters")
    if _CAT_INVALID_RE.search(text):
        raise ValueError("Category contains invalid characters")
    return text


@dataclass
class CategoryConfig:
    name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    weight: int = DEFAULT_CATEGORY_WEIGHT
    prompt_style: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": list(self.keywords),
            "weight": self.weight,
            "prompt_style": self.prompt_style,
        }


@dataclass
class TopicSourceConfig:
    source_type: str  # "rss" | "substack" | "reddit"
    locator: str
    label: str = ""
    category: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "locator": self.locator,
            "label": self.label,
            "category": self.category,
            "enabled": self.enabled,
        }


def normalize_categories(
    raw: Any,
    default_cats: list[str] | None = None,
    default_weights: dict[str, int] | None = None,
) -> list[CategoryConfig]:
    """Normalize flat string lists or structured dicts into CategoryConfig objects."""
    weights_map = default_weights or {}
    items = list(raw) if isinstance(raw, (list, tuple)) else []
    if not items and default_cats:
        items = list(default_cats)

    out: list[CategoryConfig] = []
    seen: set[str] = set()
    for entry in items:
        if isinstance(entry, CategoryConfig):
            raw_name = entry.name
            desc = entry.description
            kws = list(entry.keywords)
            w = entry.weight
            style = entry.prompt_style
        elif isinstance(entry, dict):
            raw_name = entry.get("name") or entry.get("label") or ""
            desc = str(entry.get("description") or "").strip()[:300]
            raw_kws = entry.get("keywords") or []
            if isinstance(raw_kws, str):
                raw_kws = [k.strip() for k in raw_kws.split(",")]
            kws = [str(k).strip()[:64] for k in raw_kws if str(k).strip()][:20]
            try:
                w = int(entry.get("weight", weights_map.get(str(raw_name), DEFAULT_CATEGORY_WEIGHT)))
            except (TypeError, ValueError):
                w = DEFAULT_CATEGORY_WEIGHT
            style = str(entry.get("prompt_style") or "").strip()[:400]
        elif isinstance(entry, str):
            raw_name = entry
            desc = ""
            kws = []
            w = int(weights_map.get(raw_name.strip(), DEFAULT_CATEGORY_WEIGHT))
            style = ""
        else:
            continue

        try:
            name = clean_category_name(raw_name)
        except ValueError:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(CategoryConfig(
            name=name,
            description=desc,
            keywords=kws,
            weight=max(1, min(100, w)),
            prompt_style=style,
        ))
        if len(out) >= MAX_CATEGORIES:
            break
    return out


def normalize_sources(raw: Any) -> list[TopicSourceConfig]:
    """Normalize custom topic source entries stored in User.taste['sources']."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[TopicSourceConfig] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        if isinstance(entry, TopicSourceConfig):
            st, loc = entry.source_type, entry.locator
            label, cat, enabled = entry.label, entry.category, entry.enabled
        elif isinstance(entry, dict):
            st = str(entry.get("source_type") or "").strip().lower()
            loc = str(entry.get("locator") or "").strip()
            label = str(entry.get("label") or "").strip()[:80]
            cat = str(entry.get("category") or "").strip()[:64]
            enabled = bool(entry.get("enabled", True))
        else:
            continue
        if st not in ("rss", "substack", "reddit") or not loc:
            continue
        key = (st, loc.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(TopicSourceConfig(
            source_type=st,
            locator=loc,
            label=label,
            category=cat,
            enabled=enabled,
        ))
        if len(out) >= 20:
            break
    return out


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
    default_language: str | None = None
    default_post_format: str | None = None
    category_configs: list[CategoryConfig] = field(default_factory=list)
    sources: list[TopicSourceConfig] = field(default_factory=list)
    handle: str = ""

    def __post_init__(self) -> None:
        if not self.category_configs and self.categories:
            self.category_configs = normalize_categories(self.categories)
        elif self.category_configs and not self.categories:
            self.categories = [c.name for c in self.category_configs]

    def category_weights(self) -> dict[str, int]:
        """Return {category_name: weight} for weighted random selection."""
        return {c.name: max(1, int(c.weight)) for c in self.category_configs}

    def category_config(self, name: str) -> CategoryConfig | None:
        """Look up a CategoryConfig by name (case-insensitive fallback)."""
        for c in self.category_configs:
            if c.name == name:
                return c
        low = (name or "").casefold()
        for c in self.category_configs:
            if c.name.casefold() == low:
                return c
        return None

    def effective_handle(self) -> str:
        if self.handle:
            return self.handle
        from src.config import load_brand
        return str(load_brand().get("handle") or "")

    def effective_language(self) -> str:
        if self.default_language == "hi":
            return "Hinglish"
        if self.default_language == "en":
            return "English"
        from src.config import load_brand
        return str(load_brand().get("language") or "English")

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
    username = ""
    if uid:
        try:
            from src import db
            from src.db.models import User
            with db.session() as ses:
                user = ses.get(User, uid)
                if user:
                    username = user.username or ""
                    if user.taste:
                        taste = dict(user.taste)
        except Exception:  # noqa: BLE001
            pass

    from src.config import load_brand
    brand = load_brand()
    default_weights = dict(brand.get("topics_weight", {}))
    default_cats = list(default_weights.keys())

    niche = taste.get("niche") or "Software Engineering & Dev"
    raw_cats = taste.get("categories") or taste.get("category_configs")
    if raw_cats:
        configs = normalize_categories(raw_cats, default_weights=default_weights)
    elif is_tech_niche(niche):
        configs = normalize_categories(default_cats, default_weights=default_weights)
    else:
        configs = []
    sources = normalize_sources(taste.get("sources"))
    raw_handle = str(taste.get("handle") or "").strip()
    if not raw_handle and username:
        raw_handle = f"@{username}" if not username.startswith("@") else username

    lang = taste.get("default_language")
    fmt = taste.get("default_post_format")
    result = UserTaste(
        niche=niche,
        tone=taste.get("tone") or "Educational & Insightful",
        content_type=taste.get("content_type") or "Educational & How-To",
        aesthetic=taste.get("aesthetic") or "Dark Minimalist Luxury",
        template_style=taste.get("template_style") or "Technical Dark",
        target_audience=taste.get("target_audience") or "Developers & Tech Founders",
        prompt_instructions=taste.get("prompt_instructions") or "",
        categories=[c.name for c in configs],
        default_language=lang if lang in ("en", "hi") else None,
        default_post_format=fmt if fmt in ("carousel", "image_reel") else None,
        category_configs=configs,
        sources=sources,
        handle=raw_handle,
    )
    _CACHE[uid] = result
    return result


def user_generation_defaults(user_id: int | None = None) -> tuple[str | None, str | None]:
    """Return (default_language, default_post_format) configured on the user's (or owner's) taste."""
    uid = user_id if user_id is not None else active_user_id.get()
    if uid is None:
        try:
            from sqlalchemy import select
            from src import db
            from src.db.models import User
            if db.enabled():
                with db.session() as ses:
                    owner = ses.scalars(select(User).where(User.role == "owner").order_by(User.id.asc()).limit(1)).first()
                    if owner:
                        uid = owner.id
        except Exception:  # noqa: BLE001
            return None, None
    if uid is None:
        return None, None
    t = get_user_taste(uid)
    return t.default_language, t.default_post_format


def invalidate(user_id: int | None = None) -> None:
    """Call after saving new taste settings so the next pipeline run re-reads from DB."""
    _CACHE.pop(user_id, None)
    _CACHE.pop(None, None)
