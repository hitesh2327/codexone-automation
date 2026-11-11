"""Fetch trending topics from niche-appropriate sources (HN/dev.to/GitHub/arXiv for tech,
niche subreddits, and SSRF-hardened custom RSS/Atom/Substack feeds).

Each topic gets a keyword-based or source-pinned category hint when available, or "Other"
so rank_topics.py's Gemini semantic selector can evaluate top candidates for custom categories.

Usage:
    python -m src.fetch_topics            # fetch and save data/topics_<date>.json
    python -m src.fetch_topics --dry-run  # fetch and print, write nothing
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import socket
import sys
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

import requests
import urllib3
import urllib3.connection
import urllib3.connectionpool
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import DATA_DIR, ensure_dirs, get_env, load_brand
from src.credentials import active_user_id
from src.logger import get_logger

log = get_logger("fetch_topics")

USER_AGENT = "codexone-automation/0.1 (content research bot)"
TIMEOUT = 15
MAX_FEED_BYTES = 1024 * 1024  # 1 MB cap for custom RSS/Atom/Substack fetches
MAX_REDIRECTS = 3

REDDIT_SUBS = [
    "programming", "MachineLearning", "LocalLLaMA", "compsci", "cscareerquestions",
    "ExperiencedDevs", "leetcode", "systemdesign", "osdev", "linux",
]

# Subreddit presets for common non-tech niches. Keys are lowercase niche keyword fragments.
NICHE_REDDIT_MAP: dict[str, list[str]] = {
    "food": ["food", "cooking", "recipes", "Cooking", "AskCulinary", "MealPrepSunday"],
    "cooking": ["cooking", "recipes", "food", "Cooking", "AskCulinary"],
    "travel": ["travel", "solotravel", "backpacking", "digitalnomad", "TravelHacks"],
    "fashion": ["femalefashionadvice", "malefashionadvice", "streetwear", "fashionadvice"],
    "beauty": ["MakeupAddiction", "SkincareAddiction", "beauty", "AsianBeauty"],
    "fitness": ["fitness", "xxfitness", "weightlifting", "running", "bodyweightfitness"],
    "health": ["health", "nutrition", "Supplements", "loseit", "HealthyFood"],
    "wellness": ["wellness", "nutrition", "meditation", "HealthyFood", "selfimprovement"],
    "gaming": ["gaming", "pcgaming", "indiegaming", "gamedev", "truegaming"],
    "kids": ["Parenting", "daddit", "Mommit", "education", "ChildDevelopment"],
    "parenting": ["Parenting", "daddit", "Mommit", "toddlers"],
    "education": ["education", "learnprogramming", "languagelearning", "math", "science"],
    "finance": ["personalfinance", "investing", "financialindependence", "StockMarket", "Bogleheads"],
    "business": ["Entrepreneur", "smallbusiness", "startups", "marketing", "growmybusiness"],
    "startup": ["startups", "SaaS", "Entrepreneur", "indiehackers"],
    "saas": ["SaaS", "microsaas", "startups", "Entrepreneur"],
    "music": ["WeAreTheMusicMakers", "musictheory", "Guitar", "learnmusic", "audiophile"],
    "photography": ["photography", "photocritique", "analog", "AskPhotography"],
    "anime": ["anime", "animesuggest", "manga", "OnePiece", "Naruto"],
    "movies": ["movies", "television", "Letterboxd", "flicks", "TrueFilm"],
    "meme": ["memes", "dankmemes", "wholesomememes", "me_irl"],
    "comedy": ["funny", "memes", "standupshots", "Showerthoughts"],
    "sports": ["sports", "soccer", "nba", "Cricket", "formula1"],
    "real estate": ["realestate", "FirstTimeHomeBuyer", "REBubble", "investing"],
    "marketing": ["marketing", "digital_marketing", "SEO", "socialmedia", "PPC"],
    "career": ["jobs", "resumes", "careerguidance", "interviews"],
    "productivity": ["productivity", "selfimprovement", "gtd", "nosurf", "digitalminimalism"],
    "science": ["science", "Physics", "biology", "chemistry", "space"],
    "history": ["history", "AskHistorians", "worldhistory", "todayilearned"],
    "language": ["languagelearning", "linguistics", "duolingo", "LearnJapanese"],
    "diy": ["DIY", "HomeImprovement", "woodworking", "crafts"],
    "book": ["books", "suggestmeabook", "literature"],
    "design": ["web_design", "UI_Design", "graphic_design", "UXDesign"],
}

# Tech niches eligible for HN / dev.to / GitHub / arXiv default feeds.
_TECH_NICHE_RE = re.compile(
    r"\b(?:software|engineering|dev(?:eloper|ops)?|ai|artificial intelligence|machine learning|ml|"
    r"llm|llms|algorithm\w*|data structure\w*|dsa|system design|cyber\w*|cloud|programming|"
    r"coding|linux|operating system\w*|web dev|backend|frontend|full[- ]?stack|tech(?:nology)?)\b",
    re.IGNORECASE,
)

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

_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".arpa")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")
_XML_ENTITY_RE = re.compile(rb"<!(?:ENTITY|DOCTYPE)\b", re.IGNORECASE)
_NUMERIC_IP_PART_RE = re.compile(r"^(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)$")


def _is_tech_niche(niche: str | None) -> bool:
    """Return True only when the creator's niche is software/tech/AI/dev."""
    from src.user_taste import is_tech_niche
    return is_tech_niche(niche)


