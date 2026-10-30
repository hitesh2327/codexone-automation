"""skills/tech-reel-script-writer/scripts/check.py: the bundled examples pass, and each limit is enforced.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "tech-reel-script-writer"
spec = importlib.util.spec_from_file_location("skill_check", SKILL / "scripts" / "check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

EXAMPLES = (SKILL / "examples.md").read_text(encoding="utf-8")


def binary_search() -> str:
    """The first example on its own."""
    return EXAMPLES.split("\n---\n")[1]


def run(text: str, tmp_path, *args) -> tuple[int, str]:
    f = tmp_path / "script.md"
    f.write_text(text, encoding="utf-8")
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = check.main([str(f), *args])
    return code, out.getvalue()


def test_bundled_examples_pass(tmp_path):
    code, out = run(EXAMPLES, tmp_path)
    assert code == 0, out
    assert out.count("PASS:") == 2 and "FAIL" not in out


@pytest.mark.parametrize("old,new,expect", [
    ("7. Halve the range each step", "7. " + "word " * 20 + "Halve the range each step", "beat 7"),           # beat > 16 words
    ("| 1 | BINARY SEARCH |", "| 1 | BINARY SEARCH IN SORTED ARRAYS |", "heading is"),                       # heading > 20
    ("Find *25* in a sorted array", "Find *25* in a sorted array of numbers, fast!", "caption is"),          # caption > 40
    ("Find *25* in a sorted array", "Find *25 in a sorted array", "unpaired"),
    ("`lo = mid + 1` |\n| 5", "`for x in arr: ...` |\n| 5", "placeholder"),                               # fake code
    ("#binarysearch #dsa", "#binarysearch", "hashtags for instagram"),                                         # 4 tags
    ("### Unverified", "### Not checked", "missing section"),
    ("3. Why binary search needs only twenty checks for a million items\n", "", "hook options"),              # 2 hooks
    ("found = i < len(arr) and arr[i] == x", "found = i < len(arr) and arr[i] == x\n" * 5, "snippet has"),  # 8 lines
])
def test_each_limit_fails(tmp_path, old, new, expect):
    text = binary_search()
    assert old in text, old
    code, out = run("## Binary Search" + text.split("## Binary Search", 1)[1].replace(old, new, 1), tmp_path)
    assert code == 1 and expect in out, out


def test_total_word_cap_and_override(tmp_path):
    text = "## Binary Search" + binary_search().split("## Binary Search", 1)[1]
    assert run(text, tmp_path)[0] == 0                       # 70 words <= 75
    code, out = run(text, tmp_path, "--max-words", "60")     # slower TTS
    assert code == 1 and "max 60" in out


def test_youtube_needs_a_title_and_few_hashtags(tmp_path):
    text = "## Binary Search" + binary_search().split("## Binary Search", 1)[1]
    code, out = run(text, tmp_path, "--platform", "youtube")
    assert code == 1 and "Title:" in out and "hashtags for youtube" in out


def test_absolute_words_are_flagged(tmp_path):
    text = "## Binary Search" + binary_search().split("## Binary Search", 1)[1]
    text = text.replace("2. A linear scan checks each number", "2. A linear scan always checks each number")
    code, out = run(text, tmp_path)
    assert code == 0 and "absolute word 'always'" in out    # a warning, not a failure


def test_no_script_found(tmp_path):
    code, out = run("just some notes", tmp_path)
    assert code == 1 and "no '## <Title>' script" in out
