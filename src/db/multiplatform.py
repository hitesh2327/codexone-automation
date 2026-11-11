"""Multi-platform normalized schema helpers: AAD-bound OAuth encryption and Post dual-write sync."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config_store import StoreError, _DEK_AAD, _dek_cache, _kek_id, _load_dek, _open, _seal, master_key
from src.db.models import ConfigKey, MediaAsset, OAuthToken, Post, PublishingTarget, SocialAccount, utcnow
from src.redact import register

LEGACY_PLATFORM_MAP: dict[str, str] = {
    "ig": "instagram",
    "yt": "youtube",
}

DEFAULT_KIND_TARGETS: dict[str, tuple[str, ...]] = {
    "reel": ("ig", "yt"),
    "carousel": ("ig",),
    "image": ("ig",),
}


def normalize_platform(platform: str) -> str:
    p = (platform or "").strip().lower()
    return LEGACY_PLATFORM_MAP.get(p, p)


def oauth_token_aad(social_account_id: int, dek_version: int) -> bytes:
    """Bind ciphertext to a specific social_account_id and DEK version."""
    return f"oauth_token|{social_account_id}|{dek_version}".encode()


def _load_dek_for_version(s: Session, kek: bytes, dek_version: int) -> bytes:
    cache_key = (_kek_id(kek), dek_version)
    if cache_key in _dek_cache:
        return _dek_cache[cache_key]
    row = s.get(ConfigKey, dek_version)
    if row is None:
        raise StoreError("database.key_mismatch", f"missing ConfigKey version {dek_version}")
    dek_key = _open(kek, row.nonce, row.wrapped_dek, _DEK_AAD % row.version)
    _dek_cache[cache_key] = dek_key
    return dek_key


def encrypt_oauth_tokens(
    s: Session,
    social_account_id: int,
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_type: str = "Bearer",
    scopes: list[str] | None = None,
    access_expires_at: datetime | None = None,
    refresh_expires_at: datetime | None = None,
    last_refreshed_at: datetime | None = None,
) -> OAuthToken:
    """Encrypt access/refresh tokens using AES-256-GCM with account-bound AAD and upsert OAuthToken."""
    kek = master_key()
    dek = _load_dek(s, kek, create=True)
    assert dek is not None
    aad = oauth_token_aad(social_account_id, dek.version)

    row = s.scalars(select(OAuthToken).where(OAuthToken.social_account_id == social_account_id)).first()
    if row is None:
        row = OAuthToken(social_account_id=social_account_id)
        s.add(row)

    row.dek_version = dek.version
    row.token_type = token_type
    if scopes is not None:
        row.scopes = list(scopes)
    elif row.scopes is None:
        row.scopes = []

    if access_token is not None:
        row.access_token_nonce, row.access_token_enc = _seal(dek.key, access_token.encode(), aad)
        register(access_token)
    if refresh_token is not None:
        row.refresh_token_nonce, row.refresh_token_enc = _seal(dek.key, refresh_token.encode(), aad)
        register(refresh_token)

    if access_expires_at is not None:
        row.access_expires_at = access_expires_at
    if refresh_expires_at is not None:
        row.refresh_expires_at = refresh_expires_at
    if last_refreshed_at is not None:
        row.last_refreshed_at = last_refreshed_at

    s.flush()
    return row


def decrypt_oauth_tokens(
    s: Session,
    token_row: OAuthToken,
    *,
    expected_social_account_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Decrypt (access_token, refresh_token) verifying AAD against social_account_id and dek_version."""
    acct_id = expected_social_account_id if expected_social_account_id is not None else token_row.social_account_id
    kek = master_key()
    dek_key = _load_dek_for_version(s, kek, token_row.dek_version)
    aad = oauth_token_aad(acct_id, token_row.dek_version)

    access: str | None = None
    refresh: str | None = None
    if token_row.access_token_enc and token_row.access_token_nonce:
        access = _open(dek_key, token_row.access_token_nonce, token_row.access_token_enc, aad).decode()
        register(access)
    if token_row.refresh_token_enc and token_row.refresh_token_nonce:
        refresh = _open(dek_key, token_row.refresh_token_nonce, token_row.refresh_token_enc, aad).decode()
        register(refresh)
    return access, refresh


def extract_storage_info(url: str, default_mime: str = "application/octet-stream") -> tuple[str, str, str]:
    """Extract (storage_provider, storage_key, mime_type) from a media URL."""
    from src.upload import public_id_of

    raw = (url or "").strip()
    if found := public_id_of(raw):
        public_id, resource_type = found
        mime = "video/mp4" if resource_type == "video" else "image/jpeg"
        return "cloudinary", public_id, mime

    parsed = urlsplit(raw)
    host = parsed.netloc.lower()
    if "cloudinary.com" in host:
        provider = "cloudinary"
    elif parsed.scheme == "s3" or "amazonaws.com" in host:
        provider = "s3"
    elif parsed.scheme in ("http", "https"):
        provider = "cloudinary"
    else:
        provider = "local"

    key = parsed.path.lstrip("/") or raw
    lower = parsed.path.lower()
    if lower.endswith(".mp4"):
        mime = "video/mp4"
    elif lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif lower.endswith(".srt"):
        mime = "text/plain"
    else:
        mime = default_mime
    return provider, key, mime