def _niche_reddit_subs(niche: str) -> list[str]:
    """Return Reddit subs for a given niche, without leaking tech subs into non-tech niches."""
    niche_lower = (niche or "").lower()
    for key, subs in NICHE_REDDIT_MAP.items():
        if key in niche_lower:
            return subs
    if _is_tech_niche(niche_lower):
        return REDDIT_SUBS
    return ["todayilearned", "LifeProTips", "explainlikeimfive"]


def _is_disallowed_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject loopback, private, link-local, metadata, reserved, multicast, and non-global IPs."""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or not ip_obj.is_global
    )


def _parse_noncanonical_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse hex, octal, or shorthand IPv4 literals (e.g. 0x7f.0.0.0x1, 0177.0.0.1, 2130706433)."""
    parts = host.split(".")
    if not (1 <= len(parts) <= 4) or not all(_NUMERIC_IP_PART_RE.match(p) for p in parts):
        return None
    try:
        nums = [int(p, 0) for p in parts]
    except ValueError as e:
        raise ValueError("Feed URL cannot target obfuscated numeric hostnames") from e
    if len(nums) == 1 and 0 <= nums[0] <= 0xFFFFFFFF:
        return ipaddress.IPv4Address(nums[0])
    if len(nums) == 2 and 0 <= nums[0] <= 0xFF and 0 <= nums[1] <= 0xFFFFFF:
        return ipaddress.IPv4Address((nums[0] << 24) | nums[1])
    if len(nums) == 3 and 0 <= nums[0] <= 0xFF and 0 <= nums[1] <= 0xFF and 0 <= nums[2] <= 0xFFFF:
        return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | nums[2])
    if len(nums) == 4 and all(0 <= n <= 0xFF for n in nums):
        return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3])
    raise ValueError("Feed URL cannot target numeric or obfuscated IP literals")


def _resolve_and_validate_url(url: str) -> tuple[str, str, str]:
    """Validate URL for SSRF, resolve DNS once, and return (normalized_url, host, pinned_ip)."""
    raw = (url or "").strip()
    if not raw or len(raw) > 500 or _CONTROL_RE.search(raw) or any(ch.isspace() for ch in raw):
        raise ValueError("Feed URL must be a single HTTPS link of at most 500 characters")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as e:
        raise ValueError("Feed URL is not a valid URL") from e

    if parts.scheme.lower() != "https":
        raise ValueError("Feed URL must use https:// (http://, file://, and other schemes are blocked)")
    if parts.username or parts.password:
        raise ValueError("Feed URL must not include embedded credentials")
    if port not in (None, 443):
        raise ValueError("Feed URL must use standard HTTPS port 443")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("Feed URL must include a valid hostname")
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise ValueError("Feed URL cannot target localhost or internal network domains")

    # Check canonical IPv4/IPv6 literals as well as hex/octal/shorthand IPv4 encodings.
    try:
        ip_literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(host)
    except ValueError:
        ip_literal = _parse_noncanonical_ipv4(host)

    pinned_ip = ""
    if ip_literal is not None:
        if _is_disallowed_ip(ip_literal):
            raise ValueError("Feed URL cannot target private, loopback, link-local, or reserved IP addresses")
        pinned_ip = str(ip_literal)
    else:
        if "." not in host or host.split(".")[-1].isdigit():
            raise ValueError("Feed URL must point to a valid public domain")
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise ValueError(f"Could not resolve feed host {host!r}") from e
        if not infos:
            raise ValueError(f"Could not resolve feed host {host!r}")
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            addr_str = sockaddr[0].split("%")[0]
            try:
                resolved_ip = ipaddress.ip_address(addr_str)
            except ValueError as e:
                raise ValueError(f"Invalid resolved IP address for {host!r}") from e
            if _is_disallowed_ip(resolved_ip):
                raise ValueError("Feed URL resolves to a blocked private, loopback, link-local, or reserved IP address")
            if not pinned_ip:
                pinned_ip = str(resolved_ip)
        if not pinned_ip:
            raise ValueError(f"Could not resolve feed host {host!r}")

    # Auto-convert Substack publication root URLs to their RSS /feed endpoint.
    path = parts.path
    if host.endswith(".substack.com") and path in ("", "/"):
        path = "/feed"
    normalized = urlunsplit(("https", parts.netloc, path, parts.query, ""))
    return normalized, host, pinned_ip


