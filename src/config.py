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


def _from_env(name: str) -> str | None:
    for key in _ALIASES.get(name, (name,)):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def _from_store(name: str) -> str | None:
    """A value saved on the dashboard's Config page (src/config_store.py). Only for configurable names
    (src/config_schema.py), never bootstrap ones like DATABASE_URL; never raises (file mode, no table,
    database down, no master key: all simply mean "not in the store")."""
    from src.config_schema import STORE_NAMES
    if name not in STORE_NAMES:
        return None
    try:
        from src import config_store
        return config_store.lookup(name)
    except Exception:  # noqa: BLE001
        return None


def resolve(name: str) -> tuple[str | None, str | None]:
    """(value, source) with source "env" | "store" | None.

    Precedence while existing deployments migrate: the environment wins (GitHub secrets, SSM, .env keep
    working exactly as before), then the Config store. CONFIG_PRECEDENCE=store flips it once the store
    is trusted (spec 3.4 / 3.8; flip back to roll back).
    """
    store_first = (os.getenv("CONFIG_PRECEDENCE") or "env").strip().lower() == "store"
    order = (("store", _from_store), ("env", _from_env)) if store_first else (("env", _from_env), ("store", _from_store))
    for source, read in order:
        value = read(name)
        if value:
            return value, source
    return None, None


def get_env(name: str, required: bool = True, default: str | None = None) -> str | None:
    """Return a setting (environment, then the Config store; see resolve), raising a clear error if a
    required one is missing."""
    value, _ = resolve(name)
    if value:
        return value
    if required and default is None:
        raise MissingSecretError(
            f"Missing required setting '{name}'. Set it on the dashboard's Config page, "
            f"or add it to .env (local) or GitHub Secrets (CI)."
        )
    return default


@lru_cache(maxsize=1)
def load_brand() -> dict:
    """Brand settings, loaded once per process.

    Loads brand/config.yaml as the source of truth, overlaid with any database settings if present,
    or synchronizes config.yaml to the database settings table.
    """
    with BRAND_FILE.open(encoding="utf-8") as f:
        file_brand = yaml.safe_load(f)

    from src import db  # lazy: src.db imports this module
    if db.enabled():
        db_brand = db.get_setting("brand")
        if db_brand:
            # Keep brand/config.yaml authoritative for voices, language, and preferred_hook_formulas
            # while keeping other dashboard runtime overrides
            db_brand["voices"] = file_brand.get("voices", db_brand.get("voices"))
            db_brand["language"] = file_brand.get("language", db_brand.get("language"))
            db_brand["preferred_hook_formulas"] = file_brand.get("preferred_hook_formulas", db_brand.get("preferred_hook_formulas", []))
            return db_brand

    return file_brand


def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, LOGS_DIR, DATA_DIR, TEMPLATES_DIR):
        d.mkdir(parents=True, exist_ok=True)
