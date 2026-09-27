"""Fetch trending tech topics from HN, Reddit, dev.to, GitHub, and arXiv.

Each topic gets a keyword-based category hint (AI, SystemDesign, DSA, Interview,
OS, Dev). Final selection is done later by rank_topics.py (Gemini); this module
just gathers, tags, and dedupes candidates against data/posted.json.

Usage:
    python -m src.fetch_topics            # fetch and save data/topics_<date>.json
    python -m src.fetch_topics --dry-run  # fetch and print, write nothing
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import DATA_DIR, POSTED_FILE, ensure_dirs, get_env, load_brand
from src.logger import get_logger

log = get_logger("fetch_topics")

USER_AGENT = "codexone-automation/0.1 (content research bot)"
TIMEOUT = 15

REDDIT_SUBS = [
    "programming", "MachineLearning", "LocalLLaMA", "compsci", "cscareerquestions",
    "ExperiencedDevs", "leetcode", "systemdesign", "osdev", "linux",
]

# Keyword → category hints. Word-boundary, case-insensitive. Order matters only
# for tie-breaking (first category with the most hits wins).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI": [
        "ai", "llm", "llms", "gpt", "claude", "gemini", "openai", "anthropic", "machine learning",
        "deep learning", "neural", "transformer", "diffusion", "rag", "agent", "agents", "agentic",
        "fine-tun\\w*", "embedding\\w*", "inference", "model", "models", "ml", "genai", "copilot",
        "reinforcement learning", "vector database", "prompt\\w*", "mcp",
    ],
    "SystemDesign": [
        "system design", "distributed", "scalab\\w+", "microservice\\w*", "architecture",
        "load balanc\\w+", "cach\\w+", "database\\w*", "sharding", "replication", "consensus",
        "raft", "paxos", "kafka", "queue", "latency", "throughput", "postgres\\w*", "redis",
        "kubernetes", "k8s", "cdn", "rate limit\\w*", "event sourcing", "cap theorem",
    ],
    "DSA": [
        "algorithm\\w*", "data structure\\w*", "leetcode", "graph", "tree", "trees", "heap",
        "hash ?map", "hash table", "dynamic programming", "dp", "binary search", "sorting",
        "linked list", "big-?o", "complexity", "recursion", "trie", "bfs", "dfs",
    ],
    "Interview": [
        "interview\\w*", "hiring", "job", "jobs", "resume", "offer", "faang", "career",
        "layoff\\w*", "salary", "recruit\\w*", "onboarding", "promotion",
    ],
    "OS": [
        "linux", "kernel", "operating system", "os", "scheduler", "memory management",
        "virtual memory", "syscall\\w*", "context switch\\w*", "multithread\\w*", "concurrency",
        "filesystem", "file system", "unix", "ebpf", "device driver\\w*", "page tables?",
    ],
    "Dev": [
        "python", "javascript", "typescript", "rust", "golang", "go", "java", "c\\+\\+",
        "react", "node", "api", "git", "github", "open source", "framework", "library",
        "compiler", "debug\\w*", "testing", "devops", "docker", "web", "frontend", "backend",
        "programming", "developer\\w*", "code", "coding", "cli", "ide", "vscode",
    ],
}
_CATEGORY_RE = {
    cat: re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)
    for cat, words in CATEGORY_KEYWORDS.items()
}


@dataclass
class Topic:
    title: str
    url: str
    source: str
    score: float = 0.0
    summary: str = ""
    published: str = ""
    category: str = "Other"
    category_hits: dict[str, int] = field(default_factory=dict)
    norm_score: float = 0.0  # 0..1 within its source, comparable across sources
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",), respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    return s


def _clean(text: str, limit: int = 300) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def fetch_hackernews(s: requests.Session, limit: int) -> list[Topic]:
    since = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    r = s.get(
        "https://hn.algolia.com/api/v1/search",
        params={"tags": "story", "numericFilters": f"created_at_i>{since},points>50",
                "hitsPerPage": limit},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        out.append(Topic(
            title=h.get("title") or "",
            url=h.get("url") or hn_url,
            source="hackernews",
            score=float(h.get("points") or 0),
            summary=_clean(h.get("story_text") or ""),
            published=h.get("created_at", ""),
            extra={"comments": h.get("num_comments", 0), "discussion": hn_url},
        ))
    return out


def fetch_reddit(s: requests.Session, limit: int) -> list[Topic]:
    # One combined multireddit request (r/a+b+c) — per-sub requests get 429'd fast.
    multi = "+".join(REDDIT_SUBS)
    try:
        return _reddit_json(s, multi, limit)
    except requests.RequestException as e:
        log.warning("reddit JSON failed (%s); falling back to RSS", e)
        return _reddit_rss(s, multi, limit)


def _reddit_json(s: requests.Session, sub: str, n: int) -> list[Topic]:
    r = s.get(f"https://www.reddit.com/r/{sub}/top.json",
              params={"t": "day", "limit": n}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for child in r.json()["data"]["children"]:
        d = child["data"]
        if d.get("stickied") or d.get("over_18"):
            continue
        permalink = "https://www.reddit.com" + d["permalink"]
        out.append(Topic(
            title=d["title"],
            url=permalink if d.get("is_self") else d.get("url", permalink),
            source=f"reddit/r/{d.get('subreddit', sub)}",
            score=float(d.get("score", 0)),
            summary=_clean(d.get("selftext", "")),
            published=datetime.fromtimestamp(d["created_utc"], timezone.utc).isoformat(),
            extra={"comments": d.get("num_comments", 0), "discussion": permalink},
        ))
    return out


def _reddit_rss(s: requests.Session, sub: str, n: int) -> list[Topic]:
    r = s.get(f"https://www.reddit.com/r/{sub}/top/.rss",
              params={"t": "day", "limit": n}, timeout=TIMEOUT)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        link = e.find("a:link", ns)
        cat = e.find("a:category", ns)
        out.append(Topic(
            title=e.findtext("a:title", "", ns),
            url=link.get("href") if link is not None else "",
            source=f"reddit/r/{cat.get('term') if cat is not None else sub}",
            score=0.0,  # RSS has no score
            summary=_clean(e.findtext("a:content", "", ns)),
            published=e.findtext("a:updated", "", ns),
        ))
    return out


def fetch_devto(s: requests.Session, limit: int) -> list[Topic]:
    r = s.get("https://dev.to/api/articles",
              params={"top": 1, "per_page": limit}, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        Topic(
            title=a["title"],
            url=a["url"],
            source="devto",
            score=float(a.get("public_reactions_count", 0)),
            summary=_clean(a.get("description", "")),
            published=a.get("published_at", ""),
            extra={"tags": a.get("tag_list", []), "comments": a.get("comments_count", 0)},
        )
        for a in r.json()
    ]


def fetch_github(s: requests.Session, limit: int) -> list[Topic]:
    """Proxy for GitHub trending: repos created in the last 7 days, by stars.

    GitHub has no official trending API; the search API is stable and free.
    Uses GITHUB_TOKEN if set (higher rate limit), otherwise unauthenticated.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    token = get_env("GITHUB_TOKEN", required=False)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = s.get(
        "https://api.github.com/search/repositories",
        params={"q": f"created:>{since} stars:>50", "sort": "stars", "order": "desc",
                "per_page": limit},
        headers=headers, timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [
        Topic(
            title=f"{repo['full_name']}: {repo.get('description') or ''}".strip(": "),
            url=repo["html_url"],
            source="github",
            score=float(repo.get("stargazers_count", 0)),
            summary=_clean(repo.get("description") or ""),
            published=repo.get("created_at", ""),
            extra={"language": repo.get("language"), "topics": repo.get("topics", [])},
        )
        for repo in r.json().get("items", [])
    ]


def fetch_arxiv(s: requests.Session, limit: int) -> list[Topic]:
    r = s.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.DC OR cat:cs.OS",
                "sortBy": "submittedDate", "sortOrder": "descending", "max_results": limit},
        timeout=30,
    )
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        cats = [c.get("term") for c in e.findall("a:category", ns)]
        out.append(Topic(
            title=_clean(e.findtext("a:title", "", ns), 250),
            url=(e.findtext("a:id", "", ns) or "").replace("http://", "https://"),
            source="arxiv",
            score=0.0,  # arXiv has no popularity signal
            summary=_clean(e.findtext("a:summary", "", ns)),
            published=e.findtext("a:published", "", ns),
            extra={"categories": cats},
        ))
    return out