def validate_safe_feed_url(url: str) -> str:
    """Validate and normalize a custom RSS/Atom/Substack URL with strict SSRF defenses."""
    return _resolve_and_validate_url(url)[0]


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
    s.headers["User-Agent"] = USER_AGENT
    return s


def _clean(text: str, limit: int = 300) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


class _PinnedHTTPSAdapter(HTTPAdapter):
    """Pin socket connection target to the pre-validated IP while preserving TLS SNI & Host."""

    def __init__(self, pinned_host: str, pinned_ip: str, **kwargs):
        self._pinned_host = pinned_host.lower().rstrip(".")
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pinned_host = self._pinned_host
        pinned_ip = self._pinned_ip

        class _PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
            def __init__(self, host, *args, **kw):
                super().__init__(host, *args, **kw)
                if host.lower().rstrip(".") == pinned_host:
                    self._dns_host = pinned_ip

        class _PinnedHTTPSConnectionPool(urllib3.connectionpool.HTTPSConnectionPool):
            ConnectionCls = _PinnedHTTPSConnection

        self.poolmanager = urllib3.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )
        self.poolmanager.pool_classes_by_scheme = {
            **self.poolmanager.pool_classes_by_scheme,
            "https": _PinnedHTTPSConnectionPool,
        }


def _pinned_get(s: requests.Session, url: str, pinned_host: str, pinned_ip: str):
    """Perform s.get(...) with DNS pinned to pinned_ip (eliminates TOCTOU DNS rebinding)."""
    if not (isinstance(s, requests.Session) and hasattr(s, "adapters")):
        return s.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True)

    adapter = _PinnedHTTPSAdapter(pinned_host, pinned_ip)
    prefixes = (f"https://{pinned_host}/", f"https://{pinned_host}:443/")
    saved = {p: s.adapters.get(p) for p in prefixes}
    old_trust_env = s.trust_env
    try:
        s.trust_env = False
        for p in prefixes:
            s.mount(p, adapter)
        return s.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True)
    finally:
        s.trust_env = old_trust_env
        for p, prev in saved.items():
            if prev is None:
                s.adapters.pop(p, None)
            else:
                s.adapters[p] = prev
        adapter.close()


