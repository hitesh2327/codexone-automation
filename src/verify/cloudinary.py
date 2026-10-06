"""Cloudinary "API environment variable" (cloudinary://<api_key>:<api_secret>@<cloud_name>).

Sources: Admin API reference https://cloudinary.com/documentation/admin_api (Basic Authentication, the
`ping` method, status codes 401/403/404/420, 500 admin calls/hour on the free plan) and Upload API reference
https://cloudinary.com/documentation/image_upload_api_reference (Basic Authentication "in an Authorization
header", `destroy`, status codes). The credentials go in the Authorization header, never in the URL.

    format  scheme cloudinary://, key, secret and a cloud name made of letters, digits, '-' and '_'
    live    GET  /v1_1/<cloud>/ping                 -> key + secret + cloud name match (1 Admin API call)
            POST /v1_1/<cloud>/image/upload         -> a 633-byte JPEG into codexone/_selftest/<random>
                                                       (Upload API: not rate-limited per the docs)
            HEAD <secure_url>                       -> the public link serves an image (what Instagram and
                                                       Telegram will fetch)
            POST /v1_1/<cloud>/image/destroy        -> the test image is removed again (always attempted)
"""
from __future__ import annotations

import base64
import re
import secrets
from urllib.parse import urlsplit

from src.verify.base import Result, Run, Unreachable, body, has_bad_chars, http

INTEGRATION = "cloudinary"
API = "https://api.cloudinary.com/v1_1"
CLOUD_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SELFTEST_FOLDER = "codexone/_selftest"
# An 8x8 orange JPEG (Instagram only takes JPEG, so the test uses the same format the pipeline uploads).
TEST_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/"
    "2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUB"
    "AQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJico"
    "KSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ"
    "2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMi"
    "MoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOk"
    "paanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDSooor4c+7P//Z")


def parse(url: str) -> tuple[str, str, str] | None:
    """(api_key, api_secret, cloud_name) or None if the value isn't a well-formed Cloudinary URL."""
    if not url.lower().startswith("cloudinary://") or has_bad_chars(url):
        return None
    try:
        parts = urlsplit(url)
        key, secret, cloud = parts.username, parts.password, parts.hostname
    except ValueError:
        return None
    if not key or not secret or not cloud:
        return None
    # urlsplit lower-cases hostname; the cloud name is taken verbatim from the netloc instead
    cloud = parts.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    return (key, secret, cloud) if CLOUD_RE.match(cloud) else None


def classify(r) -> str:
    s = r.status_code
    if s == 401:
        return "cloudinary.rejected"
    if s == 403:
        return "cloudinary.forbidden"
    if s == 404:
        return "cloudinary.not_found"
    if s in (420, 429):
        return "cloudinary.rate_limited"
    return "cloudinary.unavailable"


def _delivery_url_ok(url: str) -> bool:
    """Only follow links on Cloudinary's own delivery hosts (the upload response decides the URL; we never
    let it point the server at an arbitrary host)."""
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return p.scheme == "https" and (host == "res.cloudinary.com" or host.endswith(".cloudinary.com")) and not p.username


def verify(values: dict[str, str], depth: str = "live") -> Result:
    run = Run(INTEGRATION, depth)
    raw = values.get("CLOUDINARY_URL") or ""
    if not raw:
        return run.finish(not_set=True)
    if "<" in raw or ">" in raw:  # the console shows the variable as a template to fill in (product_environment_settings)
        run.fail("format", "Looks like cloudinary://key:secret@cloud", "cloudinary.placeholder", depth="format")
        return run.finish()
    parsed = parse(raw)
    if not parsed:
        run.fail("format", "Looks like cloudinary://key:secret@cloud", "cloudinary.format", depth="format")
        return run.finish()
    key, secret, cloud = parsed
    run.ok("format", "Looks like cloudinary://key:secret@cloud", f"cloud name: {cloud}", depth="format")
    run.evidence["cloud"] = cloud
    if depth == "format":
        return run.finish()

    auth = (key, secret)
    try:
        r = http("GET", f"{API}/{cloud}/ping", auth=auth)
        data = body(r)
        if r.status_code != 200:
            run.fail("credentials", "Key, secret and cloud name match", classify(r))
            return run.finish()
        if data.get("status") != "ok":  # "HTML responses instead of JSON ... typically indicates an authentication issue"
            run.fail("credentials", "Key, secret and cloud name match", "cloudinary.rejected")
            return run.finish()
        run.ok("credentials", "Key, secret and cloud name match", "Admin API ping answered")

        public_id = f"{SELFTEST_FOLDER}/{secrets.token_hex(6)}"
        r = http("POST", f"{API}/{cloud}/image/upload", auth=auth, timeout=20,
                 data={"public_id": public_id}, files={"file": ("selftest.jpg", TEST_JPEG, "image/jpeg")})
    except Unreachable:
        run.fail("reachable", "Cloudinary is reachable", "cloudinary.unreachable")
        return run.finish()

    if r.status_code != 200:
        code = classify(r)
        run.fail("upload", "A test image uploads", code if code != "cloudinary.unavailable" or r.status_code >= 500
                 else "cloudinary.upload_failed")
        return run.finish()
    up = body(r)
    stored_id = str(up.get("public_id") or public_id)
    try:
        run.ok("upload", "A test image uploads", f"{len(TEST_JPEG)} bytes into {SELFTEST_FOLDER}/")
        url = str(up.get("secure_url") or "")
        if not _delivery_url_ok(url):
            run.skip("public_link", "The public link serves the image",
                     "The upload returned a delivery address outside cloudinary.com; not fetched.")
        else:
            try:
                h = http("HEAD", url)
                ctype = h.headers.get("content-type", "")
                if h.status_code == 200 and ctype.startswith("image/"):
                    run.ok("public_link", "The public link serves the image", f"HTTPS, {ctype}")
                else:
                    run.fail("public_link", "The public link serves the image", "cloudinary.delivery_failed",
                             f"HTTP {h.status_code}")
            except Unreachable:
                run.fail("public_link", "The public link serves the image", "cloudinary.unreachable")
    finally:  # never leave the test asset behind
        try:
            d = http("POST", f"{API}/{cloud}/image/destroy", auth=auth, data={"public_id": stored_id, "invalidate": "true"})
            if d.status_code == 200 and body(d).get("result") == "ok":
                run.ok("cleanup", "The test image was deleted again")
            else:
                run.warn("cleanup", "The test image was deleted again", "cloudinary.cleanup_failed", f"HTTP {d.status_code}")
        except Unreachable:
            run.warn("cleanup", "The test image was deleted again", "cloudinary.cleanup_failed", "network error")
    return run.finish()
