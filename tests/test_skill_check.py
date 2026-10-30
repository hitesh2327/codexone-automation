"""skills/tech-reel-script-writer/scripts/check.py: the bundled examples and the evaluation scripts pass,
each limit is enforced, and the Markdown, encodings and consoles buyers actually use don't break it.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "tech-reel-script-writer"
CHECK = SKILL / "scripts" / "check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reel_scripts"
SLOW_TTS = ("--max-words", "60", "--wps", "2.3")   # how the Hinglish script is meant to be checked

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("skill_check", CHECK)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

EXAMPLES = (SKILL / "examples.md").read_text(encoding="utf-8")


def binary_search() -> str:
    """The first example on its own."""
    return "## Binary Search" + EXAMPLES.split("\n---\n")[1].split("## Binary Search", 1)[1]


def run(text: str, tmp_path, *args) -> tuple[int, str]:
    f = tmp_path / "script.md"
    f.write_text(text, encoding="utf-8")
    return run_file(f, *args)


def run_file(path, *args) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = check.main([str(path), *args])
    return code, out.getvalue()


def edited(*pairs) -> str:
    """The binary-search example with (old, new) replacements; each old must be present."""
    text = binary_search()
    for old, new in pairs:
        assert old in text, old
        text = text.replace(old, new, 1)
    return text


def test_bundled_examples_pass(tmp_path):
    code, out = run(EXAMPLES, tmp_path)
    assert code == 0, out
    assert out.count("PASS:") == 2 and "FAIL" not in out and "WARN" not in out


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
    ("Platform: instagram", "Platform: facebook", "unknown platform"),
])
def test_each_limit_fails(tmp_path, old, new, expect):
    code, out = run(edited((old, new)), tmp_path)
    assert code == 1 and expect in out, out


def test_total_word_cap_and_override(tmp_path):
    assert run(binary_search(), tmp_path)[0] == 0                       # 70 words <= 75
    code, out = run(binary_search(), tmp_path, "--max-words", "60")     # slower TTS
    assert code == 1 and "max 60" in out


def test_speaking_rate_changes_the_estimate(tmp_path):
    assert "70 words, ~26 s" in run(binary_search(), tmp_path)[1]                 # 2.7 words per second
    assert "70 words, ~30 s" in run(binary_search(), tmp_path, "--wps", "2.3")[1]  # Hindi TTS


def test_youtube_needs_a_title_and_few_hashtags(tmp_path):
    code, out = run(binary_search(), tmp_path, "--platform", "youtube")
    assert code == 1 and "Title:" in out and "hashtags for youtube" in out


def test_absolute_words_are_flagged_with_where(tmp_path):
    code, out = run(edited(("2. A linear scan checks", "2. A linear scan always checks")), tmp_path)
    assert code == 0 and "absolute word 'always' (beat 2)" in out    # a warning, not a failure


def test_technical_terms_are_not_absolutes(tmp_path):
    code, out = run(edited(("in turn: six comparisons here.", "in turn, zero-downtime or not: six comparisons.")),
                    tmp_path)
    assert code == 0 and "absolute" not in out, out


def test_no_script_found(tmp_path):
    code, out = run("just some notes", tmp_path)
    assert code == 1 and "no '## <Title>' script" in out


def test_draft_that_is_not_in_the_format_is_rejected():
    code, out = run_file(FIXTURES / "docker_draft.txt")
    assert code == 1 and "no '## <Title>' script" in out


# --- pipes in table cells (shell commands) ----------------------------------------------------------

def test_escaped_pipe_is_one_cell_and_is_measured(tmp_path):
    long_cmd = r"`ps aux \| grep python \| awk '{print $2}'`"     # 39 characters once unescaped
    code, out = run(edited(("`arr.index(25)  # O(n) scan`", long_cmd)), tmp_path)
    assert code == 1 and "beat 2 code is 39 chars" in out, out
    code, out = run(edited(("`arr.index(25)  # O(n) scan`", r"`ps aux \| grep node`")), tmp_path)
    assert code == 0 and "WARN" not in out, out


def test_unescaped_pipe_in_backticks_warns(tmp_path):
    code, out = run(edited(("`arr.index(25)  # O(n) scan`", "`ps aux | grep node`")), tmp_path)
    assert code == 0 and "isn't escaped" in out, out


def test_pipe_outside_backticks_breaks_the_row(tmp_path):
    code, out = run(edited(("`arr.index(25)  # O(n) scan`", "ps aux | grep node")), tmp_path)
    assert code == 1 and "row 2 has 6 columns" in out, out


# --- Markdown that agents and people actually write --------------------------------------------------

def test_markdown_variants_parse(tmp_path):
    text = edited(("### Voice-over", "### Voice over"),                       # no hyphen
                  ("```python\nfrom bisect", "~~~python\n## not a heading\nfrom bisect"),   # ~~~ fence, ## inside
                  ("arr[i] == x\n```", "arr[i] == x\n~~~"))
    voice, rest = text.split("### Shot list")
    text = re.sub(r"^(\d)\. ", r"\1) ", voice, flags=re.M) + "### Shot list" + rest   # 1) numbering
    code, out = run(text, tmp_path)
    assert code == 0 and "7 beats, 70 words" in out, out


def test_unclosed_code_block_is_reported(tmp_path):
    code, out = run(edited(("arr[i] == x\n```", "arr[i] == x\n")), tmp_path)
    assert code == 1 and "never closed" in out, out


def test_wrapped_beat_lines_are_counted(tmp_path):
    for wrapped in ("2. A linear scan checks each number\n   in turn: six comparisons here.",
                    "2. A linear scan checks each number\nin turn: six comparisons here."):
        code, out = run(edited(("2. A linear scan checks each number in turn: six comparisons here.", wrapped)),
                        tmp_path)
        assert code == 0 and "7 beats, 70 words" in out, out


def test_crlf_bom_and_utf16_files(tmp_path):
    for name, data in (("crlf-bom.md", ("﻿" + binary_search().replace("\n", "\r\n")).encode("utf-8")),
                       ("utf16.md", binary_search().encode("utf-16"))):     # Windows PowerShell 5.1's default
        f = tmp_path / name
        f.write_bytes(data)
        code, out = run_file(f)
        assert code == 0 and "PASS: Binary Search" in out, (name, out)


def test_indented_snippet_fence(tmp_path):
    base = "found = i < len(arr) and arr[i] == x"
    line = base + "  # " + "z" * (60 - len(base) - 4)          # exactly 60 characters
    snippet = "  ```python\n  from bisect import bisect_left\n  " + line + "\n  ```"
    text = edited(("```python\nfrom bisect import bisect_left\ni = bisect_left(arr, x)\n"
                   "found = i < len(arr) and arr[i] == x\n```", snippet))
    code, out = run(text, tmp_path)
    assert code == 0, out


def test_hashtag_rules(tmp_path):
    code, out = run(edited(("Drop it in the comments.",
                            "Drop it in the comments. #1 tip: C# folks too, see https://x.com/#faq &#35;")), tmp_path)
    assert code == 0, out                                                  # still 5 hashtags
    code, out = run(edited(("#python", "#python #100DaysOfCode")), tmp_path)
    assert code == 1 and "6 hashtags" in out, out


# --- code on screen: placeholders vs real syntax -----------------------------------------------------

@pytest.mark.parametrize("code_cell,ok", [
    ("`[...arr, 25]`", True),             # JS spread
    ("`git log main...dev`", True),       # git symmetric difference
    ("`find(...)`", False),
    ("`arr.index(…)`", False),
])
def test_placeholder_vs_real_syntax(tmp_path, code_cell, ok):
    code, out = run(edited(("`arr.index(25)  # O(n) scan`", code_cell)), tmp_path)
    assert (code == 0) == ok and (("placeholder" in out) != ok), out


# --- cheat-sheet comparison table --------------------------------------------------------------------

def test_comparison_table_is_checked(tmp_path):
    table = ("| Approach | Time | Space | Needs |\n|---|---|---|---|\n| Linear scan | O(n) | O(1) | Nothing |\n"
             "| Hash set | O(1) avg | O(n) | Extra memory |\n| Binary search | O(log n) | O(1) | Sorted input |\n")
    code, out = run(edited((table, "")), tmp_path)
    assert code == 1 and "no comparison table" in out, out
    code, out = run(edited(("| Linear scan | O(n) | O(1) | Nothing |", "| Linear scan | O(n) | O(1) | Nothing | x |")),
                    tmp_path)
    assert code == 1 and "has 5 columns" in out, out
    code, out = run(edited(("| Linear scan | O(n) | O(1) | Nothing |",
                            "| Linear scan | O(n) | O(1) | Nothing |\n| A | B | C | D |\n| E | F | G | H |")), tmp_path)
    assert code == 1 and "5 rows (need 2-4)" in out, out


# --- hooks ---------------------------------------------------------------------------------------------

def test_recommended_hook_is_marked_and_used(tmp_path):
    code, out = run(edited((" (recommended)", "")), tmp_path)
    assert code == 0 and "no hook is marked" in out, out
    code, out = run(edited(("1. Binary search finds 25 in three checks, not six. Here's how.",
                            "1. Binary search: the trick your phone book used.")), tmp_path)
    assert code == 0 and "beat 1 doesn't use the recommended hook (hook 1)" in out, out
    code, out = run(edited(("1. Binary search finds 25 in three checks, not six. (recommended)",
                            "1. **Recommended:** Binary search finds 25 in three checks, not six.")), tmp_path)
    assert code == 0 and "WARN" not in out, out                           # marker before the hook
    code, out = run(edited(("2. Still scanning sorted arrays one number at a time?",
                            "2. Recommended move: halve the range")), tmp_path)
    assert code == 0 and "WARN" not in out, out                           # a 5-word hook isn't cut to 4


# --- non-English text --------------------------------------------------------------------------------

def test_visible_length_ignores_combining_marks(tmp_path):
    assert check.visible_len("नमस्ते") == 4 and len("नमस्ते") == 6        # virama and vowel sign take no space
    caption = "दोनों सिरों से *स्वैप* करो, फिर बीच की ओर बढ़ो"             # 44 code points, 38 on screen
    assert len(caption.replace("*", "")) > 40 >= check.visible_len(caption)
    code, out = run(edited(("Find *25* in a sorted array", caption)), tmp_path)
    assert code == 0 and "caption is" not in out, out


@pytest.mark.parametrize("via_stdin", [False, True])
def test_windows_cp1252_console_does_not_crash(tmp_path, via_stdin):
    text = (FIXTURES / "two_pointers_hinglish.md").read_text(encoding="utf-8")
    text = text.replace("## Two Pointers: Reverse a String", "## दो pointers: string reverse")   # non-ASCII output
    f = tmp_path / "hinglish.md"
    f.write_text(text, encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    cmd = [sys.executable, str(CHECK), "-" if via_stdin else str(f), *SLOW_TTS]
    p = subprocess.run(cmd, input=f.read_bytes() if via_stdin else None, capture_output=True, env=env, timeout=60)
    assert p.returncode == 0 and b"Traceback" not in p.stderr, p.stderr.decode("utf-8", "replace")
    assert "PASS: दो pointers: string reverse" in p.stdout.decode("utf-8")


# --- command line ------------------------------------------------------------------------------------

def test_missing_file_exits_2(tmp_path):
    code, out = run_file(tmp_path / "nope.md")
    assert code == 2 and "can't read" in out


def test_bad_arguments_exit_2(tmp_path):
    f = tmp_path / "script.md"
    f.write_text(binary_search(), encoding="utf-8")
    with pytest.raises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
        check.main([str(f), "--wps", "0"])
    assert e.value.code == 2


def test_batch_file_with_notes(tmp_path):
    text = (FIXTURES / "batch_week.md").read_text(encoding="utf-8") + "\n## Notes\n- record on Monday\n"
    code, out = run(text, tmp_path)
    assert code == 0 and out.count("PASS:") == 2 and "SKIP: Notes" in out and "2 passed, 0 failed" in out, out
    code, out = run(text + "\n" + edited(("#binarysearch #dsa", "#binarysearch")), tmp_path)
    assert code == 1 and "3 scripts: 2 passed, 1 failed" in out, out


# --- the evaluation scripts (all six categories, three platforms, three formats, three audiences) ------

FIXTURE_FILES = sorted(FIXTURES.glob("*.md"))


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=[p.stem for p in FIXTURE_FILES])
def test_evaluation_scripts_pass(path):
    code, out = run_file(path, *(SLOW_TTS if "hinglish" in path.stem else ()))
    assert code == 0 and "FAIL" not in out, out


def test_evaluation_scripts_cover_every_option():
    heads = "\n".join(p.read_text(encoding="utf-8") for p in FIXTURE_FILES)
    for option in ("DSA", "System Design", "AI / ML", "Dev & tools", "OS", "Interview & careers",
                   "instagram", "youtube", "tiktok", "animated", "screen", "talking",
                   "beginner", "intermediate", "senior"):
        assert re.search(rf"(Category|Platform|Format|Audience): {re.escape(option)}\b", heads), option


def test_fix_mode_example_reports_true_counts():
    draft = (FIXTURES / "docker_draft.txt").read_text(encoding="utf-8")
    fixed = (FIXTURES / "docker_cache_fixed.md").read_text(encoding="utf-8")
    beats = check.numbered(check.parse(fixed)[0]["sections"]["voiceover"])
    total = sum(len(check.words(b)) for b in beats)
    assert f"Cut from {len(check.words(draft))} words" in fixed and f"to {total} (" in fixed
    assert "### Changes" in fixed