def _safe_fetch_bytes(s: requests.Session, url: str, max_bytes: int = MAX_FEED_BYTES) -> tuple[str, bytes]:
    """Fetch a feed URL safely: HTTPS-only, IP-pinned DNS, redirect-validated, capped at max_bytes."""
    current_url, pinned_host, pinned_ip = _resolve_and_validate_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        r = _pinned_get(s, current_url, pinned_host, pinned_ip)
        try:
            status_code = getattr(r, "status_code", 200)
            headers = getattr(r, "headers", {}) or {}
            if status_code in (301, 302, 303, 307, 308):
                loc = headers.get("Location") or headers.get("location")
                if not loc:
                    raise ValueError("Redirect response missing Location header")
                current_url, pinned_host, pinned_ip = _resolve_and_validate_url(urljoin(current_url, loc))
                continue
            r.raise_for_status()
            raw_cl = headers.get("Content-Length") or headers.get("content-length")
            if raw_cl is not None:
                try:
                    if int(raw_cl) > max_bytes:
                        raise ValueError("Feed response exceeds 1 MB size limit")
                except ValueError as e:
                    if "exceeds" in str(e):
                        raise
            if callable(getattr(r, "iter_content", None)):
                buf = bytearray()
                for chunk in r.iter_content(chunk_size=16384):
                    if chunk:
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            raise ValueError("Feed response exceeds 1 MB size limit")
                data = bytes(buf)
            else:
                data = getattr(r, "content", b"") or b""
                if len(data) > max_bytes:
                    raise ValueError("Feed response exceeds 1 MB size limit")
            return current_url, data
        finally:
            if callable(getattr(r, "close", None)):
                r.close()
    raise ValueError("Feed exceeded maximum redirect limit")


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def parse_feed_xml(
    data: bytes,
    source_label: str = "rss",
    limit: int = 30,
    pinned_category: str = "",
) -> list[Topic]:
    """Parse RSS 2.0 or Atom XML bytes into Topic objects using hardened expat validation."""
    if not data or not data.strip():
        return []
    if _XML_ENTITY_RE.search(data):
        raise ValueError("Feed XML contains disallowed DOCTYPE/ENTITY declarations")

    def _forbid_dtd(*_args, **_kwargs):
        raise ValueError("Feed XML contains disallowed DOCTYPE/ENTITY declarations")

    ep = expat.ParserCreate()
    ep.StartDoctypeDeclHandler = _forbid_dtd
    ep.EntityDeclHandler = _forbid_dtd
    ep.UnparsedEntityDeclHandler = _forbid_dtd
    ep.ExternalEntityRefHandler = _forbid_dtd
    try:
        ep.Parse(data, True)
    except expat.ExpatError as e:
        raise ValueError(f"Invalid RSS/Atom XML: {e}") from e

    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"Invalid RSS/Atom XML: {e}") from e

    def _tag_name(el: ET.Element) -> str:
        return el.tag.rsplit("}", 1)[-1].lower()

    def _child_text(parent: ET.Element, *names: str) -> str:
        want = set(names)
        for ch in parent:
            if _tag_name(ch) in want and ch.text:
                return ch.text.strip()
        return ""

    out: list[Topic] = []
    root_name = _tag_name(root)
    extra = {"pinned_category": pinned_category} if pinned_category else {}

    if root_name == "rss" or root.find("channel") is not None:
        channel = root if root_name == "channel" else root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item"):
            title = _clean(_child_text(item, "title"), 250)
            link = _child_text(item, "link", "guid")
            summary = _clean(_child_text(item, "encoded", "description", "summary"))
            published = _child_text(item, "pubdate", "date", "published")
            if not title:
                continue
            out.append(Topic(
                title=title,
                url=link,
                source=source_label,
                score=0.0,
                summary=summary,
                published=published,
                category=pinned_category or "Other",
                extra=dict(extra),
            ))
            if len(out) >= limit:
                break
        return out

    if root_name == "feed":
        for entry in root:
            if _tag_name(entry) != "entry":
                continue
            title = _clean(_child_text(entry, "title"), 250)
            link = ""
            for ch in entry:
                if _tag_name(ch) == "link":
                    href = ch.get("href") or (ch.text or "").strip()
                    rel = (ch.get("rel") or "alternate").lower()
                    if href and (rel == "alternate" or not link):
                        link = href
                        if rel == "alternate":
                            break
            summary = _clean(_child_text(entry, "summary", "content"))
            published = _child_text(entry, "published", "updated")
            if not title:
                continue
            out.append(Topic(
                title=title,
                url=link,
                source=source_label,
                score=0.0,
                summary=summary,
                published=published,
                category=pinned_category or "Other",
                extra=dict(extra),
            ))
            if len(out) >= limit:
                break
        return out

    raise ValueError("Unsupported feed format (expected RSS 2.0 or Atom)")


def fetch_rss(
    s: requests.Session,
    url: str,
    limit: int = 30,
    label: str = "",
    category: str = "",
) -> list[Topic]:
    """Fetch and parse a custom RSS/Atom/Substack feed safely (SSRF-hardened)."""
    resolved_url, data = _safe_fetch_bytes(s, url, max_bytes=MAX_FEED_BYTES)
    host = urlsplit(resolved_url).hostname or "rss"
    source_label = label or f"rss/{host.removeprefix('www.')}"
    return parse_feed_xml(data, source_label=source_label, limit=limit, pinned_category=category)


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


