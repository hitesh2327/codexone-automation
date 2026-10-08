"""The visitor's real IP address, for rate limits and logs (QA-M-05).

Behind CloudFront every request reaches the Lambda from a CloudFront edge address, so `request.client.host`
is shared by everyone on that edge: 20 bad sign-ins from anyone locked out everyone there. The real address
is taken ONLY from a header a trusted proxy sets, chosen by CLIENT_IP_SOURCE:

    (unset)                    the TCP peer (request.client.host): direct exposure, or a proxy you don't trust
    cloudfront                 CloudFront-Viewer-Address ("ip:port"), which CloudFront itself sets. Honoured only
                               when ORIGIN_VERIFY is set, i.e. the Lambda rejects anything that did not come
                               through CloudFront (api/lambda_handler.py), so a visitor can't send it directly.
    x-forwarded-for            the entry TRUSTED_PROXY_HOPS (default 1) from the right of X-Forwarded-For: the
                               address your own reverse proxy saw. Entries a client adds on the left are ignored.

A missing or malformed header falls back to the TCP peer (never to a client-chosen value), so a spoofed header
can neither dodge a limit nor pin one on someone else.
"""
from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import Request

log = logging.getLogger("codexone.api.clientip")
_warned = False


def _valid(raw: str) -> str | None:
    raw = raw.strip().strip("[]")
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def _viewer_address(value: str) -> str | None:
    """CloudFront-Viewer-Address: "198.51.100.10:46532" or "2001:db8::1:46532" (address, then the port)."""
    value = value.strip()
    if not value:
        return None
    if value.startswith("["):  # [v6]:port
        return _valid(value[1:value.find("]")]) if "]" in value else None
    host, _, port = value.rpartition(":")
    return _valid(host) if host and port.isdigit() else _valid(value)


def client_ip(request: Request) -> str:
    global _warned
    peer = request.client.host if request.client else "unknown"
    source = (os.environ.get("CLIENT_IP_SOURCE") or "").strip().lower()
    if source == "cloudfront":
        if not os.environ.get("ORIGIN_VERIFY"):
            if not _warned:
                log.warning("CLIENT_IP_SOURCE=cloudfront ignored: ORIGIN_VERIFY isn't set, so the header can't be trusted")
                _warned = True
            return peer
        return _viewer_address(request.headers.get("cloudfront-viewer-address", "")) or peer
    if source == "x-forwarded-for":
        try:
            hops = max(1, int(os.environ.get("TRUSTED_PROXY_HOPS") or "1"))
        except ValueError:
            hops = 1
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        return (_valid(parts[-hops]) if len(parts) >= hops else None) or peer
    return peer
