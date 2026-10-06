"""AWS Lambda entry point (behind CloudFront). Handler: api.lambda_handler.handler

Cold start: make /tmp-backed working folders, load secrets from SSM Parameter Store into the
environment, then import the app (its settings read the environment on import).
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path

# Lambda's filesystem is read-only except /tmp; the image symlinks logs/ data/ output/ here.
for _d in ("logs", "data", "output"):
    Path("/tmp", _d).mkdir(parents=True, exist_ok=True)


def _load_secrets() -> None:
    prefix = os.environ.get("SSM_PREFIX")
    if not prefix:
        return
    import boto3

    ssm, token = boto3.client("ssm"), None
    while True:
        kw = {"Path": prefix, "WithDecryption": True, **({"NextToken": token} if token else {})}
        page = ssm.get_parameters_by_path(**kw)
        for p in page["Parameters"]:
            os.environ.setdefault(p["Name"].rsplit("/", 1)[-1], p["Value"])  # template env wins
        token = page.get("NextToken")
        if not token:
            break


_load_secrets()

from mangum import Mangum  # noqa: E402

from api.app.main import app  # noqa: E402

_VERIFY = os.environ.get("ORIGIN_VERIFY", "")


async def guarded(scope, receive, send):
    """Only CloudFront may call the function URL: it adds X-Origin-Verify, so anyone hitting the
    raw *.lambda-url.* address directly gets a 403 before the app sees the request."""
    if scope["type"] == "http" and _VERIFY:
        sent = dict(scope["headers"]).get(b"x-origin-verify", b"").decode()
        if not hmac.compare_digest(sent, _VERIFY):
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Forbidden"}'})
            return
    await app(scope, receive, send)


handler = Mangum(guarded, lifespan="auto")