def fetch_reddit(
    s: requests.Session,
    limit: int,
    niche: str | None = None,
    subs: list[str] | None = None,
) -> list[Topic]:
    # One combined multireddit request (r/a+b+c) — per-sub requests get 429'd fast.
    if subs:
        chosen = [re.sub(r"^/?r/", "", sub.strip()) for sub in subs if sub.strip()]
        chosen = [sub for sub in chosen if _SUBREDDIT_RE.match(sub)]
    elif niche:
        chosen = _niche_reddit_subs(niche)
        log.info("reddit subs for niche %r: %s", niche, ", ".join(chosen[:5]))
    else:
        chosen = REDDIT_SUBS
    if not chosen:
        return []
    multi = "+".join(chosen)
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
# Niche-aware source routing
# --------------------------------------------------------------------------- #
def resolve_sources_for_user(taste: Any) -> dict[str, Any]:
    """Resolve tech feeds, subreddits, and RSS/Substack feeds for a UserTaste."""
    niche = str(getattr(taste, "niche", "") or "")
    is_tech = _is_tech_niche(niche)
    tech_feeds = ["hackernews", "devto", "github", "arxiv"] if is_tech else []

    custom_subs: list[str] = []
    custom_rss: list[dict[str, str]] = []
    for src in getattr(taste, "sources", []) or []:
        if not getattr(src, "enabled", True):
            continue
        st = getattr(src, "source_type", "")
        loc = str(getattr(src, "locator", "") or "").strip()
        label = str(getattr(src, "label", "") or "")
        cat = str(getattr(src, "category", "") or "")
        if st == "reddit":
            clean_sub = re.sub(r"^/?r/", "", loc)
            if _SUBREDDIT_RE.match(clean_sub):
                custom_subs.append(clean_sub)
        elif st in ("rss", "substack") and loc:
            if st == "substack" and "://" not in loc:
                slug = re.sub(r"[^a-z0-9-]", "", loc.lower())
                if slug:
                    loc = f"https://{slug}.substack.com/feed"
            custom_rss.append({"url": loc, "label": label, "category": cat})

    default_subs = _niche_reddit_subs(niche)
    reddit_subs = list(dict.fromkeys([*custom_subs, *default_subs]))

    # Non-tech users without custom RSS get a curated Google News topic RSS feed for their niche.
    rss_sources = list(custom_rss)
    if not is_tech and not rss_sources and niche.strip():
        rss_sources.append({
            "url": f"https://news.google.com/rss/search?q={quote_plus(niche.strip())}&hl=en-US&gl=US&ceid=US:en",
            "label": f"news/{niche.strip()[:24]}",
            "category": "",
        })

    return {
        "is_tech": is_tech,
        "tech_feeds": tech_feeds,
        "reddit_subs": reddit_subs,
        "rss_sources": rss_sources,
    }


# --------------------------------------------------------------------------- #
# Tagging + dedupe
# --------------------------------------------------------------------------- #
def _custom_keyword_regexes(taste: Any) -> dict[str, re.Pattern[str]]:
    out: dict[str, re.Pattern[str]] = {}
    for cfg in getattr(taste, "category_configs", []) or []:
        kws = [re.escape(k.strip()) for k in (getattr(cfg, "keywords", None) or []) if k.strip()]
        if kws:
            out[cfg.name] = re.compile(r"\b(?:" + "|".join(kws) + r")\b", re.IGNORECASE)
    return out


def categorize(t: Topic, niche: str | None = None, taste: Any = None) -> None:
    if t.extra.get("pinned_category"):
        t.category = str(t.extra["pinned_category"])
        return

    text = " ".join([t.title, t.summary, " ".join(map(str, t.extra.get("tags", []))),
                     " ".join(map(str, t.extra.get("topics", [])))])

    custom_rx = _custom_keyword_regexes(taste) if taste is not None else {}
    if custom_rx:
        hits = {cat: len(rx.findall(text)) for cat, rx in custom_rx.items()}
        hits = {k: v for k, v in hits.items() if v}
        t.category_hits = hits
        if hits:
            t.category = max(hits, key=lambda c: hits[c])
            return

    eff_niche = niche if niche is not None else getattr(taste, "niche", None)
    if _is_tech_niche(eff_niche):
        user_cats = set(getattr(taste, "categories", []) or []) if taste is not None else set()
        hits = {cat: len(rx.findall(text)) for cat, rx in _CATEGORY_RE.items()}
        if user_cats:
            hits = {k: v for k, v in hits.items() if k in user_cats}
        hits = {k: v for k, v in hits.items() if v}
        t.category_hits = hits
        if t.source == "arxiv" and (not user_cats or "AI" in user_cats):
            hits.setdefault("AI", 0)
            if not any(c in ("cs.DC", "cs.OS") for c in t.extra.get("categories", [])):
                hits["AI"] += 2
        if hits:
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