def _parse_iso_dt(val: str | None) -> datetime | None:
    if not val or not isinstance(val, str):
        return None
    try:
        dt = datetime.fromisoformat(val)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _derive_target_status(post_status: str, has_schedule: bool, plat_entry: dict) -> str:
    p_status = str(plat_entry.get("status") or "").strip().lower()
    if p_status in ("published", "failed", "skipped"):
        return p_status
    s = (post_status or "pending").strip().lower()
    if s == "published":
        return "published"
    if s == "publishing":
        return "publishing"
    if s == "failed":
        return "failed"
    if s in ("rejected", "replaced", "expired"):
        return "cancelled"
    if s == "approved":
        return "scheduled" if has_schedule else "queued"
    return "queued"


def expected_targets_for_post(post: Post) -> list[dict]:
    """Build canonical PublishingTarget specs from a legacy Post row."""
    allowed = DEFAULT_KIND_TARGETS.get(post.kind, ("ig",))
    raw_targets = post.targets if isinstance(post.targets, list) else list(allowed)
    platforms_blob = post.platforms if isinstance(post.platforms, dict) else {}

    ordered_keys: list[tuple[str, str]] = []
    seen_norm: set[str] = set()
    for raw in [*raw_targets, *platforms_blob.keys()]:
        if not isinstance(raw, str) or not raw.strip():
            continue
        norm = normalize_platform(raw)
        if norm not in seen_norm:
            seen_norm.add(norm)
            ordered_keys.append((raw, norm))

    specs: list[dict] = []
    for raw_key, norm in ordered_keys:
        entry = platforms_blob.get(raw_key)
        if not isinstance(entry, dict):
            entry = platforms_blob.get(norm)
        if not isinstance(entry, dict):
            entry = {}

        status = _derive_target_status(post.status, post.publish_at is not None, entry)
        ext_id = entry.get("id")
        if not ext_id and norm == "instagram" and post.ig_media_id:
            ext_id = post.ig_media_id
        published_at = _parse_iso_dt(entry.get("at"))
        if published_at is None and status == "published":
            published_at = post.published_at

        title_override = post.yt_title if (norm == "youtube" and post.yt_title) else None
        platform_options = {"yt_description": post.yt_description} if (norm == "youtube" and post.yt_description) else {}
        specs.append({
            "platform": norm,
            "status": status,
            "scheduled_at": post.publish_at,
            "published_at": published_at,
            "external_post_id": str(ext_id) if ext_id else None,
            "external_url": str(entry["url"]) if entry.get("url") else None,
            "title_override": title_override,
            "platform_options": platform_options,
            "attempts": int(entry.get("attempts") if entry.get("attempts") is not None else (post.attempts or 0)),
            "error_message": str(entry["error"]) if entry.get("error") else None,
        })
    return specs


def expected_media_for_post(post: Post) -> list[dict]:
    """Build canonical MediaAsset specs from a legacy Post.media JSON blob."""
    media = post.media if isinstance(post.media, dict) else {}
    specs: list[dict] = []

    slides = media.get("carousel")
    if isinstance(slides, list):
        for idx, url in enumerate(slides):
            if isinstance(url, str) and url.strip():
                provider, key, mime = extract_storage_info(url, "image/jpeg")
                specs.append({
                    "role": "carousel_slide",
                    "slide_index": idx,
                    "storage_provider": provider,
                    "storage_key": key,
                    "public_url": url.strip(),
                    "mime_type": mime,
                })

    for media_key, role, default_mime in (
        ("reel", "reel_mp4", "video/mp4"),
        ("cover", "cover_jpg", "image/jpeg"),
        ("image_reel", "image_reel_mp4", "video/mp4"),
        ("image_cover", "cover_jpg", "image/jpeg"),
    ):
        url = media.get(media_key)
        if isinstance(url, str) and url.strip():
            slide_idx = 1 if (media_key == "image_cover" and isinstance(media.get("cover"), str) and media.get("cover")) else None
            provider, key, mime = extract_storage_info(url, default_mime)
            specs.append({
                "role": role,
                "slide_index": slide_idx,
                "storage_provider": provider,
                "storage_key": key,
                "public_url": url.strip(),
                "mime_type": mime,
            })
    return specs


def _find_default_social_account_id(s: Session, user_id: int | None, platform: str) -> int | None:
    if user_id is None:
        return None
    stmt = (
        select(SocialAccount.id)
        .where(SocialAccount.user_id == user_id, SocialAccount.platform == platform)
        .order_by(SocialAccount.is_default.desc(), SocialAccount.id.asc())
        .limit(1)
    )
    return s.scalars(stmt).first()


