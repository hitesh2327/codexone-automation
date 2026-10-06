"""Every error code a verifier can return has a troubleshooting entry in the web app's docs, and the docs
have no entry for a code that doesn't exist (so the "How to fix" link on a failed check always lands)."""
from __future__ import annotations

import re
from pathlib import Path

from src.verify.base import CODES, docs_link

GUIDES = Path(__file__).resolve().parent.parent / "web" / "src" / "lib" / "config-guides.ts"


def _troubleshooting_keys() -> set[str]:
    text = GUIDES.read_text(encoding="utf-8")
    start = text.index("export const TROUBLESHOOTING")
    end = text.index("export const GLOSSARY")
    return set(re.findall(r'^\s*"([a-z]+\.[a-z_]+)":\s*\{', text[start:end], re.M))


def test_every_code_has_a_troubleshooting_entry():
    keys = _troubleshooting_keys()
    missing = sorted(set(CODES) - keys)
    assert not missing, f"add a TROUBLESHOOTING entry in config-guides.ts for: {missing}"


def test_no_orphan_troubleshooting_entries():
    orphans = sorted(_troubleshooting_keys() - set(CODES))
    assert not orphans, f"TROUBLESHOOTING has entries for codes no verifier returns: {orphans}"


def test_docs_links_point_at_the_entry_anchor():
    assert docs_link("gemini.key_rejected", "gemini") == "/config/guide/errors#gemini-key_rejected"
    assert docs_link(None, "telegram") == "/config/guide/telegram"