def load_posted(user_id: int | None = None) -> tuple[set[str], set[str]]:
    """URLs and titles already published for this tenant (or all if user_id=None)."""
    from src.queue_store import posted_entries
    uid = user_id if user_id is not None else active_user_id.get()
    items = posted_entries(user_id=uid)
    urls = {normalize_url(i["url"]) for i in items if i.get("url")}
    titles = {normalize_title(i["title"]) for i in items if i.get("title")}
    return urls, titles


def dedupe(topics: list[Topic], user_id: int | None = None) -> list[Topic]:
    posted_urls, posted_titles = load_posted(user_id=user_id)
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
def fetch_all_for_user(
    taste: Any,
    limit: int = 30,
    user_id: int | None = None,
) -> list[Topic]:
    """Fetch, categorize, normalize, and tenant-dedupe topics according to UserTaste."""
    plan = resolve_sources_for_user(taste)
    s = _session()
    raw: list[Topic] = []

    for name in plan["tech_feeds"]:
        try:
            got = SOURCES[name](s, limit)
            log.info("%-10s %3d items", name, len(got))
            raw.extend(got)
        except Exception as e:  # one broken source must not kill the run
            log.error("%-10s FAILED: %s", name, e)

    if plan["reddit_subs"]:
        try:
            got = fetch_reddit(s, limit, niche=getattr(taste, "niche", None), subs=plan["reddit_subs"])
            log.info("%-10s %3d items", "reddit", len(got))
            raw.extend(got)
        except Exception as e:
            log.error("%-10s FAILED: %s", "reddit", e)

    for rss in plan["rss_sources"]:
        try:
            got = fetch_rss(s, rss["url"], limit=limit, label=rss.get("label", ""), category=rss.get("category", ""))
            log.info("rss %-20s %3d items", rss.get("label") or rss["url"][:20], len(got))
            raw.extend(got)
        except Exception as e:
            log.error("rss %s FAILED: %s", rss["url"], e)

    for t in raw:
        categorize(t, niche=getattr(taste, "niche", None), taste=taste)
    normalize_scores(raw)
    topics = dedupe(raw, user_id=user_id)
    log.info("total %d raw → %d after dedupe", len(raw), len(topics))
    return topics


def fetch_all(
    limit: int = 30,
    sources: list[str] | None = None,
    niche: str | None = None,
    user_id: int | None = None,
) -> list[Topic]:
    taste = None
    try:
        from src.user_taste import get_user_taste
        taste = get_user_taste(user_id) if user_id is not None else get_user_taste()
    except Exception:  # noqa: BLE001
        taste = None

    if sources is None and taste is not None:
        if niche is not None and getattr(taste, "niche", None) != niche:
            from dataclasses import replace
            try:
                taste = replace(taste, niche=niche)
            except TypeError:
                pass
        return fetch_all_for_user(taste, limit=limit, user_id=user_id)

    eff_niche = niche if niche is not None else (getattr(taste, "niche", None) if taste else None)
    s = _session()
    raw: list[Topic] = []
    for name in sources or SOURCES:
        try:
            if name == "reddit":
                got = fetch_reddit(s, limit, niche=eff_niche)
            else:
                got = SOURCES[name](s, limit)
            log.info("%-10s %3d items", name, len(got))
            raw.extend(got)
        except Exception as e:  # one broken source must not kill the run
            log.error("%-10s FAILED: %s", name, e)
    for t in raw:
        categorize(t, niche=eff_niche, taste=taste)
    normalize_scores(raw)
    topics = dedupe(raw, user_id=user_id)
    log.info("total %d raw → %d after dedupe", len(raw), len(topics))
    return topics


def print_report(topics: list[Topic], per_category: int) -> None:
    weights = load_brand().get("topics_weight", {})
    order = sorted(weights, key=weights.get, reverse=True) + ["Other"]
    seen_cats = list(dict.fromkeys([*order, *(t.category for t in topics)]))
    print(f"\n=== Today's topics ({datetime.now():%Y-%m-%d}) ===")
    for cat in seen_cats:
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
