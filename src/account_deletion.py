"""Close an account and erase its personal data (DPDP Act right to erasure; Meta and YouTube deletion rules).

    from src import account_deletion
    account_deletion.delete_account(user_id)    # raises DeletionError; returns what was removed

Order matters:
1. Billing stops first: the Razorpay subscription (and any half-finished one) is cancelled now, not at the period
   end. If Razorpay can't be reached, nothing is deleted, so nobody is billed for an account that's gone.
2. In one database transaction: the user's posts, integration tokens (Instagram, YouTube, Telegram) and one-time
   codes are deleted (explicitly: never relying on the database's ON DELETE CASCADE being enforced); the activity
   log and generation history keep their events for the record but lose the name, email and details (actor becomes
   "deleted user"); then the user row goes.
3. After the commit, the posts' images and videos are deleted from Cloudinary. A media failure is logged for
   manual clean-up but doesn't undo the deletion.

Kept, as the law requires: payment records at Razorpay (tax and audit). Posts already published to Instagram or
YouTube stay there; the user deletes them on those platforms. The owner account can't be deleted this way.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, or_, select, update

from src import activity, billing, db

log = logging.getLogger("codexone.account_deletion")
ANONYMOUS = "deleted user"
_BILLABLE = ("created", "authenticated", "active", "pending", "halted", "paused")


class DeletionError(Exception):
    """`code`: not_found | owner | billing."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _stop_billing(user) -> None:
    if not billing.configured():
        return
    for sub_id in (user.razorpay_pending_subscription_id, user.razorpay_subscription_id):
        if not sub_id:
            continue
        try:
            if billing.fetch_subscription(sub_id).get("status") in _BILLABLE:
                billing.cancel_subscription(sub_id, at_cycle_end=False)
        except billing.BillingError as e:
            raise DeletionError("billing", "We couldn't cancel your subscription with Razorpay, so nothing was deleted. "
                                           "Try again in a few minutes.") from e


def _media_urls(media: dict | None) -> list[str]:
    urls: list[str] = []
    for value in (media or {}).values():
        urls.extend(v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str))
    return urls


def delete_account(user_id: int) -> dict:
    from src.db.models import ActivityLog, GenerationJob, OtpCode, Post, User, UserConfigValue
    with db.session() as s:
        user = s.get(User, user_id, with_for_update=True)
        if user is None:
            raise DeletionError("not_found", "That account doesn't exist.")
        if (user.role or "") == "owner":
            raise DeletionError("owner", "The owner account runs Mintly's own posts and can't be deleted here.")
        _stop_billing(user)

        names = [n for n in (user.username, user.email) if n]
        mine = or_(ActivityLog.user_id == user_id, ActivityLog.actor.in_(names)) if names else ActivityLog.user_id == user_id
        s.execute(update(ActivityLog).where(mine).values(actor=ANONYMOUS, detail=None, user_id=None))
        jobs = or_(GenerationJob.user_id == user_id, GenerationJob.requested_by.in_(names)) if names \
            else GenerationJob.user_id == user_id
        s.execute(update(GenerationJob).where(jobs).values(requested_by=ANONYMOUS, user_id=None))

        posts = s.scalars(select(Post).where(Post.user_id == user_id)).all()
        urls = [u for p in posts for u in _media_urls(p.media)]
        for p in posts:
            s.delete(p)
        s.execute(delete(UserConfigValue).where(UserConfigValue.user_id == user_id))
        s.execute(delete(OtpCode).where(OtpCode.user_id == user_id))
        s.delete(user)
    removed_media = 0
    if urls:
        try:
            from src import upload
            removed_media = upload.delete_media(urls)
        except Exception as e:  # noqa: BLE001 -- the account is gone; leftover files are cleaned up by hand
            log.error("account %s deleted, but %d media files couldn't be removed: %s", user_id, len(urls), type(e).__name__)
    activity.record("account.deleted", f"Account #{user_id} was deleted by its owner", level="warning",
                    source="profile", actor=ANONYMOUS, detail={"posts": len(posts), "media": removed_media})
    return {"posts": len(posts), "media_files": removed_media}
