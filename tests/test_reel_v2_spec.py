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
