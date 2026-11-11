"""Pick today's topic(s) from data/topics_<date>.json using user category weights + Gemini.

Category is chosen by weighted random (seeded by date, so reruns are stable),
skipping the category used most recently. Gemini then picks the best candidate
within that category -- or evaluates the top 40 candidates semantically when a
custom category has 0 keyword hits, or proposes an evergreen topic when none fit.

Usage:
    python -m src.rank_topics [--date YYYY-MM-DD] [--category DSA] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.config import DATA_DIR, load_brand
from src.credentials import active_user_id
from src.llm import generate_json
from src.logger import get_logger

log = get_logger("rank_topics")

TECH_CATEGORY_DESCRIPTIONS = {
    "AI": "AI/ML/LLMs: how models, agents, RAG, embeddings, inference work; notable releases",
    "SystemDesign": "System design: scalability, databases, caching, queues, distributed systems",
    "DSA": "Data structures & algorithms: patterns, complexity, classic interview problems",
    "Interview": "Tech interviews & careers: prep strategy, common questions, negotiation",
    "OS": "Operating systems: processes, threads, memory, scheduling, file systems, Linux",
    "Dev": "General software development: languages, tools, practices, open source",
}


def _category_descriptions(categories: list[str], niche: str, taste: Any = None) -> dict[str, str]:
    """Return category name → description for the active user's niche."""
    result = {}
    for cat in categories:
        cfg = taste.category_config(cat) if taste is not None and hasattr(taste, "category_config") else None
        if cfg and getattr(cfg, "description", ""):
            result[cat] = cfg.description
        elif cat in TECH_CATEGORY_DESCRIPTIONS:
            result[cat] = TECH_CATEGORY_DESCRIPTIONS[cat]
        else:
            result[cat] = f"{cat}: trending and evergreen topics in {niche}"
    return result


class RankedTopic(BaseModel):
    category: str
    title: str = Field(description="Short, punchy search-friendly topic (4-8 words, specific, no fake clickbait)")
    angle: str = Field(description="Curiosity gap, costly production mistake, or counter-intuitive trade-off this post exposes (1-2 sentences)")
    source_url: str = Field(description="URL of the chosen candidate, or empty if evergreen")
    evergreen: bool = Field(description="True if not based on a trending candidate")
    why: str = Field(description="Why the target audience will save or share this post today, 1 sentence")
    prompt_style: str = Field(default="", description="Per-category tone and angle directives (populated after ranking)")


def pick_category(weights: dict[str, int], seed: str, avoid: str | None) -> str:
    rng = random.Random(seed)
    pool = {c: w for c, w in weights.items() if c != avoid} or weights
    return rng.choices(list(pool), weights=list(pool.values()), k=1)[0]


def _posted(user_id: int | None = None) -> list[dict]:
    from src.queue_store import posted_entries
    uid = user_id if user_id is not None else active_user_id.get()
    return posted_entries(user_id=uid)


def last_category(user_id: int | None = None) -> str | None:
    """Category of the most recently generated post (queued or published) for this tenant."""
    from src import queue_store as q
    uid = user_id if user_id is not None else active_user_id.get()
    items = sorted(q.load(user_id=uid), key=lambda i: i.created_at)
    if items:
        return items[-1].category
    posted = _posted(user_id=uid)
    return posted[-1].get("category") if posted else None


def recent_titles(limit: int = 40, user_id: int | None = None) -> list[str]:
    """Topics already covered recently (queue + posted) for this tenant so a slot never repeats one."""
    from src import queue_store as q
    uid = user_id if user_id is not None else active_user_id.get()
    titles = [i.topic for i in sorted(q.load(user_id=uid), key=lambda i: i.created_at)]
    titles += [p.get("title", "") for p in _posted(user_id=uid)]
    return list(dict.fromkeys(t for t in reversed(titles) if t))[:limit]


def load_candidates(day: str) -> list[dict]:
    path = DATA_DIR / f"topics_{day}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run `python -m src.fetch_topics` first")
    return json.loads(path.read_text(encoding="utf-8"))


