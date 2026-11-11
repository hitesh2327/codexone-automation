"""Idempotent Phase-2 backfill and parity verification for the multi-platform schema.

Usage:
    python -m src.db.backfill_multiplatform [--batch-size 500] [--dry-run] [--verify-only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import nullcontext
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src import db
from src.config_store import StoreError, _load_dek, master_key
from src.db.models import (
    MediaAsset,
    OAuthToken,
    Post,
    PostedTopic,
    PublishingTarget,
    SocialAccount,
    User,
    UserConfigValue,
    utcnow,
)
from src.db.multiplatform import (
    decrypt_oauth_tokens,
    encrypt_oauth_tokens,
    expected_media_for_post,
    expected_targets_for_post,
    sync_post_multiplatform,
)
from src.user_config_store import _decrypt_row


def _resolve_default_user_id(s: Session) -> int:
    if s.get(User, 1) is not None:
        return 1
    uid = s.scalars(select(func.min(User.id))).first()
    return int(uid) if uid is not None else 1


def _chunked_user_ids(s: Session, batch_size: int) -> list[list[int]]:
    keys = ("IG_ACCESS_TOKEN", "IG_USER_ID", "YT_REFRESH_TOKEN", "YT_CLIENT_ID", "YT_PRIVACY")
    uids = list(
        s.scalars(
            select(UserConfigValue.user_id)
            .where(UserConfigValue.key.in_(keys))
            .distinct()
            .order_by(UserConfigValue.user_id.asc())
        )
    )
    return [uids[i : i + batch_size] for i in range(0, len(uids), batch_size)]


def _upsert_social_account_and_token(
    s: Session,
    *,
    user_id: int,
    platform: str,
    external_account_id: str,
    metadata_json: dict[str, Any],
    access_token: str | None = None,
    refresh_token: str | None = None,
    scopes: list[str] | None = None,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Return (account_action, token_action) in {'created', 'updated', 'skipped'}."""
    acct = s.scalars(
        select(SocialAccount).where(
            SocialAccount.user_id == user_id,
            SocialAccount.platform == platform,
            SocialAccount.external_account_id == external_account_id,
        )
    ).first()

    if acct is None:
        acct_action = "created"
        if not dry_run:
            acct = SocialAccount(
                user_id=user_id,
                platform=platform,
                external_account_id=external_account_id,
                account_type="business",
                status="active",
                metadata_json=metadata_json,
                is_default=True,
                connected_at=utcnow(),
                updated_at=utcnow(),
            )
            s.add(acct)
            s.flush()
    else:
        merged_meta = dict(acct.metadata_json or {})
        merged_meta.update(metadata_json)
        if merged_meta != (acct.metadata_json or {}):
            acct_action = "updated"
            if not dry_run:
                acct.metadata_json = merged_meta
                acct.updated_at = utcnow()
        else:
            acct_action = "skipped"

    if access_token is None and refresh_token is None:
        return acct_action, "skipped"

    if acct is None:
        # Only reachable when dry_run=True and account doesn't exist yet.
        return acct_action, "created"

    tok_row = s.scalars(select(OAuthToken).where(OAuthToken.social_account_id == acct.id)).first()
    if tok_row is None:
        tok_action = "created"
        if not dry_run:
            encrypt_oauth_tokens(
                s,
                acct.id,
                access_token=access_token,
                refresh_token=refresh_token,
                scopes=scopes,
            )
    else:
        try:
            cur_acc, cur_ref = decrypt_oauth_tokens(s, tok_row)
        except StoreError:
            cur_acc, cur_ref = None, None
        needs_update = (
            (access_token is not None and cur_acc != access_token)
            or (refresh_token is not None and cur_ref != refresh_token)
            or (scopes is not None and (tok_row.scopes or []) != scopes)
        )
        if needs_update:
            tok_action = "updated"
            if not dry_run:
                encrypt_oauth_tokens(
                    s,
                    acct.id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    scopes=scopes,
                )
        else:
            tok_action = "skipped"

    return acct_action, tok_action


