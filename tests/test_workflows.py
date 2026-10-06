"""Workflow guards: user-typed dispatch inputs never reach a shell inline, Generate has its own concurrency
group, nothing in the generate workflow publishes, and the migration history has one head.

Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["on"] = doc.pop(True, doc.get("on"))  # YAML 1.1 reads the key `on` as True
    return doc


def steps(doc: dict):
    for job in doc["jobs"].values():
        yield from job["steps"]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_free_text_input_is_inlined_into_a_shell_script(path):
    doc = load(path)
    types = {name: spec.get("type", "string")
             for name, spec in ((doc["on"].get("workflow_dispatch") or {}).get("inputs") or {}).items()}
    for step in steps(doc):
        for expr in EXPRESSION.findall(step.get("run", "")):
            for name in re.findall(r"inputs\.(\w+)", expr) + re.findall(r"github\.event\.inputs\.(\w+)", expr):
                assert types.get(name) == "boolean", (
                    f"{path.name}: step {step.get('name')!r} inlines inputs.{name} into run: (pass it through env:)")
        assert "github.head_ref" not in step.get("run", "")


def test_generate_workflow_has_no_input_expression_in_any_run_block():
    """Stricter for the workflow the dashboard dispatches: not even boolean inputs are inlined into run:."""
    doc = load(ROOT / ".github" / "workflows" / "daily-generate.yml")
    for step in steps(doc):
        for expr in EXPRESSION.findall(step.get("run", "")):
            assert "inputs." not in expr and "github.event" not in expr, (step.get("name"), expr)


def test_generate_inputs_are_read_through_env():
    doc = load(ROOT / ".github" / "workflows" / "daily-generate.yml")
    step = next(s for s in steps(doc) if s.get("name", "").startswith("Generate post"))
    assert {"IN_SLOT", "IN_CATEGORY", "IN_TOPIC", "IN_SOURCE_URL", "IN_REQUEST_ID"} <= set(step["env"])
    for var in ("IN_TOPIC", "IN_SOURCE_URL", "IN_CATEGORY"):
        assert f'"${var}"' in step["run"] and "${{" not in step["run"]  # always quoted, never interpolated


def test_generate_workflow_contract_with_the_dashboard():
    doc = load(ROOT / ".github" / "workflows" / "daily-generate.yml")
    inputs = doc["on"]["workflow_dispatch"]["inputs"]
    assert {"slot", "category", "topic", "source_url", "request_id", "dry_run", "force", "allow_duplicate"} <= set(inputs)
    assert len(inputs) <= 10                                           # GitHub's limit
    assert "inputs.request_id" in doc["run-name"] and "Generate " in doc["run-name"]  # how the API finds its run
    assert doc["concurrency"]["group"] not in ("queue-state", "")      # a poll dispatch must not cancel a queued Generate
    assert doc["concurrency"]["cancel-in-progress"] is False
    assert doc["on"]["schedule"]                                       # the scheduled runs are intact
    assert {c["cron"] for c in doc["on"]["schedule"]} == {"30 2 * * *", "30 12 * * *"}
    assert any("job-end" in s.get("run", "") and "failure()" in s.get("if", "") for s in steps(doc))


def test_generate_workflow_never_publishes():
    text = (ROOT / ".github" / "workflows" / "daily-generate.yml").read_text(encoding="utf-8")
    for forbidden in ("main.py poll", "main.py publish", "publish_item", "publish_due", "--platform"):
        assert forbidden not in text
    doc = load(ROOT / ".github" / "workflows" / "daily-generate.yml")
    assert "YT_CLIENT_SECRET" not in doc["env"] and "YT_REFRESH_TOKEN" not in doc["env"]


def test_other_workflows_keep_the_shared_queue_group():
    for name in ("poll-approvals.yml", "refresh-token.yml"):
        assert load(ROOT / ".github" / "workflows" / name)["concurrency"]["group"] == "queue-state"


def test_migrations_have_a_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(ROOT / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "api" / "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, heads
