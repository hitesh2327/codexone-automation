"""The v2 renderer trusts the scene spec: these checks are what stand between a sloppy Gemini
draft and a broken or over-length reel. Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reel_v2.spec import MAX_WORDS, SceneSpec, validate  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "src" / "reel_v2" / "examples" / "blue_green.json"


@pytest.fixture
def spec() -> SceneSpec:
    return SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


def test_example_is_valid(spec):
    assert validate(spec) == []


def test_narration_over_budget_is_rejected(spec):
    spec.beats[1].narration += " and" * MAX_WORDS
    assert any("words" in p and "30 seconds" in p for p in validate(spec))


def test_trigger_must_be_spoken(spec):
    spec.beats[4].trigger = "teleport"
    assert any("trigger" in p for p in validate(spec))


def test_flow_must_follow_an_edge(spec):
    spec.beats[0].flows[0].dst = "g1"  # users -> g1 has no wire
    assert any("not an edge" in p for p in validate(spec))


def test_reverse_flow_on_an_edge_is_fine(spec):
    f = spec.beats[0].flows[0]
    f.src, f.dst = f.dst, f.src
    assert validate(spec) == []


def test_counter_labels_must_stay_the_same(spec):
    spec.beats[3].counters[0].label = "VERSION"
    assert any("counter labels" in p for p in validate(spec))


def test_group_nodes_must_share_a_row(spec):
    spec.nodes[-1].row = 3
    assert any("share one row" in p for p in validate(spec))


def test_hook_needs_motion(spec):
    spec.beats[0].flows = []
    assert any("first frame" in p for p in validate(spec))


def test_unknown_node_in_state_change(spec):
    spec.beats[2].states[0].node = "nope"
    assert any("unknown node" in p for p in validate(spec))


# --------------------------------------------------------------------------- #
# Repairs: the slips that made 28 Oct's "Chunking" post fall back, fixed instead of rejected
# --------------------------------------------------------------------------- #
from src.reel_v2 import spec as specmod  # noqa: E402
from src.reel_v2.spec import CAPTION_MAX, HEADING_MAX, TERM_MAX, Flow, repair  # noqa: E402


def test_repair_fixes_the_chunking_failures(spec):
    spec.nodes[-1].row = 3                                         # group split across rows
    spec.beats[1].trigger = "split"                                # not a word of the narration
    spec.beats[2].flows.append(Flow(src="b1", dst="g1", tone="blue"))   # no such wire
    spec.beats[3].flows.append(Flow(src="b1", dst="b1", tone="blue"))   # self-loop (db->db)
    spec.beats[0].heading = "ZERO DOWNTIME BLUE GREEN DEPLOYS"
    spec.beats[0].caption = "Ship version two *without* taking the whole application down for anyone"
    spec.beats[4].term = "kubectl patch service app -p '{\"spec\":{\"selector\":{\"v\":\"green\"}}}'"
    assert validate(spec)                                          # broken before
    fixed = repair(spec)
    assert validate(spec) == [], validate(spec)                    # valid after, no rewrite needed
    assert any("group" in f for f in fixed) and any("trigger" in f for f in fixed)
    b = spec.beats[0]
    assert len(b.heading) <= HEADING_MAX and len(b.caption.replace("*", "")) <= CAPTION_MAX
    assert b.caption.count("*") % 2 == 0 and len(spec.beats[4].term) <= TERM_MAX
    assert spec.beats[1].trigger in spec.beats[1].narration
    assert all(f.src != f.dst for f in spec.beats[3].flows)
    assert ("b1", "g1") in {(e.src, e.dst) for e in spec.edges}    # the arrow kept, its wire added


def test_repair_leaves_a_valid_spec_alone(spec):
    before = spec.model_dump_json()
    assert repair(spec) == [] and spec.model_dump_json() == before


def _fake_llm(monkeypatch, drafts, review_ok=True):
    calls = {"write": 0, "review": 0}

    def fake(prompt, schema, **k):
        if schema is SceneSpec:
            calls["write"] += 1
            return drafts.pop(0)
        calls["review"] += 1
        return specmod.Review(ok=review_ok, issues=[] if review_ok else ["counter says 100%"])
    monkeypatch.setattr(specmod, "generate_json", fake)
    monkeypatch.setattr(specmod, "load_brand", lambda: {"handle": "@t", "hashtags": ["#x"]})
    return calls


def _too_wordy(s: SceneSpec) -> SceneSpec:
    s.beats[1].narration += " and" * MAX_WORDS                     # not repairable: needs a rewrite
    return s


def test_generate_rewrites_what_repair_cannot_fix(monkeypatch, spec):
    good = SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    calls = _fake_llm(monkeypatch, [_too_wordy(spec.model_copy(deep=True)), good])
    assert specmod.generate("Blue-Green", "SystemDesign") is good
    assert calls == {"write": 2, "review": 1}


def test_generate_allows_two_rewrites_then_fails(monkeypatch, spec):
    drafts = [_too_wordy(SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))) for _ in range(3)]
    calls = _fake_llm(monkeypatch, drafts)
    with pytest.raises(ValueError, match="30 seconds"):
        specmod.generate("Blue-Green", "SystemDesign")
    assert calls["write"] == 3


def test_last_attempt_ships_without_another_review(monkeypatch, spec):
    good = lambda: SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))  # noqa: E731
    calls = _fake_llm(monkeypatch, [good(), good(), good()], review_ok=False)   # reviewer never satisfied
    specmod.generate("Blue-Green", "SystemDesign")
    assert calls == {"write": 3, "review": 2}
