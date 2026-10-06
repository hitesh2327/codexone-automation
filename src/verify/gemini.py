"""Gemini API key (+ optional model choice).

    format  key present, no whitespace/control characters (no prefix or length rule: Google is moving
            from "standard" to "auth" keys and the shape is not a documented contract, spec U1);
            model ids match a strict pattern (they go into a URL path)
    live    GET  /v1beta/models                       -> the key is accepted   (docs: ai.google.dev/api/models)
            POST /v1beta/models/{model}:countTokens   -> this model exists for this key (ai.google.dev/api/tokens)
    deep    POST /v1beta/models/{model}:generateContent with a tiny JSON schema: proves structured output
            works on this key and model. Uses one request of the daily quota, so only on explicit request.

The key travels in the documented `x-goog-api-key` header (ai.google.dev/gemini-api/docs/api-key, REST
example), never in the URL.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from src.verify.base import Result, Run, Unreachable, body, has_bad_chars, http

INTEGRATION = "gemini"
API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-flash-latest"  # mirrors src/llm.py (not imported: it pulls in the SDK)
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,79}$")


def _model(raw: str | None) -> str:
    m = (raw or "").strip()
    return m[len("models/"):] if m.startswith("models/") else m


def classify(r, context: str) -> str:
    """Map an error response to a catalogue code. The google.rpc error shape is parsed defensively:
    `error.status` / `error.details[].reason` / `error.code` (int or snake_case string) / message."""
    err = body(r).get("error") or {}
    if not isinstance(err, dict):
        err = {}
    msg = str(err.get("message") or "").lower()
    status = str(err.get("status") or "").upper()
    code = str(err.get("code") or "").lower()
    reasons = {str(d.get("reason") or "").upper() for d in err.get("details") or [] if isinstance(d, dict)}
    quota_ids = " ".join(str(v.get("quotaId") or "") for d in err.get("details") or [] if isinstance(d, dict)
                         for v in d.get("violations") or [] if isinstance(v, dict)).lower()
    s = r.status_code
    if "leaked" in msg or "blocked" in msg or "API_KEY_SERVICE_BLOCKED" in reasons:
        return "gemini.key_blocked"
    if s == 401 or "API_KEY_INVALID" in reasons or (s == 400 and "api key" in msg):
        return "gemini.key_rejected"
    if s == 402 or code == "payment_required":
        return "gemini.billing"
    if s == 403 or status == "PERMISSION_DENIED" or (s == 400 and status == "FAILED_PRECONDITION"):
        return "gemini.forbidden"
    if s == 404:
        return "gemini.model_not_found" if context == "model" else "gemini.unavailable"
    if s == 429:
        daily = code == "quota_exceeded" or "perday" in quota_ids or "per day" in msg or "daily" in msg
        return "gemini.quota" if daily else "gemini.rate_limited"
    return "gemini.unavailable"


def verify(values: dict[str, str], depth: str = "live") -> Result:
    run = Run(INTEGRATION, depth)
    key = values.get("GEMINI_API_KEY") or ""
    if not key:
        return run.finish(not_set=True)
    if has_bad_chars(key):
        run.fail("key_format", "Key looks like a key", "gemini.format", depth="format")
    else:
        run.ok("key_format", "Key looks like a key", depth="format")

    model = _model(values.get("GEMINI_MODEL")) or DEFAULT_MODEL
    fallbacks = [_model(m) for m in (values.get("GEMINI_FALLBACK_MODELS") or "").split(",") if m.strip()]
    bad = [m for m in [model, *fallbacks] if not MODEL_RE.match(m)]
    if bad:
        run.fail("model_format", "Model names are valid", "gemini.model_format", depth="format")
    else:
        run.ok("model_format", "Model names are valid", f"main model: {model}", depth="format")
    run.evidence["model"] = model if not bad else None
    if run.failed or depth == "format":
        return run.finish()

    headers = {"x-goog-api-key": key}
    try:
        r = http("GET", f"{API}/models", headers=headers, params={"pageSize": 1000})
        if r.status_code != 200:
            run.fail("key_accepted", "Gemini accepts the key", classify(r, "key"))
            return run.finish()
        names = [m.get("name", "") for m in body(r).get("models") or [] if isinstance(m, dict)]
        run.ok("key_accepted", "Gemini accepts the key", f"{len(names)} models visible to this key")
        run.evidence["models_visible"] = len(names)

        r = http("POST", f"{API}/models/{quote(model, safe='')}:countTokens", headers=headers,
                 json={"contents": [{"parts": [{"text": "ping"}]}]})
        if r.status_code != 200 or "totalTokens" not in body(r):
            run.fail("model_available", f"Model {model} works with this key",
                     classify(r, "model") if r.status_code != 200 else "gemini.unavailable")
            return run.finish()
        run.ok("model_available", f"Model {model} works with this key", "countTokens answered (nothing generated)")
    except Unreachable:
        run.fail("reachable", "Gemini is reachable", "gemini.unreachable")
        return run.finish()

    if depth != "deep":
        run.skip("generation", "Structured generation works", "Not run: it uses 1 request of today's quota. "
                 "Use 'Run a real test' to include it.", depth="deep")
        return run.finish()
    try:
        r = http("POST", f"{API}/models/{quote(model, safe='')}:generateContent", headers=headers, timeout=25, json={
            "contents": [{"parts": [{"text": "Return the JSON object {\"ok\": true}."}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 256,
                                 "responseSchema": {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"}}}},
        })
    except Unreachable:
        run.fail("generation", "Structured generation works", "gemini.unreachable", depth="deep")
        return run.finish()
    if r.status_code != 200:
        run.fail("generation", "Structured generation works", classify(r, "model"), depth="deep")
        return run.finish()
    try:  # candidates[0].content.parts[*].text holds the JSON (shape per ai.google.dev/api/generate-content)
        parts = body(r)["candidates"][0]["content"]["parts"]
        parsed = json.loads("".join(p.get("text", "") for p in parts if isinstance(p, dict)))
        assert isinstance(parsed, dict)
        run.ok("generation", "Structured generation works", "1 request used", depth="deep")
    except (KeyError, IndexError, TypeError, ValueError, AssertionError):
        run.warn("generation", "Structured generation works", "gemini.generation_empty", depth="deep")
    return run.finish()
