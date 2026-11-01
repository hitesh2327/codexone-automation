"""Tests for Cloudflare edge & CDN response caching and security headers."""
from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import api.app.main as main_mod


def test_api_multi_cdn_zero_store_headers(client):
    r = client.get("/api/public/brand")
    assert r.status_code == 200
    assert "no-store" in r.headers.get("Cache-Control", "")
    assert r.headers.get("CDN-Cache-Control") == "no-store"
    assert r.headers.get("Cloudflare-CDN-Cache-Control") == "no-store"
    assert r.headers.get("Surrogate-Control") == "no-store"
    assert r.headers.get("Pragma") == "no-cache"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_spa_and_assets_cache_headers(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dist_dir = Path(tmp_dir)
        assets_dir = dist_dir / "assets"
        assets_dir.mkdir(parents=True)

        (dist_dir / "index.html").write_text("<!DOCTYPE html><html><body>SPA</body></html>")
        (assets_dir / "app-chunk123.js").write_text("console.log('chunk');")
        (dist_dir / "favicon.ico").write_text("fake_icon")

        monkeypatch.setattr(main_mod, "WEB_DIST", dist_dir)
        app = main_mod.create_app()
        test_client = TestClient(app)

        # 1. SPA fallback index.html: must be zero-cache to avoid stale chunk mismatches
        r_index = test_client.get("/")
        assert r_index.status_code == 200
        assert "no-store" in r_index.headers.get("Cache-Control", "")
        assert "no-cache" in r_index.headers.get("Cache-Control", "")
        assert r_index.headers.get("Pragma") == "no-cache"

        # 2. SPA client-side route fallback to index.html
        r_route = test_client.get("/dashboard/posts")
        assert r_route.status_code == 200
        assert "no-store" in r_route.headers.get("Cache-Control", "")

        # 3. Hashed static asset: must be immutable 1-year cache
        r_asset = test_client.get("/assets/app-chunk123.js")
        assert r_asset.status_code == 200
        assert r_asset.headers.get("Cache-Control") == "public, max-age=31536000, immutable"

        # 4. Root static asset: must be revalidated / 1-hour cache
        r_static = test_client.get("/favicon.ico")
        assert r_static.status_code == 200
        assert r_static.headers.get("Cache-Control") == "public, max-age=3600, must-revalidate"
