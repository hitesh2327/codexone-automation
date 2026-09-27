"""Central config: project paths, .env secrets, and brand settings."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output"
LOGS_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
BRAND_FILE = ROOT / "brand" / "config.yaml"
POSTED_FILE = DATA_DIR / "posted.json"

# Locally we read .env; in GitHub Actions the vars come from Secrets and
# load_dotenv is a no-op (it never overrides variables that are already set).
load_dotenv(ROOT / ".env", override=False)

# Alternate names accepted for a variable (first match wins).
_ALIASES: dict[str, tuple[str, ...]] = {
    "CLOUDINARY_URL": ("CLOUDINARY_URL", "COUDNARY_API_ENV_VAR", "CLOUDINARY_API_ENV_VAR"),
}


class MissingSecretError(RuntimeError):
    pass


def get_env(name: str, required: bool = True, default: str | None = None) -> str | None:
    """Return an env var, raising a clear error if a required one is missing."""
    for key in _ALIASES.get(name, (name,)):
        value = os.getenv(key)
        if value:
            return value.strip()
    if required and default is None:
        raise MissingSecretError(
            f"Missing required environment variable '{name}'. "
            f"Add it to .env (local) or GitHub Secrets (CI)."
        )
    return default


@lru_cache(maxsize=1)
def load_brand() -> dict:
    """Load brand/config.yaml once."""
    with BRAND_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, LOGS_DIR, DATA_DIR, TEMPLATES_DIR):
        d.mkdir(parents=True, exist_ok=True)
