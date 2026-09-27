"""Pick today's topic(s) from data/topics_<date>.json using brand category weights + Gemini.

Category is chosen by weighted random (seeded by date, so reruns are stable),
skipping the category used most recently. Gemini then picks the best candidate
within that category -- or proposes an evergreen topic when nothing trending
fits (common for DSA).

Usage:
    python -m src.rank_topics [--date YYYY-MM-DD] [--category DSA] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date

from pydantic import BaseModel, Field

from src.config import DATA_DIR, POSTED_FILE, load_brand
from src.llm import generate_json
from src.logger import get_logger

log = get_logger("rank_topics")

CATEGORY_DESCRIPTIONS = {
    "AI": "AI/ML/LLMs: how models, agents, RAG, embeddings, inference work; notable releases",
    "SystemDesign": "System design: scalability, databases, caching, queues, distributed systems",
    "DSA": "Data structures & algorithms: patterns, complexity, classic interview problems",
    "Interview": "Tech interviews & careers: prep strategy, common questions, negotiation",
    "OS": "Operating systems: processes, threads, memory, scheduling, file systems, Linux",
    "Dev": "General software development: languages, tools, practices, open source",
}


class RankedTopic(BaseModel):
    category: str
    title: str = Field(description="Short, specific post topic (not clickbait)")
    angle: str = Field(description="What the post teaches, in 1-2 sentences, beginner-friendly")
    source_url: str = Field(description="URL of the chosen candidate, or empty if evergreen")
    evergreen: bool = Field(description="True if not based on a trending candidate")
    why: str = Field(description="Why this is a good pick for today, 1 sentence")


def pick_category(weights: dict[str, int], seed: str, avoid: str | None) -> str:
    rng = random.Random(seed)
    pool = {c: w for c, w in weights.items() if c != avoid} or weights
    return rng.choices(list(pool), weights=list(pool.values()), k=1)[0]


def _posted() -> list[dict]:
    try:
        return json.loads(POSTED_FILE.read_text(encoding="utf-8") or "[]")
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def last_category() -> str | None:
    """Category of the most recently generated post (queued or published)."""
    from src import queue_store as q
    items = sorted(q.load(), key=lambda i: i.created_at)
    if items:
        return items[-1].category
    posted = _posted()
    return posted[-1].get("category") if posted else None


def recent_titles(limit: int = 40) -> list[str]:
    """Topics already covered recently (queue + posted) so a new slot never repeats one."""
    from src import queue_store as q
    titles = [i.topic for i in sorted(q.load(), key=lambda i: i.created_at)]
    titles += [p.get("title", "") for p in _posted()]
    return list(dict.fromkeys(t for t in reversed(titles) if t))[:limit]


def load_candidates(day: str) -> list[dict]:
    path = DATA_DIR / f"topics_{day}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run `python -m src.fetch_topics` first")
    return json.loads(path.read_text(encoding="utf-8"))


def rank(day: str, category: str | None = None, seed: str | None = None) -> RankedTopic:
    """seed: makes the category pick stable per run; use a different seed per daily slot."""
    brand = load_brand()
    weights = brand["topics_weight"]
    category = category or pick_category(weights, seed or day, last_category())
    covered = recent_titles()
    candidates = [c for c in load_candidates(day) if c["category"] == category]
    candidates.sort(key=lambda c: c.get("norm_score", 0), reverse=True)
    log.info("category=%s, %d trending candidates", category, len(candidates))

    lines = "\n".join(
        f"- {c['title']} | {c['source']} | score {c.get('norm_score', 0):.2f} | {c['url']}"
        + (f"\n  {c['summary'][:200]}" if c.get("summary") else "")
        for c in candidates[:25]
    ) or "(none)"

    prompt = f"""You choose today's Instagram post topic for {brand['handle']}, a tech education
account. Audience: students and junior developers in India. Language: {brand['language']}.

Category: {category} -- {CATEGORY_DESCRIPTIONS.get(category, category)}

Trending candidates in this category (title | source | popularity 0-1 | url):
{lines}

Pick ONE topic that:
- teaches a real, durable concept (explainable in a 45s reel and a 6-slide carousel),
- is technically accurate and not hype or clickbait,
- is relevant to the audience (not niche product drama, not non-English repos, not company news with no lesson).

Prefer a trending candidate if one is genuinely teachable; you may reframe it into the
underlying concept (e.g. a trending agent repo -> "How AI coding agents use tools").
If no candidate is suitable, propose a classic evergreen {category} topic instead and set
evergreen=true with source_url="". Set category to "{category}".

Already covered recently -- do NOT pick any of these or a near-duplicate:
{chr(10).join("- " + t for t in covered) or "(none)"}"""

    result = generate_json(prompt, RankedTopic, temperature=0.4)
    result.category = category
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pick today's topic with Gemini")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--category", choices=list(CATEGORY_DESCRIPTIONS))
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
