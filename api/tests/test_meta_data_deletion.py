"""Tests for MNT-503: Meta Data Deletion callback & status verification."""
import base64
import hashlib
import hmac
import json
import pytest

from api.app.routes.webhooks import parse_signed_request


def make_signed_request(payload: dict, secret: str) -> str:
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_sig = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{encoded_sig}.{encoded_payload}"


def test_parse_signed_request_valid():
    secret = "test_meta_app_secret_123"
    payload = {"user_id": "17841400998877", "algorithm": "HMAC-SHA256"}
    signed_req = make_signed_request(payload, secret)
    
    parsed = parse_signed_request(signed_req, secret)
    assert parsed is not None
    assert parsed["user_id"] == "17841400998877"


def test_parse_signed_request_invalid_signature():
    secret = "test_meta_app_secret_123"
    wrong_secret = "attacker_secret_456"
    payload = {"user_id": "17841400998877", "algorithm": "HMAC-SHA256"}
    signed_req = make_signed_request(payload, secret)
    
    with pytest.raises(ValueError, match="Signature mismatch"):
        parse_signed_request(signed_req, wrong_secret)


def test_parse_signed_request_tampered_payload():
    secret = "test_meta_app_secret_123"
    payload = {"user_id": "17841400998877", "algorithm": "HMAC-SHA256"}
    signed_req = make_signed_request(payload, secret)
    sig, _ = signed_req.split(".", 1)
    tampered_payload = base64.urlsafe_b64encode(json.dumps({"user_id": "hacked"}).encode()).decode().rstrip("=")
    
    with pytest.raises(ValueError):
        parse_signed_request(f"{sig}.{tampered_payload}", secret)
