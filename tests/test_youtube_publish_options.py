"""Unit tests for YouTube Shorts publishing options, privacy defaults, and scheduling."""
from __future__ import annotations

import logging
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config_schema
from src import publish_youtube as yt


def test_privacy_defaults_to_public_when_unset(monkeypatch):
    monkeypatch.delenv("YT_PRIVACY", raising=False)
    assert yt.privacy() == "public"


def test_privacy_defaults_to_public_when_empty_string(monkeypatch):
    monkeypatch.setenv("YT_PRIVACY", "")
    assert yt.privacy() == "public"


def test_privacy_respects_valid_choices(monkeypatch):
    for choice in ("public", "unlisted", "private"):
        monkeypatch.setenv("YT_PRIVACY", choice)
        assert yt.privacy() == choice
        # Case insensitive
        monkeypatch.setenv("YT_PRIVACY", choice.upper())
        assert yt.privacy() == choice


def test_privacy_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("YT_PRIVACY", "invalid_choice")
    with pytest.raises(yt.YTError, match="YT_PRIVACY must be private, unlisted or public"):
        yt.privacy()


def test_build_metadata_outputs_public_by_default(monkeypatch):
    monkeypatch.delenv("YT_PRIVACY", raising=False)
    meta = yt.build_metadata("Sample caption\n\n#systemdesign")
    assert meta["status"]["privacyStatus"] == "public"
    assert "publishAt" not in meta["status"]


def test_build_metadata_outputs_configured_privacy(monkeypatch):
    monkeypatch.setenv("YT_PRIVACY", "unlisted")
    meta = yt.build_metadata("Sample caption\n\n#systemdesign")
    assert meta["status"]["privacyStatus"] == "unlisted"
    assert "publishAt" not in meta["status"]


def test_build_metadata_with_publish_at_sets_private_and_publish_at(monkeypatch):
    # Even if YT_PRIVACY is public, YouTube Data API v3 requires privacyStatus="private" for scheduled uploads
    monkeypatch.setenv("YT_PRIVACY", "public")
    scheduled_time = "2026-11-15T10:00:00Z"
    meta = yt.build_metadata("Sample caption\n\n#systemdesign", publish_at=scheduled_time)
    assert meta["status"]["privacyStatus"] == "private"
    assert meta["status"]["publishAt"] == scheduled_time


def test_warn_if_private_only_logs_when_private(caplog):
    with caplog.at_level(logging.WARNING, logger="codexone.publish_youtube"):
        yt._warn_if_private("public")
    assert not any("YT_PRIVACY=private" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="codexone.publish_youtube"):
        yt._warn_if_private("unlisted")
    assert not any("YT_PRIVACY=private" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="codexone.publish_youtube"):
        yt._warn_if_private("private")
    assert any("YT_PRIVACY=private" in r.message for r in caplog.records)


def test_publish_reel_does_not_warn_when_scheduled(monkeypatch, caplog):
    monkeypatch.setattr(yt, "credentials", lambda: None)
    monkeypatch.setattr(yt, "load_brand", lambda: {"cta": ""})
    with caplog.at_level(logging.WARNING, logger="codexone.publish_youtube"):
        yt.publish_reel("local.mp4", "Caching explained\n\n#systemdesign", dry_run=True,
                        publish_at="2026-11-15T10:00:00Z")
    assert not any("YT_PRIVACY=private" in r.message for r in caplog.records)


def test_config_schema_contains_yt_privacy():
    assert "YT_PRIVACY" in config_schema.STORE_NAMES
    assert "YT_PRIVACY" in config_schema.PER_USER_FIELD_NAMES
    field = config_schema.FIELDS_BY_NAME["YT_PRIVACY"]
    assert field.name == "YT_PRIVACY"
    assert field.integration == "youtube"
    assert field.label == "Upload privacy"
    assert field.secret is False
    assert field.required is False
    assert field.shape == "public"
    assert field.choices == ("public", "unlisted", "private")
    assert field.per_user is True
