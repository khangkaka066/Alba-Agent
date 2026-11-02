from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app.billing.license import verify_license
from app.billing.plans import Plan, limits_for_plan, plan_limits
from app.billing.router import _payment_fields, _verify_polar, _verify_stripe, _verify_vietqr
from scripts.issue_enterprise_license import issue_license


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def test_default_subscription_limits_and_json_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_BILLING_PLAN_LIMITS_JSON", raising=False)
    assert limits_for_plan("FREE").max_persistent_bots == 3
    assert limits_for_plan("ENTERPRISE").max_monthly_cost_usd is None
    monkeypatch.setenv("NEXUS_BILLING_PLAN_LIMITS_JSON", '{"FREE":{"max_persistent_bots":2,"max_monthly_cost_usd":"3.50"}}')
    limits = plan_limits()[Plan.FREE]
    assert limits.max_persistent_bots == 2
    assert str(limits.max_monthly_cost_usd) == "3.50"
    monkeypatch.setenv("NEXUS_BILLING_PLAN_LIMITS_JSON", '{"FREE":{"unexpected":10}}')
    with pytest.raises(RuntimeError):
        plan_limits()


def test_offline_ed25519_license_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setenv("NEXUS_LICENSE_PUBLIC_KEY", base64.b64encode(public).decode())
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "EdDSA", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({
        "iss": "nexus-license", "aud": "nexus-enterprise", "sub": "acme",
        "iat": now - 1, "nbf": now - 1, "exp": now + 600,
        "features": ["multi_workspace", "sso", "audit_logs"],
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    token = f"{header}.{payload}.{_b64url(private.sign(signing_input))}"
    license_data = verify_license(token, now=now)
    assert license_data.subject == "acme"
    assert license_data.features == frozenset({"multi_workspace", "sso", "audit_logs"})
    token_head, token_body, token_signature = token.split(".")
    corrupted_signature = bytearray(base64.urlsafe_b64decode(token_signature + "=" * (-len(token_signature) % 4)))
    corrupted_signature[0] ^= 1
    corrupted_token = f"{token_head}.{token_body}.{_b64url(bytes(corrupted_signature))}"
    with pytest.raises(ValueError, match="verification failed"):
        verify_license(corrupted_token, now=now)


def test_offline_license_issuer_and_verifier_interoperate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "issuer.pem"
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setenv("NEXUS_LICENSE_PUBLIC_KEY", base64.b64encode(public).decode())
    token = issue_license(private_path, "customer", 30, {"audit_logs"}, None)
    assert verify_license(token).features == frozenset({"audit_logs"})


def test_payment_webhook_signature_verifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b'{"id":"evt_test"}'
    timestamp = str(int(time.time()))
    stripe_secret = "whsec_stripe_local_test_secret"
    monkeypatch.setenv("NEXUS_STRIPE_WEBHOOK_SECRET", stripe_secret)
    stripe_signature = hmac.new(stripe_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    _verify_stripe(raw, f"t={timestamp},v1={stripe_signature}")
    with pytest.raises(HTTPException):
        _verify_stripe(raw, f"t={timestamp},v1=invalid")

    polar_secret = "polar_local_test_webhook_secret"
    monkeypatch.setenv("NEXUS_POLAR_WEBHOOK_SECRET", polar_secret)
    event_id = "msg_test"
    message = f"{event_id}.{timestamp}.".encode() + raw
    polar_signature = base64.b64encode(hmac.new(polar_secret.encode(), message, hashlib.sha256).digest()).decode()
    _verify_polar(raw, {"webhook-id": event_id, "webhook-timestamp": timestamp, "webhook-signature": f"v1,{polar_signature}"})

    vietqr_secret = "vietqr_local_test_webhook_secret"
    monkeypatch.setenv("NEXUS_VIETQR_WEBHOOK_SECRET", vietqr_secret)
    from starlette.requests import Request

    headers = [(b"x-nexus-timestamp", timestamp.encode()), (
        b"x-nexus-signature", ("sha256=" + hmac.new(vietqr_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()).encode(),
    )]
    request = Request({"type": "http", "headers": headers, "method": "POST", "path": "/", "query_string": b"", "server": ("test", 80), "scheme": "http"})
    _verify_vietqr(raw, request)


def test_payment_events_map_products_and_only_top_up_paid_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, workspace_id = "74c3ec65-638a-4a9f-a439-4c710d2d9535", "34c3ec65-638a-4a9f-a439-4c710d2d9535"
    monkeypatch.setenv("NEXUS_BILLING_PRODUCT_PLANS_JSON", '{"stripe":{"price_pro":"PRO"}}')
    monkeypatch.setenv("NEXUS_BILLING_PRODUCT_CREDITS_JSON", '{"stripe":{"price_credit":"12.5"}}')
    base = {
        "id": "evt_subscription", "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_1", "status": "active", "current_period_end": 1900000000,
            "items": {"data": [{"price": {"id": "price_pro"}}]},
            "metadata": {"tenant_id": tenant_id, "workspace_id": workspace_id},
        }},
    }
    fields = _payment_fields(base, "stripe")
    assert fields[4] is Plan.PRO
    assert fields[5] == 0
    cancelled = json.loads(json.dumps(base))
    cancelled["type"] = "customer.subscription.deleted"
    assert _payment_fields(cancelled, "stripe")[4] is Plan.FREE
    paid_credit = json.loads(json.dumps(base))
    paid_credit["id"] = "evt_credit"
    paid_credit["type"] = "payment_intent.succeeded"
    paid_credit["data"]["object"]["product_id"] = "price_credit"
    assert _payment_fields(paid_credit, "stripe")[5] == Decimal("12.5")
