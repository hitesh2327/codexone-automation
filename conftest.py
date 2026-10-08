"""Session-wide test safety for BOTH suites (api/tests and tests/), loaded by pytest before any test module.

QA-L-13:
  * one throwaway SQLite database for the whole session, chosen here (no test module redirects it at import);
  * every secret name the code knows is replaced by a SENTINEL before src.config loads the developer's .env
    (load_dotenv never overrides), so no test can ever run with a production credential;
  * outbound network is blocked: any socket to a non-loopback host fails the test that opened it;
  * the temporary directory is removed at the end of the session.
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="codexone-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["MAIL_OUTBOX_DIR"] = str(_TMP / "outbox")

from src.redact import SECRET_ENV_NAMES  # noqa: E402  (stdlib-only module: does not load .env)

for _name in SECRET_ENV_NAMES:
    if _name in ("DATABASE_URL", "DATABASE_URL_POOLED"):
        continue
    if "CLOUDINARY" in _name or "COUDNARY" in _name:  # the SDK parses it on import: keep the shape
        os.environ[_name] = "cloudinary://SENTINEL000:SENTINELsecret@sentinel-cloud"
    else:
        os.environ[_name] = f"SENTINEL-{_name.lower()}-not-a-real-value"
for _name in ("SMTP_HOST", "SMTP_USER", "SMTP_USERNAME", "MAIL_FROM", "IG_USER_ID", "TG_CHAT_ID", "YT_CLIENT_ID",
              "GOOGLE_WEB_CLIENT_ID", "GITHUB_REPOSITORY", "DATABASE_URL_POOLED"):
    os.environ[_name] = ""  # real non-secret settings from .env (e.g. an SMTP host) must not be used either
os.environ["MAIL_DRIVER"] = "console"


def _loopback(host) -> bool:
    if host in (None, "", "localhost", "testserver"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else None
    if isinstance(address, tuple) and not _loopback(host):
        raise RuntimeError(f"test tried to open a network connection to {host!r} (blocked by conftest.py)")
    return _real_connect(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _loopback(host):
        raise RuntimeError(f"test tried to resolve {host!r} (blocked by conftest.py)")
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp():
    yield
    try:
        from src import db
        db.engine().dispose()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(_TMP, ignore_errors=True)