SOURCES = {
    "hackernews": fetch_hackernews,
    "reddit": fetch_reddit,
    "devto": fetch_devto,
    "github": fetch_github,
    "arxiv": fetch_arxiv,
}


# --------------------------------------------------------------------------- #
# Tagging + dedupe
# --------------------------------------------------------------------------- #
def categorize(t: Topic) -> None:
    text = " ".join([t.title, t.summary, " ".join(map(str, t.extra.get("tags", []))),
                     " ".join(map(str, t.extra.get("topics", [])))])
    hits = {cat: len(rx.findall(text)) for cat, rx in _CATEGORY_RE.items()}
    hits = {k: v for k, v in hits.items() if v}
    t.category_hits = hits
    if t.source == "arxiv":
        hits.setdefault("AI", 0)
        if not any(c in ("cs.DC", "cs.OS") for c in t.extra.get("categories", [])):
            hits["AI"] += 2
    if hits:
        # Prefer specific categories over the generic "Dev" on ties.
        t.category = max(hits, key=lambda c: (hits[c], c != "Dev"))


def normalize_scores(topics: list[Topic]) -> None:
    """Score relative to the best item from the same source (stars ≠ upvotes)."""
    best: dict[str, float] = {}
    for t in topics:
        key = t.source.split("/")[0]
        best[key] = max(best.get(key, 0.0), t.score)
    for t in topics:
        top = best[t.source.split("/")[0]]
        t.norm_score = round(t.score / top, 3) if top else 0.3  # unscored feeds: neutral


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip().lower())
    host = p.netloc.removeprefix("www.").removeprefix("m.")
    return urlunsplit(("", host, p.path.rstrip("/"), "", ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def load_posted() -> tuple[set[str], set[str]]:
    if not POSTED_FILE.exists():
        return set(), set()
    try:
        items = json.loads(POSTED_FILE.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        log.error("%s is not valid JSON; ignoring it for dedupe", POSTED_FILE)
        return set(), set()
    urls = {normalize_url(i["url"]) for i in items if i.get("url")}
    titles = {normalize_title(i["title"]) for i in items if i.get("title")}
    return urls, titles


def dedupe(topics: list[Topic]) -> list[Topic]:
    posted_urls, posted_titles = load_posted()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out = []
    # Highest score first so the best copy of a cross-posted item survives.
    for t in sorted(topics, key=lambda x: x.score, reverse=True):
        u, ti = normalize_url(t.url), normalize_title(t.title)
        if not ti or u in posted_urls or ti in posted_titles:
            continue
        if u in seen_urls or ti in seen_titles:
            continue
        seen_urls.add(u)
        seen_titles.add(ti)
        out.append(t)
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def fetch_all(limit: int = 30, sources: list[str] | None = None) -> list[Topic]:
    s = _session()
    raw: list[Topic] = []
    for name in sources or SOURCES:
        try:
            got = SOURCES[name](s, limit)
            log.info("%-10s %3d items", name, len(got))
            raw.extend(got)
        except Exception as e:  # one broken source must not kill the run
            log.error("%-10s FAILED: %s", name, e)
    for t in raw:
        categorize(t)
    normalize_scores(raw)
    topics = dedupe(raw)
    log.info("total %d raw → %d after dedupe", len(raw), len(topics))
    return topics


def print_report(topics: list[Topic], per_category: int) -> None:
    weights = load_brand().get("topics_weight", {})
    order = sorted(weights, key=weights.get, reverse=True) + ["Other"]
    print(f"\n=== Today's topics ({datetime.now():%Y-%m-%d}) ===")
    for cat in order:
        items = sorted((t for t in topics if t.category == cat),
                       key=lambda t: t.norm_score, reverse=True)
        if not items:
            continue
        w = f" (weight {weights[cat]})" if cat in weights else ""
        print(f"\n## {cat}{w} — {len(items)} candidates")
        for t in items[:per_category]:
            score = f"{int(t.score):>5}" if t.score else "    -"
            print(f"  {score}  [{t.source}] {t.title[:100]}")
            print(f"         {t.url}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print only; write nothing")
    ap.add_argument("--limit", type=int, default=30, help="max items per source")
    ap.add_argument("--sources", nargs="+", choices=list(SOURCES), help="subset of sources")
    ap.add_argument("--show", type=int, default=6, help="items to print per category")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

    ensure_dirs()
    log.info("fetching topics (limit=%d, dry_run=%s)", args.limit, args.dry_run)
    topics = fetch_all(args.limit, args.sources)
    print_report(topics, args.show)

    if args.dry_run:
        log.info("dry run: not writing output")
    else:
        out = DATA_DIR / f"topics_{datetime.now():%Y-%m-%d}.json"
        out.write_text(json.dumps([asdict(t) for t in topics], indent=2, ensure_ascii=False),
                       encoding="utf-8")
        log.info("saved %d topics → %s", len(topics), out.relative_to(DATA_DIR.parent))
    return 0 if topics else 1


if __name__ == "__main__":
    sys.exit(main())
