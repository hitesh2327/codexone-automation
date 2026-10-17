"""Per-user integration config: Telegram chat ID, Instagram, YouTube credentials.

GET  /api/integrations          -> list all per-user keys with masked values
PUT  /api/integrations/{key}    -> save one key (body: {value: str})
DELETE /api/integrations/{key}  -> remove one key

Only keys in PER_USER_FIELD_NAMES are accepted.
Mounted under /api (signed in + CSRF on writes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.app.deps import CurrentUser, current_user
from src import user_config_store
from src.config_schema import FIELDS_BY_NAME, PER_USER_FIELD_NAMES

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _actor(cu: CurrentUser) -> str:
    return cu.username or cu.email or f"user {cu.id}"


def _mask(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    f = FIELDS_BY_NAME.get(key)
    if f and f.secret:
        return f"***{value[-4:]}" if len(value) > 4 else "****"
    return value


@router.get("")
def list_integrations(cu: CurrentUser = Depends(current_user)) -> dict:
    data = user_config_store.snapshot(cu.id)
    return {
        "values": {
            k: {"set": v is not None, "masked": _mask(k, v)}
            for k in PER_USER_FIELD_NAMES
            if (f := FIELDS_BY_NAME.get(k)) and not f.advanced
        }
    }


class PutBody(BaseModel):
    value: str = Field(min_length=1, max_length=2000)


@router.put("/{key}")
def put_integration(key: str, body: PutBody, cu: CurrentUser = Depends(current_user)) -> dict:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    versions = user_config_store.save(cu.id, {key: body.value}, actor=_actor(cu))
    return {"key": key, "version": versions[key]}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(key: str, cu: CurrentUser = Depends(current_user)) -> None:
    if key not in PER_USER_FIELD_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "unknown_key", "message": f"Not a per-user setting: {key}"})
    user_config_store.delete(cu.id, key)
