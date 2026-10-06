"""Config section: encrypted store, resolver precedence, verify-then-save, readiness, and the security
properties of spec 3.6 (S1 no secret in any response, S2 a DB dump reveals nothing, S3 nothing secret in
the activity log, S4 admin + CSRF, S5 a failed verify never changes a stored value, S6 409 on concurrent
edits, S7 key rotation). Providers are never called: verifiers are replaced by fakes and a guard fails
any real HTTP request from the verify library.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text

from api.app.routes import config as route
from src import config_store, db
from src import verify as verify_lib
from src.config import get_env
from src.config_schema import FIELDS
from src.db.models import ActivityLog, ConfigCheck, ConfigKey, ConfigMeta, ConfigValue
from src.verify import base
from src.verify.base import Run

SENTINEL = "SENTINEL-secret-value-7f3a9c"
KEY1 = config_store.generate_master_key()
KEY2 = config_store.generate_master_key()
ALL_NAMES = {f.name for f in FIELDS} | {"COUDNARY_API_ENV_VAR", "CLOUDINARY_API_ENV_VAR", "CONFIG_PRECEDENCE"}
INVALID = {"gemini": "gemini.key_rejected", "telegram": "telegram.token_rejected", "cloudinary": "cloudinary.rejected",
           "github": "github.token_rejected", "database": "database.unreachable"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for n in ALL_NAMES:          # the developer's real .env is loaded into os.environ: keep it out of these tests
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("CONFIG_MASTER_KEY", KEY1)

    class NoNetwork:
        RequestException = Exception

        def request(self, *a, **k):
            raise AssertionError("a test tried to reach a real provider")
    monkeypatch.setattr(base, "requests", NoNetwork())
    with db.session() as s:
        for model in (ConfigCheck, ConfigValue, ConfigKey, ConfigMeta, ActivityLog):
            s.execute(delete(model))
    config_store._dek_cache.clear()
    config_store.invalidate()
    route._recent.clear()
    route._deep_at.clear()
    route.limiter._hits.clear()
    yield
    config_store._dek_cache.clear()
    config_store.invalidate()


class Fake:
    """Programmable stand-in for src.verify.run, recording the values each check received."""

    def __init__(self):
        self.status: dict[str, str] = {}
        self.seen: list[tuple[str, dict, str]] = []

    def __call__(self, integration, values=None, depth="live"):
        if values is None:
            values = verify_lib.effective_values(integration)
        self.seen.append((integration, dict(values), depth))
        run = Run(integration, depth)
        st = self.status.get(integration, "valid")
        if st == "valid":
            run.ok("x", "Works", f"evidence for {integration}")
        elif st == "warning":
            run.warn("x", "Works", "github.token_expiring")
        elif st == "invalid":
            run.fail("x", "Works", INVALID[integration])
        elif st == "unknown":
            run.fail("x", "Works", "verify.crashed")
        return run.finish()


@pytest.fixture()
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(route, "run_verify", f)
    return f


def put(c, integration, values, expected=None, **kw):
    expected = expected if expected is not None else {k: 0 for k in values}
    return c.put(f"/api/config/{integration}", json={"values": values, "expected": expected, **kw})


def version_of(c, integration, name):
    data = c.get("/api/config").json()
    integ = next(i for i in data["integrations"] if i["name"] == integration)
    return next(f for f in integ["fields"] if f["name"] == name)


# --------------------------------------------------------------------------- #
# Access control (S4)
# --------------------------------------------------------------------------- #
def test_requires_sign_in_and_csrf(client, authed, fake):
    client.cookies.clear()
    assert client.get("/api/config").status_code == 401


def test_csrf_required_on_writes(authed, fake):
    authed.headers.pop("X-CSRF-Token")
    assert put(authed, "gemini", {"GEMINI_API_KEY": SENTINEL}).status_code == 403
    assert authed.post("/api/config/gemini/verify", json={}).status_code == 403


# --------------------------------------------------------------------------- #
# Save = verify, then store (S1, S2, S3, S5)
# --------------------------------------------------------------------------- #
def test_save_cleans_verifies_encrypts_and_never_echoes(authed, fake):
    r = put(authed, "gemini", {"GEMINI_API_KEY": f' "GEMINI_API_KEY={SENTINEL}"\n'})
    assert r.status_code == 200, r.text
    assert fake.seen[-1][1]["GEMINI_API_KEY"] == SENTINEL           # verified the cleaned value
    assert r.json()["cleaned"]["GEMINI_API_KEY"]
    field = next(f for f in r.json()["integration"]["fields"] if f["name"] == "GEMINI_API_KEY")
    assert field["is_set"] and field["source"] == "store" and field["value"] is None and len(field["fingerprint"]) == 8
    assert get_env("GEMINI_API_KEY") == SENTINEL                     # the pipeline sees it

    # S1: no endpoint returns the secret or a part of it
    bodies = [r.text] + [authed.get(p).text for p in ("/api/config", "/api/config/schema", "/api/config/readiness",
                                                       "/api/config/gemini/history")]
    bodies.append(authed.post("/api/config/gemini/verify", json={}).text)
    for b in bodies:
        assert SENTINEL not in b and SENTINEL[9:21] not in b
    # S2: the database holds ciphertext only
    with db.engine().connect() as c:
        dump = repr(c.execute(text("select * from config_values")).fetchall()) + \
            repr(c.execute(text("select * from config_keys")).fetchall())
    assert SENTINEL not in dump and SENTINEL.encode().hex() not in dump
    # S3: the audit trail has names, not values
    with db.session() as s:
        rows = list(s.scalars(select(ActivityLog)))
    assert any(e.event == "config.saved" and "GEMINI_API_KEY" in e.message for e in rows)
    assert all(SENTINEL not in (e.message + repr(e.detail)) for e in rows)


def test_failed_verify_never_replaces_a_working_value(authed, fake):
    assert put(authed, "gemini", {"GEMINI_API_KEY": "good-key-123456"}).status_code == 200
    v = version_of(authed, "gemini", "GEMINI_API_KEY")["version"]
    fake.status["gemini"] = "invalid"
    r = put(authed, "gemini", {"GEMINI_API_KEY": "typo-key-999999"}, expected={"GEMINI_API_KEY": v})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "verify_failed"
    assert r.json()["detail"]["result"]["code"] == "gemini.key_rejected"
    assert get_env("GEMINI_API_KEY") == "good-key-123456"
    assert version_of(authed, "gemini", "GEMINI_API_KEY")["version"] == v


def test_unknown_outcome_saves_only_when_asked(authed, fake):
    fake.status["gemini"] = "unknown"
    r = put(authed, "gemini", {"GEMINI_API_KEY": "maybe-key-123456"})
    assert r.status_code == 409 and r.json()["detail"]["can_force"] is True
    assert get_env("GEMINI_API_KEY", required=False) is None
    r = put(authed, "gemini", {"GEMINI_API_KEY": "maybe-key-123456"}, save_unverified=True)
    assert r.status_code == 200
    assert get_env("GEMINI_API_KEY") == "maybe-key-123456"
    assert r.json()["integration"]["state"] == "unknown"


def test_concurrent_edit_gets_409(authed, fake):
    assert put(authed, "gemini", {"GEMINI_API_KEY": "first-key-123456"}).status_code == 200
    r = put(authed, "gemini", {"GEMINI_API_KEY": "second-key-12345"})  # still claims version 0
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conflict"
    assert get_env("GEMINI_API_KEY") == "first-key-123456"


def test_save_rules(authed, fake):
    assert put(authed, "gemini", {"NOT_A_FIELD": "x"}).status_code == 422
    assert put(authed, "gemini", {"TG_BOT_TOKEN": "x"}).status_code == 422          # another integration's field
    assert put(authed, "instagram", {"IG_ACCESS_TOKEN": "x"}).status_code == 400    # not editable yet
    assert put(authed, "gemini", {"GEMINI_API_KEY": ""}).json()["detail"]["code"] == "required_field"
    r = authed.put("/api/config/gemini", json={"values": {"GEMINI_API_KEY": "abc-123456"}})
    assert r.json()["detail"]["code"] == "expected_versions"
    assert put(authed, "gemini", {"GEMINI_API_KEY": "x" * 5000}).status_code == 422


def test_remove_is_versioned_and_audited(authed, fake):
    put(authed, "gemini", {"GEMINI_API_KEY": "good-key-123456"})
    v = version_of(authed, "gemini", "GEMINI_API_KEY")["version"]
    assert authed.delete(f"/api/config/gemini/GEMINI_API_KEY?version={v + 1}").status_code == 409
    assert authed.delete(f"/api/config/gemini/GEMINI_API_KEY?version={v}").status_code == 204
    assert get_env("GEMINI_API_KEY", required=False) is None
    with db.session() as s:
        assert s.scalars(select(ActivityLog).where(ActivityLog.event == "config.removed")).first()


# --------------------------------------------------------------------------- #
# Resolver precedence (env wins during migration; flag flips it)
# --------------------------------------------------------------------------- #
def test_environment_wins_and_conflict_is_flagged(authed, fake, monkeypatch):
    put(authed, "gemini", {"GEMINI_API_KEY": "store-key-123456"})
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-12345678")
    assert get_env("GEMINI_API_KEY") == "env-key-12345678"
    f = version_of(authed, "gemini", "GEMINI_API_KEY")
    assert (f["source"], f["overridden"], f["conflict"]) == ("env", True, True)
    monkeypatch.setenv("CONFIG_PRECEDENCE", "store")
    assert get_env("GEMINI_API_KEY") == "store-key-123456"
    monkeypatch.setenv("CONFIG_PRECEDENCE", "env")
    monkeypatch.setenv("GEMINI_API_KEY", "store-key-123456")      # same value: no conflict
    assert version_of(authed, "gemini", "GEMINI_API_KEY")["conflict"] is False


def test_bootstrap_names_never_come_from_the_store():
    from src.config_schema import BOOTSTRAP, STORE_NAMES
    assert "DATABASE_URL" in BOOTSTRAP and "DATABASE_URL" not in STORE_NAMES
    assert "CONFIG_MASTER_KEY" not in STORE_NAMES


def test_resolver_never_breaks_when_the_store_is_unavailable(monkeypatch):
    def broken():
        raise RuntimeError("database down")
    monkeypatch.setattr(db, "session", broken)
    config_store.invalidate()
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-12345678")
    assert get_env("GEMINI_API_KEY") == "env-key-12345678"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert get_env("GEMINI_API_KEY", required=False) is None


def test_runner_masks_store_secrets(monkeypatch, capsys):
    config_store.save({"GEMINI_API_KEY": "mask-me-12345678"}, actor="t")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    config_store._masked.clear()
    assert get_env("GEMINI_API_KEY") == "mask-me-12345678"
    assert "::add-mask::mask-me-12345678" in capsys.readouterr().out
    from src.redact import redact
    assert "mask-me-12345678" not in redact("leak mask-me-12345678")


# --------------------------------------------------------------------------- #
# Crypto (S2, S7) and the master key
# --------------------------------------------------------------------------- #
def test_wrong_or_missing_master_key(monkeypatch):
    config_store.save({"GEMINI_API_KEY": "k-1234567890"}, actor="t")
    monkeypatch.setenv("CONFIG_MASTER_KEY", KEY2)
    config_store._dek_cache.clear()
    config_store.invalidate()
    assert get_env("GEMINI_API_KEY", required=False) is None
    with pytest.raises(config_store.StoreError) as e:
        config_store.check_canary()
    assert e.value.code == "database.key_mismatch"
    monkeypatch.setenv("CONFIG_MASTER_KEY", "too-short")
    with pytest.raises(config_store.StoreError) as e:
        config_store.master_key()
    assert e.value.code == "database.master_key_invalid"
    monkeypatch.delenv("CONFIG_MASTER_KEY")
    with pytest.raises(config_store.StoreError) as e:
        config_store.save({"GEMINI_API_KEY": "x-1234567890"}, actor="t")
    assert e.value.code == "database.master_key_missing"


def test_rotation_rewraps_and_old_key_stops_working(monkeypatch):
    config_store.save({"GEMINI_API_KEY": "rotate-me-123456", "GITHUB_DISPATCH_TOKEN": "tok-1234567890"}, actor="t")
    config_store.rotate_master_key(KEY1, KEY2)
    monkeypatch.setenv("CONFIG_MASTER_KEY", KEY2)
    config_store.invalidate()
    assert get_env("GEMINI_API_KEY") == "rotate-me-123456"
    assert config_store.check_canary() == "ok"
    monkeypatch.setenv("CONFIG_MASTER_KEY", KEY1)
    config_store._dek_cache.clear()
    config_store.invalidate()
    assert get_env("GEMINI_API_KEY", required=False) is None


def test_ciphertext_cannot_be_moved_between_settings():
    config_store.save({"GEMINI_API_KEY": "aaaa-1234567890", "GITHUB_DISPATCH_TOKEN": "bbbb-1234567890"}, actor="t")
    with db.session() as s:
        a, b = s.get(ConfigValue, "GEMINI_API_KEY"), s.get(ConfigValue, "GITHUB_DISPATCH_TOKEN")
        b.ciphertext, b.nonce = a.ciphertext, a.nonce          # attacker with DB write access swaps rows
    config_store.invalidate()
    assert get_env("GITHUB_DISPATCH_TOKEN", required=False) is None  # AAD binds ciphertext to its name
    assert get_env("GEMINI_API_KEY") == "aaaa-1234567890"


def test_config_version_bumps_only_on_required_changes():
    v0 = config_store.config_version()
    config_store.save({"GEMINI_MODEL": "gemini-x"}, actor="t", required={"GEMINI_API_KEY"})
    assert config_store.config_version() == v0
    config_store.save({"GEMINI_API_KEY": "k1-1234567890"}, actor="t", required={"GEMINI_API_KEY"})
    v1 = config_store.config_version()
    assert v1 == v0 + 1
    config_store.save({"GEMINI_API_KEY": "k1-1234567890"}, actor="t", required={"GEMINI_API_KEY"})  # same value
    assert config_store.config_version() == v1


# --------------------------------------------------------------------------- #
# Verify endpoint
# --------------------------------------------------------------------------- #
def test_verify_candidate_merges_with_current_values(authed, fake):
    put(authed, "telegram", {"TG_BOT_TOKEN": "111:SENTINELtokentokentokentoken", "TG_CHAT_ID": "42"})
    r = authed.post("/api/config/telegram/verify", json={"values": {"TG_CHAT_ID": " -100 "}})
    assert r.status_code == 200
    _, values, _ = fake.seen[-1]
    assert values == {"TG_BOT_TOKEN": "111:SENTINELtokentokentokentoken", "TG_CHAT_ID": "-100"}
    assert "SENTINELtoken" not in r.text


def test_deep_check_needs_consent_and_has_a_cooldown(authed, fake):
    put(authed, "gemini", {"GEMINI_API_KEY": "good-key-123456"})
    assert authed.post("/api/config/gemini/verify", json={"depth": "deep"}).json()["detail"]["code"] == "consent_required"
    assert authed.post("/api/config/gemini/verify", json={"depth": "deep", "consent": True}).status_code == 200
    r = authed.post("/api/config/gemini/verify", json={"depth": "deep", "consent": True})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_same_values_within_10s_reuse_the_result(authed, fake):
    put(authed, "gemini", {"GEMINI_API_KEY": "good-key-123456"})
    n = len(fake.seen)
    a = authed.post("/api/config/gemini/verify", json={}).json()["result"]
    b = authed.post("/api/config/gemini/verify", json={}).json()["result"]
    assert len(fake.seen) == n and b.get("reused") is True and a.get("reused") is True  # the save's check was reused


def test_per_user_rate_limit(authed, fake, monkeypatch):
    monkeypatch.setattr(route, "RATE_LIMIT", 2)
    put(authed, "gemini", {"GEMINI_API_KEY": "good-key-123456"})
    authed.post("/api/config/gemini/verify", json={"values": {"GEMINI_API_KEY": "other-1234567"}})
    r = authed.post("/api/config/gemini/verify", json={"values": {"GEMINI_API_KEY": "other-7654321"}})
    assert r.status_code == 429


def test_history_lists_results_without_values(authed, fake):
    put(authed, "gemini", {"GEMINI_API_KEY": SENTINEL})
    h = authed.get("/api/config/gemini/history").json()["checks"]
    assert h and h[0]["status"] == "valid" and SENTINEL not in repr(h)


# --------------------------------------------------------------------------- #
# Readiness (G1-G8) and staleness
# --------------------------------------------------------------------------- #
def make_ready(c):
    assert put(c, "gemini", {"GEMINI_API_KEY": "good-key-123456"}).status_code == 200
    assert put(c, "telegram", {"TG_BOT_TOKEN": "111:tokentokentokentokentok", "TG_CHAT_ID": "42"}).status_code == 200
    assert put(c, "cloudinary", {"CLOUDINARY_URL": "cloudinary://1:secretsecret@demo"}).status_code == 200
    assert put(c, "github", {"GITHUB_REPOSITORY": "acme/automation", "GITHUB_DISPATCH_TOKEN": "github_pat_123456789"}).status_code == 200


def test_readiness_needs_every_tier1_check_for_the_current_values(authed, fake, monkeypatch):
    r = authed.get("/api/config/readiness").json()
    assert r["ready_to_generate"] is False
    assert {m["id"] for m in r["missing"]} >= {"G2", "G3", "G4", "G5"}
    make_ready(authed)
    r = authed.get("/api/config/readiness").json()
    assert r["ready_to_generate"] is True, r["missing"]
    g6 = next(c for c in r["conditions"] if c["id"] == "G6")
    assert g6["ok"] is None and g6["blocking"] is False      # system test not built: reported honestly

    # a value changing outside the dashboard makes the old result stale
    monkeypatch.setenv("GEMINI_API_KEY", "changed-in-env-123")
    r = authed.get("/api/config/readiness").json()
    assert r["ready_to_generate"] is False
    assert {m["id"] for m in r["missing"]} == {"G2", "G7"}
    integ = next(i for i in authed.get("/api/config").json()["integrations"] if i["name"] == "gemini")
    assert integ["state"] == "stale"


def test_readiness_blocks_without_repository_or_master_key(authed, fake, monkeypatch):
    make_ready(authed)
    with db.session() as s:
        s.delete(s.get(ConfigValue, "GITHUB_REPOSITORY"))
    config_store.invalidate()
    ids = {m["id"] for m in authed.get("/api/config/readiness").json()["missing"]}
    assert "G8" in ids
    monkeypatch.delenv("CONFIG_MASTER_KEY")
    config_store._dek_cache.clear()
    config_store.invalidate()
    r = authed.get("/api/config/readiness").json()
    g1 = next(c for c in r["conditions"] if c["id"] == "G1")
    assert g1["ok"] is False and g1["code"] == "database.master_key_missing"


def test_failed_check_blocks_readiness(authed, fake):
    make_ready(authed)
    fake.status["telegram"] = "invalid"
    authed.post("/api/config/telegram/verify", json={"values": {"TG_CHAT_ID": "43"}})   # different values: no reuse
    put(authed, "telegram", {"TG_CHAT_ID": "43"}, expected={"TG_CHAT_ID": 1})          # rejected, nothing stored
    r = authed.get("/api/config/readiness").json()
    assert r["ready_to_generate"] is True   # the stored (working) values are still verified
    with db.session() as s:
        s.get(ConfigValue, "TG_CHAT_ID").value_plain = "44"                             # changed behind our back
    config_store.invalidate()
    assert authed.get("/api/config/readiness").json()["ready_to_generate"] is False


def test_database_verifier_on_the_test_db():
    r = verify_lib.run("database")
    assert r.status == "valid", r.to_dict()
    assert {c.name for c in r.checks} >= {"connect", "schema", "write", "master_key"}


# --------------------------------------------------------------------------- #
# Telegram helpers
# --------------------------------------------------------------------------- #
def test_detect_chat_and_webhook_removal(authed, fake, monkeypatch):
    from src.verify import telegram as tg
    seen = []
    monkeypatch.setattr(tg, "detect_chats", lambda token: (seen.append(token) or [{"id": "42", "type": "private", "title": "Ana"}], None))
    r = authed.post("/api/config/telegram/detect", json={"token": ' "111:tokentokentokentokentok" '})
    assert r.json()["chats"][0]["id"] == "42" and seen == ["111:tokentokentokentokentok"]
    assert "tokentoken" not in r.text
    monkeypatch.setattr(tg, "detect_chats", lambda token: ([], "telegram.no_chat_found"))
    r = authed.post("/api/config/telegram/detect", json={"token": "111:tokentokentokentokentok"}).json()
    assert r["code"] == "telegram.no_chat_found" and r["docs"].endswith("#telegram-no_chat_found")

    calls = []
    monkeypatch.setattr(tg, "delete_webhook", lambda token: calls.append(token))
    assert authed.post("/api/config/telegram/delete-webhook", json={"token": "111:tokentokentokentokentok"}).status_code == 400
    assert authed.post("/api/config/telegram/delete-webhook",
                       json={"token": "111:tokentokentokentokentok", "confirm": True}).json() == {"ok": True}
    assert calls == ["111:tokentokentokentokentok"]


def test_overview_lists_every_integration_honestly(authed, fake):
    data = authed.get("/api/config").json()
    names = [i["name"] for i in data["integrations"]]
    assert names[:5] == ["database", "gemini", "telegram", "cloudinary", "github"]
    ig = next(i for i in data["integrations"] if i["name"] == "instagram")
    assert ig["implemented"] is False and ig["editable"] is False
    assert data["precedence"] == "env" and data["master_key"] in ("ok", "empty")
