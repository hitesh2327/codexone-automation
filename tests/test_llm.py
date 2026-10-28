"""Gemini wrapper: a stalled request must never hang a run (28 Oct: a Regenerate hung 29 min until GitHub
cancelled it). Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import llm  # noqa: E402


class Out(BaseModel):
    ok: bool


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = script, []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(parsed=Out(ok=True), text="")


@pytest.fixture()
def fake(monkeypatch):
    def install(script, models=("m1", "m2", "m3")):
        models_api = FakeModels(list(script))
        monkeypatch.setattr(llm, "_get_client", lambda: SimpleNamespace(models=models_api))
        monkeypatch.setattr(llm, "_models", lambda: list(models))
        monkeypatch.setattr(llm.time, "sleep", lambda s: None)
        return models_api
    return install


def test_a_stalled_request_moves_on_to_the_next_model(fake):
    api = fake([httpx.ReadTimeout("stalled"), "ok"])
    assert llm.generate_json("p", Out).ok
    assert api.calls == ["m1", "m2"]                    # no second try on the model that stalled


def test_a_dropped_connection_moves_on_too(fake):
    api = fake([httpx.ConnectError("reset"), "ok"])
    assert llm.generate_json("p", Out).ok and api.calls == ["m1", "m2"]


def test_the_time_budget_stops_the_model_chain(fake, monkeypatch):
    api = fake([httpx.ReadTimeout("stalled")] * 3)
    clock = iter([0.0, 0.0, 10_000.0, 10_000.0])           # start, before m1, before m2 (past the budget)
    monkeypatch.setattr(llm.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="ran out of time"):
        llm.generate_json("p", Out)
    assert api.calls == ["m1"]


def test_the_client_is_built_with_a_timeout(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, api_key, http_options):
            seen["timeout_ms"] = http_options.timeout
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm.genai, "Client", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("GEMINI_TIMEOUT_S", raising=False)
    llm._get_client()
    assert seen["timeout_ms"] == llm.TIMEOUT_S * 1000
    monkeypatch.setattr(llm, "_client", None)