def sync_post_multiplatform(
    s: Session,
    post: Post,
    *,
    default_user_id: int = 1,
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """Idempotently sync PublishingTarget and MediaAsset rows from a Post row."""
    target_counts = {"created": 0, "updated": 0, "skipped": 0}
    media_counts = {"created": 0, "updated": 0, "skipped": 0}

    existing_targets = list(
        s.scalars(select(PublishingTarget).where(PublishingTarget.post_id == post.id))
    )
    by_acct: dict[int, PublishingTarget] = {
        t.social_account_id: t for t in existing_targets if t.social_account_id is not None
    }
    by_plat: dict[str, PublishingTarget] = {}
    for t in existing_targets:
        by_plat.setdefault(t.platform, t)

    target_specs = expected_targets_for_post(post)
    seen_target_ids: set[int] = set()
    for spec in target_specs:
        acct_id = _find_default_social_account_id(s, post.user_id, spec["platform"])
        row = by_acct.get(acct_id) if acct_id is not None else None
        if row is None:
            row = by_plat.get(spec["platform"])
        if row is None:
            target_counts["created"] += 1
            if not dry_run:
                row = PublishingTarget(
                    post_id=post.id,
                    social_account_id=acct_id,
                    platform=spec["platform"],
                    status=spec["status"],
                    scheduled_at=spec["scheduled_at"],
                    published_at=spec["published_at"],
                    external_post_id=spec["external_post_id"],
                    external_url=spec["external_url"],
                    title_override=spec["title_override"],
                    platform_options=spec["platform_options"],
                    attempts=spec["attempts"],
                    error_message=spec["error_message"],
                    updated_at=utcnow(),
                )
                s.add(row)
                s.flush()
                seen_target_ids.add(row.id)
        else:
            seen_target_ids.add(row.id)
            changed = (
                (acct_id is not None and row.social_account_id != acct_id)
                or row.status != spec["status"]
                or row.scheduled_at != spec["scheduled_at"]
                or row.published_at != spec["published_at"]
                or row.external_post_id != spec["external_post_id"]
                or row.external_url != spec["external_url"]
                or row.title_override != spec["title_override"]
                or (row.platform_options or {}) != spec["platform_options"]
                or row.attempts != spec["attempts"]
                or row.error_message != spec["error_message"]
            )
            if changed:
                target_counts["updated"] += 1
                if not dry_run:
                    if acct_id is not None:
                        row.social_account_id = acct_id
                    row.status = spec["status"]
                    row.scheduled_at = spec["scheduled_at"]
                    row.published_at = spec["published_at"]
                    row.external_post_id = spec["external_post_id"]
                    row.external_url = spec["external_url"]
                    row.title_override = spec["title_override"]
                    row.platform_options = spec["platform_options"]
                    row.attempts = spec["attempts"]
                    row.error_message = spec["error_message"]
                    row.updated_at = utcnow()
            else:
                target_counts["skipped"] += 1

    if not dry_run:
        for t in existing_targets:
            if t.id not in seen_target_ids:
                s.delete(t)

    effective_uid = post.user_id if post.user_id is not None else default_user_id
    existing_media = list(
        s.scalars(select(MediaAsset).where(MediaAsset.post_id == post.id))
    )
    media_by_key: dict[tuple[str, int | None], MediaAsset] = {
        (m.role, m.slide_index): m for m in existing_media
    }
    seen_media_keys: set[tuple[str, int | None]] = set()
    for spec in expected_media_for_post(post):
        mkey = (spec["role"], spec["slide_index"])
        seen_media_keys.add(mkey)
        mrow = media_by_key.get(mkey)
        if mrow is None:
            media_counts["created"] += 1
            if not dry_run:
                s.add(
                    MediaAsset(
                        user_id=effective_uid,
                        post_id=post.id,
                        role=spec["role"],
                        slide_index=spec["slide_index"],
                        storage_provider=spec["storage_provider"],
                        storage_key=spec["storage_key"],
                        public_url=spec["public_url"],
                        mime_type=spec["mime_type"],
                    )
                )
        else:
            changed = (
                mrow.user_id != effective_uid
                or mrow.storage_provider != spec["storage_provider"]
                or mrow.storage_key != spec["storage_key"]
                or mrow.public_url != spec["public_url"]
                or mrow.mime_type != spec["mime_type"]
            )
            if changed:
                media_counts["updated"] += 1
                if not dry_run:
                    mrow.user_id = effective_uid
                    mrow.storage_provider = spec["storage_provider"]
                    mrow.storage_key = spec["storage_key"]
                    mrow.public_url = spec["public_url"]
                    mrow.mime_type = spec["mime_type"]
            else:
                media_counts["skipped"] += 1

    if not dry_run:
        for m in existing_media:
            if (m.role, m.slide_index) not in seen_media_keys:
                s.delete(m)

    return {"publishing_targets": target_counts, "media_assets": media_counts}
