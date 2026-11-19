"""Tests for MNT-105: Web Download Mode, SSRF prevention, and ZIP generation."""
import pytest
from fastapi import HTTPException

from api.app.routes.posts import _validate_media_url
from src.user_taste import default_user_taste, get_user_taste, UserTaste


def test_validate_media_url_safe():
    # Safe URLs do not raise HTTPException
    _validate_media_url("https://res.cloudinary.com/codexone/video/upload/v1234/reel.mp4")
    _validate_media_url("https://sub.cloudinary.com/codexone/image/upload/v1234/slide.png")


def test_validate_media_url_ssrf_rejected():
    # Insecure scheme
    with pytest.raises(HTTPException) as exc1:
        _validate_media_url("http://127.0.0.1:8000/api")
    assert exc1.value.status_code == 400

    # Foreign or loopback hosts
    with pytest.raises(HTTPException) as exc2:
        _validate_media_url("https://localhost:3000")
    assert exc2.value.status_code == 400

    # Userinfo rejected
    with pytest.raises(HTTPException) as exc3:
        _validate_media_url("https://attacker@res.cloudinary.com/evil")
    assert exc3.value.status_code == 400

    # Non-standard port rejected
    with pytest.raises(HTTPException) as exc4:
        _validate_media_url("https://res.cloudinary.com:8080/evil")
    assert exc4.value.status_code == 400


def test_user_taste_delivery_mode_default():
    taste = default_user_taste()
    assert taste["delivery_mode"] == "auto_publish"
    ut = get_user_taste(None)
    assert ut.delivery_mode in ("auto_publish", "download_only")
