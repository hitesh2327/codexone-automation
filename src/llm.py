"""Thin Gemini wrapper: structured JSON output (pydantic schema) with retries."""
from __future__ import annotations

import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from src.config import get_env
from src.logger import get_logger

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_FALLBACKS = "gemini-3.5-flash,gemini-flash-lite-latest"
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_env("GEMINI_API_KEY"))
    return _client


def _models() -> list[str]:
    primary = get_env("GEMINI_MODEL", required=False, default=DEFAULT_MODEL)
    fallbacks = get_env("GEMINI_FALLBACK_MODELS", required=False, default=DEFAULT_FALLBACKS)
    out = [primary] + [m.strip() for m in fallbacks.split(",") if m.strip()]
    return list(dict.fromkeys(out))


def generate_json(prompt: str, schema: type[T], *, system: str = "",
                  temperature: float = 0.7, retries_per_model: int = 2) -> T:
    """Call Gemini and parse the response into `schema`.

    Transient errors (429/5xx, bad JSON) are retried, then the next fallback
    model is tried -- free-tier models are often briefly overloaded (503).
    """
    config = types.GenerateContentConfig(
        system_instruction=system or None,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    last: Exception | None = None
    for model in _models():
        for attempt in range(1, retries_per_model + 1):
            try:
                resp = _get_client().models.generate_content(
                    model=model, contents=prompt, config=config)
                if resp.parsed is not None:
                    return resp.parsed  # type: ignore[return-value]
                return schema.model_validate_json(resp.text or "")
            except errors.APIError as e:
                last = e
                # 4xx other than rate limit are not worth retrying (bad key, bad request).
                if e.code and 400 <= e.code < 500 and e.code not in (404, 429):
                    raise RuntimeError(f"Gemini request rejected ({e.code}): {e.message}") from e
                if e.code == 404:
                    log.warning("Gemini model %s not found; skipping", model)
                    break
                wait = 5 * attempt
                log.warning("Gemini %s on %s (attempt %d/%d); retrying in %ds",
                            e.code, model, attempt, retries_per_model, wait)
                time.sleep(wait)
            except ValueError as e:  # malformed / schema-mismatched JSON
                last = e
                log.warning("Gemini %s returned invalid JSON (attempt %d): %s", model, attempt, e)
        log.warning("giving up on %s, trying next model", model)
    raise RuntimeError(f"Gemini failed on all models {_models()}: {last}")
