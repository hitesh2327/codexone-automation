"""HTML → PNG rendering with Jinja2 templates + a single headless Chromium (Playwright)."""
from __future__ import annotations

import html
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import Page, sync_playwright
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import STANDARD_TYPES

from src.config import TEMPLATES_DIR, load_brand

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html"]))


def brand_context() -> dict:
    b = load_brand()
    return {"colors": b["colors"], "fonts": b["fonts"], "handle": b["handle"]}


# --------------------------------------------------------------------------- #
# Text → HTML helpers
# --------------------------------------------------------------------------- #
_INLINE_CODE = re.compile(r"`([^`]+)`|\b(O\([^)]{1,20}\))")


def inline(text: str) -> str:
    """Escape text; render `code` and O(n)-style complexities as inline code."""
    text = strip_emphasis(text)
    out, pos = [], 0
    for m in _INLINE_CODE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        out.append(f'<code class="inline">{html.escape(m.group(1) or m.group(2))}</code>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def body_html(text: str) -> str:
    """Lines starting with '-', '•' or '*' become a bullet list; others paragraphs."""
    parts, bullets = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^[-•*]\s+(.*)", line)
        if m:
            bullets.append(f"<li>{inline(m.group(1))}</li>")
            continue
        if bullets:
            parts.append(f"<ul>{''.join(bullets)}</ul>")
            bullets = []
        parts.append(f"<p>{inline(line)}</p>")
    if bullets:
        parts.append(f"<ul>{''.join(bullets)}</ul>")
    return "".join(parts)


_EMPH = re.compile(r"\*([^*]+)\*")


def strip_emphasis(text: str) -> str:
    return _EMPH.sub(lambda m: m.group(1), text)


def emphasize(text: str) -> str:
    """Escape; *marked* words get the highlight color. No marks → last word highlighted."""
    if _EMPH.search(text):
        return _EMPH.sub(lambda m: f'<span class="hl">{m.group(1)}</span>', html.escape(text))
    parts = html.escape(text).split()
    return " ".join(parts[:-1] + [f'<span class="hl">{parts[-1]}</span>']) if parts else ""


def highlight_heading(text: str, words: int = 2) -> str:
    """Color *marked* words; else the tail (after ':' if present, else the last N words)."""
    if _EMPH.search(text):
        return emphasize(text)
    if ":" in text:
        head, tail = text.split(":", 1)
        return f'{html.escape(head)}:<br><span class="hl">{html.escape(tail.strip())}</span>'
    parts = text.split()
    if len(parts) <= words:
        return f'<span class="hl">{html.escape(text)}</span>'
    return f'{html.escape(" ".join(parts[:-words]))} <span class="hl">{html.escape(" ".join(parts[-words:]))}</span>'


def _token_class(ttype) -> str:
    while ttype not in STANDARD_TYPES and ttype.parent:
        ttype = ttype.parent
    return STANDARD_TYPES.get(ttype, "")


def code_html(code: str, language: str) -> str:
    """Syntax-highlight into one <span class="ln"> per line (for line numbers)."""
    try:
        lexer = get_lexer_by_name(language or "text", stripnl=False, ensurenl=False)
    except Exception:
        lexer = TextLexer()
    lines: list[list[str]] = [[]]
    for ttype, value in lexer.get_tokens(code.rstrip("\n")):
        cls = _token_class(ttype)
        for i, chunk in enumerate(value.split("\n")):
            if i:
                lines.append([])
            if chunk:
                esc = html.escape(chunk)
                lines[-1].append(f'<span class="{cls}">{esc}</span>' if cls else esc)
    return "".join(f'<span class="ln">{"".join(l) or " "}</span>' for l in lines)


# --------------------------------------------------------------------------- #
# Browser
# --------------------------------------------------------------------------- #
@contextmanager
def browser_page(width: int, height: int) -> Iterator[Page]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            yield page
        finally:
            browser.close()


def render_to_png(page: Page, template: str, context: dict, out: Path,
                  transparent: bool = False) -> Path:
    html_str = env.get_template(template).render(**context)
    page.set_content(html_str, wait_until="networkidle")
    page.evaluate("window.__fit ? window.__fit() : document.fonts.ready")
    out.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out), omit_background=transparent)
    return out