def rank(
    day: str,
    category: str | None = None,
    seed: str | None = None,
    user_id: int | None = None,
) -> RankedTopic:
    """seed: makes the category pick stable per run; use a different seed per daily slot."""
    from src.user_taste import get_user_taste
    taste = get_user_taste(user_id) if user_id is not None else get_user_taste()

    brand = load_brand()
    if hasattr(taste, "category_weights") and taste.category_weights():
        weights = taste.category_weights()
    elif getattr(taste, "categories", None):
        weights = {c: 1 for c in taste.categories}
    else:
        from src.user_taste import is_tech_niche
        if is_tech_niche(getattr(taste, "niche", None)):
            weights = dict(brand["topics_weight"])
        elif category:
            weights = {category: 1}
        else:
            raise ValueError(f"No content categories configured for niche {getattr(taste, 'niche', '')!r}. Configure categories first.")

    cat_descs = _category_descriptions(list(weights.keys()), taste.niche, taste=taste)
    avoid = last_category(user_id=user_id) if user_id is not None else last_category()
    category = category or pick_category(weights, seed or day, avoid)
    covered = recent_titles(user_id=user_id) if user_id is not None else recent_titles()

    all_candidates = load_candidates(day)
    candidates = [c for c in all_candidates if c.get("category") == category]
    semantic_fallback = False
    if not candidates and all_candidates:
        # Custom/non-tech categories often have 0 keyword-tagged hits; evaluate top 40 across all sources.
        candidates = sorted(all_candidates, key=lambda c: c.get("norm_score", 0), reverse=True)[:40]
        candidate_limit = 40
        semantic_fallback = True
        log.info("category=%s had 0 keyword hits; passing top %d candidates to semantic selector",
                 category, len(candidates))
    else:
        candidates.sort(key=lambda c: c.get("norm_score", 0), reverse=True)
        candidate_limit = 25
        log.info("category=%s, %d trending candidates", category, len(candidates))

    lines = "\n".join(
        f"- {c['title']} | {c['source']} | score {c.get('norm_score', 0):.2f} | {c['url']}"
        + (f"\n  {c['summary'][:200]}" if c.get("summary") else "")
        for c in candidates[:candidate_limit]
    ) or "(none)"

    handle = taste.effective_handle() if hasattr(taste, "effective_handle") else (getattr(taste, "handle", "") or brand["handle"])
    language = taste.effective_language() if hasattr(taste, "effective_language") else brand["language"]

    cat_cfg = taste.category_config(category) if hasattr(taste, "category_config") else None
    cat_style = getattr(cat_cfg, "prompt_style", "") if cat_cfg else ""
    global_style = getattr(taste, "prompt_instructions", "") or ""
    combined_style = "\n".join(p for p in (cat_style, global_style) if p.strip())
    style_line = f"\nCategory style & angle: {cat_style}" if cat_style else ""

    candidate_heading = (
        f"Top {len(candidates)} trending candidates across sources (pick one that fits {category}, or set evergreen=true):"
        if semantic_fallback
        else "Trending candidates in this category (title | source | popularity 0-1 | url):"
    )

    prompt = f"""You choose today's Instagram post topic for {handle}.
Niche: {taste.niche}. Target audience: {taste.target_audience}. Language: {language}.

Category: {category} -- {cat_descs.get(category, category)}{style_line}

{candidate_heading}
{lines}

Pick ONE topic that:
- exposes a real curiosity gap, costly mistake, or counter-intuitive trade-off for {taste.target_audience} (triggers saves/shares, not dry textbook definitions),
- can be explained visually in an 18-24s reel and a 5-7 slide carousel,
- is factually accurate and not hype or clickbait,
- is relevant to the {taste.niche} niche and specifically the "{category}" content pillar.

Prefer a trending candidate if one is genuinely useful; you may reframe it.
If no candidate is suitable, propose an evergreen {category} topic and set evergreen=true.
Set category to "{category}".

Already covered recently -- do NOT pick any of these or a near-duplicate:
{chr(10).join("- " + t for t in covered) or "(none)"}"""

    result = generate_json(prompt, RankedTopic, temperature=0.4)
    result.category = category
    result.prompt_style = combined_style
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pick today's topic with Gemini")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--category")
    ap.add_argument("--dry-run", action="store_true", help="print only; write nothing")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    topic = rank(args.date, args.category)
    print(topic.model_dump_json(indent=2))
    if not args.dry_run:
        out = DATA_DIR / f"ranked_{args.date}.json"
        out.write_text(topic.model_dump_json(indent=2), encoding="utf-8")
        log.info("saved → %s", out.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
