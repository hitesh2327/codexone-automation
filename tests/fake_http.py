"""A recording stand-in for `requests` used by the verifier tests: no test ever reaches a real provider.

Responses are built from the providers' documented shapes (see each test). Every request is recorded so
tests can assert what was NOT called (no publish, no dispatch, no getUpdates offset, no secret in a URL).
"""
from __future__ import annotations

import json as _json
import re

import requests


class FakeResponse:
    def __init__(self, status: int = 200, data=None, headers: dict | None = None, text: str | None = None):
        self.status_code = status
        self._data = data
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.text = text if text is not None else (_json.dumps(data) if data is not None else "")

    def json(self):
        if self._data is None:
            raise ValueError("no JSON")
        return self._data


class _Headers(dict):
    def get(self, k, default=None):
        return super().get(k.lower(), default)


class FakeHTTP:
    """`routes`: list of (method, url-regex, response | callable(call) -> response). First match wins."""

    RequestException = requests.RequestException

    def __init__(self, routes=None):
        self.routes = list(routes or [])
        self.calls: list[dict] = []

    def add(self, method: str, pattern: str, response) -> "FakeHTTP":
        self.routes.append((method, pattern, response))
        return self

    def request(self, method, url, **kw):
        call = {"method": method.upper(), "url": url, **kw}
        self.calls.append(call)
        for m, pat, resp in self.routes:
            if m == method.upper() and re.search(pat, url):
                r = resp(call) if callable(resp) else resp
                if isinstance(r, Exception):
                    raise r
                r.headers = _Headers(r.headers)
                return r
        raise AssertionError(f"unexpected request {method} {url}")

    def urls(self) -> list[str]:
        return [c["url"] for c in self.calls]

    def everything_sent(self) -> str:
        """Every URL, query and body as one string (to assert a secret travelled only where allowed)."""
        parts = []
        for c in self.calls:
            parts.append(c["url"])
            for k in ("params", "json", "data"):
                if c.get(k) is not None:
                    parts.append(_json.dumps(c[k], default=str))
        return "\n".join(parts)
