"""QA-M-01: the deploy tooling provisions (or loudly flags) every runtime name the dashboard needs.
No AWS: put_secrets runs in dry-run mode against a fake .env."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDED = ("CONFIG_MASTER_KEY", "GITHUB_REPOSITORY", "GITHUB_DISPATCH_TOKEN")


def _put_secrets():
    spec = importlib.util.spec_from_file_location("put_secrets", ROOT / "infra" / "put_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_env(**extra):
    base = {k: "SENTINEL" for k in ("DATABASE_URL", "JWT_SECRET", "SESSION_SECRET", "ADMIN_USERNAME", "ADMIN_PASSWORD")}
    return {**base, **extra}


def test_put_secrets_writes_the_dashboard_runtime_names(monkeypatch, capsys):
    mod = _put_secrets()
    assert set(NEEDED) <= set(mod.OPTIONAL)
    monkeypatch.setattr(mod, "dotenv_values", lambda _p: _fake_env(**{n: "SENTINEL_x" for n in NEEDED}))
    monkeypatch.setattr(sys, "argv", ["put_secrets.py"])                 # dry run
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert all(f"   {n}" in out for n in NEEDED) and "WARNING" not in out and "SENTINEL" not in out


def test_put_secrets_warns_about_missing_runtime_names(monkeypatch, capsys):
    mod = _put_secrets()
    monkeypatch.setattr(mod, "dotenv_values", lambda _p: _fake_env())
    monkeypatch.setattr(sys, "argv", ["put_secrets.py"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert all(f"WARNING: {n} is not in .env" in out for n in NEEDED)


def test_deploy_script_checks_the_runtime_names():
    text = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")
    assert "for NAME in CONFIG_MASTER_KEY GITHUB_REPOSITORY GITHUB_DISPATCH_TOKEN" in text
    assert "--with-decryption" not in text.split("for NAME in")[1].split("done")[0]   # names only
    readme = (ROOT / "infra" / "README.md").read_text(encoding="utf-8")
    assert all(n in readme for n in NEEDED)


def test_check_secrets_says_when_an_identity_comparison_is_skipped(monkeypatch, capsys):
    """QA-L-01: an unset EXPECTED_* repository variable used to skip the comparison silently."""
    spec = importlib.util.spec_from_file_location("check_secrets", ROOT / "scripts" / "check_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("YT_CLIENT_ID", "SENTINEL.apps.googleusercontent.com")
    monkeypatch.delenv("EXPECTED_FP_YT_CLIENT_ID", raising=False)
    mod.yt_value("YT_CLIENT_ID")
    out = capsys.readouterr().out
    assert "SKIPPED: EXPECTED_FP_YT_CLIENT_ID is not set" in out and "SENTINEL" not in out
    import hashlib
    monkeypatch.setenv("EXPECTED_FP_YT_CLIENT_ID", hashlib.sha256(b"SENTINEL.apps.googleusercontent.com").hexdigest()[:8])
    mod.yt_value("YT_CLIENT_ID")
    out = capsys.readouterr().out
    assert "SKIPPED" not in out and "matches local" in out
