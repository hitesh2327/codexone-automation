"""AWS Lambda entry point (behind CloudFront). Handler: api.lambda_handler.handler

Cold start: make /tmp-backed working folders. App and secrets are loaded lazily on the first request
to guarantee container boot stays under AWS Lambda's 10-second INIT timeout ceiling.
"""
from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path
from typing import Any

# Lambda's filesystem is read-only except /tmp; the image symlinks logs/ data/ output/ here.
for _d in ("logs", "data", "output"):
    Path("/tmp", _d).mkdir(parents=True, exist_ok=True)

_mangum_app = None
log = logging.getLogger("codexone.api")


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


def _get_mangum_app():
    global _mangum_app
    if _mangum_app is not None:
        return _mangum_app

    _load_secrets()

    from mangum import Mangum
    from api.app.main import app, sync_admin

    try:
        sync_admin()
    except Exception as e:
        log.warning("sync_admin failed during lazy init: %s", e)

    _verify = os.environ.get("ORIGIN_VERIFY", "")

    async def guarded(scope, receive, send):
        """Only CloudFront may call the function URL: it adds X-Origin-Verify, so anyone hitting the
        raw *.lambda-url.* address directly gets a 403 before the app sees the request."""
        if scope["type"] == "http" and _verify:
            sent = dict(scope["headers"]).get(b"x-origin-verify", b"").decode()
            if not hmac.compare_digest(sent, _verify):
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"Forbidden"}'})
                return
        await app(scope, receive, send)

    _mangum_app = Mangum(guarded, lifespan="off")
    return _mangum_app


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    app_instance = _get_mangum_app()
    return app_instance(event, context)