def _backfill_social_accounts(s: Session, batch_size: int, dry_run: bool) -> dict[str, dict[str, int]]:
    acct_stats = {"created": 0, "updated": 0, "skipped": 0}
    tok_stats = {"created": 0, "updated": 0, "skipped": 0}

    batches = _chunked_user_ids(s, batch_size)
    if not batches:
        return {"social_accounts": acct_stats, "oauth_tokens": tok_stats}

    dek = None
    try:
        dek = _load_dek(s, master_key(), create=False)
    except StoreError:
        dek = None

    for uid_batch in batches:
        rows = list(
            s.scalars(
                select(UserConfigValue).where(UserConfigValue.user_id.in_(uid_batch))
            )
        )
        by_user: dict[int, dict[str, str]] = {}
        for r in rows:
            val = _decrypt_row(r, dek)
            if val:
                by_user.setdefault(r.user_id, {})[r.key] = val

        for uid in uid_batch:
            vals = by_user.get(uid, {})
            if vals.get("IG_ACCESS_TOKEN") or vals.get("IG_USER_ID"):
                ext_id = vals.get("IG_USER_ID") or f"ig-user-{uid}"
                a_act, t_act = _upsert_social_account_and_token(
                    s,
                    user_id=uid,
                    platform="instagram",
                    external_account_id=ext_id,
                    metadata_json={"source": "user_config_values"},
                    access_token=vals.get("IG_ACCESS_TOKEN"),
                    scopes=["instagram_business_content_publish"],
                    dry_run=dry_run,
                )
                acct_stats[a_act] += 1
                tok_stats[t_act] += 1

            if vals.get("YT_REFRESH_TOKEN") or vals.get("YT_CLIENT_ID"):
                meta: dict[str, Any] = {"source": "user_config_values"}
                if vals.get("YT_PRIVACY"):
                    meta["yt_privacy"] = vals["YT_PRIVACY"]
                if vals.get("YT_CLIENT_ID"):
                    meta["yt_client_id"] = vals["YT_CLIENT_ID"]
                a_act, t_act = _upsert_social_account_and_token(
                    s,
                    user_id=uid,
                    platform="youtube",
                    external_account_id=f"yt-default-{uid}",
                    metadata_json=meta,
                    refresh_token=vals.get("YT_REFRESH_TOKEN"),
                    scopes=["https://www.googleapis.com/auth/youtube.upload"],
                    dry_run=dry_run,
                )
                acct_stats[a_act] += 1
                tok_stats[t_act] += 1

    return {"social_accounts": acct_stats, "oauth_tokens": tok_stats}


def _backfill_posts(s: Session, batch_size: int, dry_run: bool, default_uid: int) -> dict[str, dict[str, int]]:
    target_stats = {"created": 0, "updated": 0, "skipped": 0}
    media_stats = {"created": 0, "updated": 0, "skipped": 0}

    offset = 0
    while True:
        posts = list(
            s.scalars(
                select(Post)
                .order_by(Post.created_at.asc(), Post.id.asc())
                .offset(offset)
                .limit(batch_size)
            )
        )
        if not posts:
            break
        for post in posts:
            res = sync_post_multiplatform(s, post, default_user_id=default_uid, dry_run=dry_run)
            for k in ("created", "updated", "skipped"):
                target_stats[k] += res["publishing_targets"][k]
                media_stats[k] += res["media_assets"][k]
        offset += len(posts)
        if len(posts) < batch_size:
            break

    return {"publishing_targets": target_stats, "media_assets": media_stats}


def _backfill_posted_topics(s: Session, batch_size: int, dry_run: bool, default_uid: int) -> dict[str, int]:
    stats = {"updated": 0, "skipped": 0}
    total_with_uid = int(
        s.scalar(select(func.count()).select_from(PostedTopic).where(PostedTopic.user_id.is_not(None))) or 0
    )
    stats["skipped"] = total_with_uid

    last_id = 0
    while True:
        rows = list(
            s.scalars(
                select(PostedTopic)
                .where(PostedTopic.user_id.is_(None), PostedTopic.id > last_id)
                .order_by(PostedTopic.id.asc())
                .limit(batch_size)
            )
        )
        if not rows:
            break
        last_id = rows[-1].id
        item_ids = [r.item_id for r in rows if r.item_id]
        post_owners: dict[str, int | None] = {}
        if item_ids:
            for pid, uid in s.execute(select(Post.id, Post.user_id).where(Post.id.in_(item_ids))).all():
                post_owners[pid] = uid
        for r in rows:
            resolved_uid = post_owners.get(r.item_id) if r.item_id in post_owners else None
            target_uid = resolved_uid if resolved_uid is not None else default_uid
            stats["updated"] += 1
            if not dry_run:
                r.user_id = target_uid
        if len(rows) < batch_size:
            break

    return stats


def backfill_all(
    session: Session | None = None,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run idempotent backfill for social_accounts, oauth_tokens, publishing_targets, media_assets, posted_topics."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    ctx = nullcontext(session) if session is not None else db.session()
    with ctx as s:
        default_uid = _resolve_default_user_id(s)
        cred_res = _backfill_social_accounts(s, batch_size, dry_run)
        post_res = _backfill_posts(s, batch_size, dry_run, default_uid)
        topic_res = _backfill_posted_topics(s, batch_size, dry_run, default_uid)
        if not dry_run:
            s.flush()
        return {
            "dry_run": dry_run,
            "social_accounts": cred_res["social_accounts"],
            "oauth_tokens": cred_res["oauth_tokens"],
            "publishing_targets": post_res["publishing_targets"],
            "media_assets": post_res["media_assets"],
            "posted_topics": topic_res,
        }


def _digest_rows(rows: list[tuple[Any, ...]]) -> str:
    payload = json.dumps(sorted(rows), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_parity(session: Session | None = None) -> dict[str, Any]:
    """Compare legacy Post/PostedTopic data with normalized PublishingTarget/MediaAsset/PostedTopic.user_id."""
    ctx = nullcontext(session) if session is not None else db.session()
    with ctx as s:
        posts = list(s.scalars(select(Post).order_by(Post.id.asc())))
        legacy_target_rows: list[tuple[str, str, str, str]] = []
        legacy_media_rows: list[tuple[str, str, int, str]] = []
        for p in posts:
            for t in expected_targets_for_post(p):
                legacy_target_rows.append((p.id, t["platform"], t["status"], t["external_post_id"] or ""))
            for m in expected_media_for_post(p):
                legacy_media_rows.append(
                    (p.id, m["role"], m["slide_index"] if m["slide_index"] is not None else -1, m["public_url"])
                )

        norm_targets = list(
            s.execute(
                select(
                    PublishingTarget.post_id,
                    PublishingTarget.platform,
                    PublishingTarget.status,
                    PublishingTarget.external_post_id,
                )
            ).all()
        )
        norm_target_rows = [(r[0], r[1], r[2], r[3] or "") for r in norm_targets]

        norm_media = list(
            s.execute(
                select(
                    MediaAsset.post_id,
                    MediaAsset.role,
                    MediaAsset.slide_index,
                    MediaAsset.public_url,
                ).where(MediaAsset.post_id.is_not(None))
            ).all()
        )
        norm_media_rows = [(r[0], r[1], r[2] if r[2] is not None else -1, r[3]) for r in norm_media]

        targets_checksum_legacy = _digest_rows(legacy_target_rows)
        targets_checksum_normalized = _digest_rows(norm_target_rows)
        media_checksum_legacy = _digest_rows(legacy_media_rows)
        media_checksum_normalized = _digest_rows(norm_media_rows)

        posted_total = int(s.scalar(select(func.count()).select_from(PostedTopic)) or 0)
        posted_missing_uid = int(
            s.scalar(select(func.count()).select_from(PostedTopic).where(PostedTopic.user_id.is_(None))) or 0
        )
        social_accounts_count = int(s.scalar(select(func.count()).select_from(SocialAccount)) or 0)
        oauth_tokens_count = int(s.scalar(select(func.count()).select_from(OAuthToken)) or 0)

        targets_match = len(legacy_target_rows) == len(norm_target_rows)
        targets_checksum_match = targets_checksum_legacy == targets_checksum_normalized
        media_match = len(legacy_media_rows) == len(norm_media_rows)
        media_checksum_match = media_checksum_legacy == media_checksum_normalized
        posted_topics_match = posted_missing_uid == 0

        return {
            "ok": (
                targets_match
                and targets_checksum_match
                and media_match
                and media_checksum_match
                and posted_topics_match
            ),
            "posts_count": len(posts),
            "expected_targets_count": len(legacy_target_rows),
            "publishing_targets_count": len(norm_target_rows),
            "targets_match": targets_match,
            "targets_checksum_legacy": targets_checksum_legacy,
            "targets_checksum_normalized": targets_checksum_normalized,
            "targets_checksum_match": targets_checksum_match,
            "expected_media_count": len(legacy_media_rows),
            "media_assets_count": len(norm_media_rows),
            "media_match": media_match,
            "media_checksum_legacy": media_checksum_legacy,
            "media_checksum_normalized": media_checksum_normalized,
            "media_checksum_match": media_checksum_match,
            "posted_topics_total": posted_total,
            "posted_topics_with_user_id": posted_total - posted_missing_uid,
            "posted_topics_missing_user_id": posted_missing_uid,
            "posted_topics_match": posted_topics_match,
            "social_accounts_count": social_accounts_count,
            "oauth_tokens_count": oauth_tokens_count,
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill and verify normalized multi-platform DB tables")
    ap.add_argument("--batch-size", type=int, default=500, help="rows/users per batch (default: 500)")
    ap.add_argument("--dry-run", action="store_true", help="inspect changes without writing to the database")
    ap.add_argument("--verify-only", action="store_true", help="only run verify_parity()")
    args = ap.parse_args(argv)

    if not db.enabled():
        print(json.dumps({"error": "DATABASE_URL is not set"}))
        return 1

    if args.verify_only:
        report = verify_parity()
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 2

    summary = backfill_all(batch_size=args.batch_size, dry_run=args.dry_run)
    parity = verify_parity()
    print(json.dumps({"backfill": summary, "parity": parity}, indent=2))
    if not args.dry_run and not parity["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
