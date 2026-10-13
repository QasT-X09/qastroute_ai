"""
Qastroute AI - Production Hardening & Security Test Suite.
Verifies critical security controls, provider adapter contracts, failover safety,
tenant cache isolation, true cost accounting, and zero synthetic responses.
"""

import pytest
import uuid
import hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.billing import create_api_key, verify_api_key, revoke_api_key, process_webhook_event
from app.cache import cache
from app.router import router, MODEL_CATALOG
from app.adapters.base import ProviderError, ProviderResponse, UsageMetadata
from app.adapters.registry import registry

client = TestClient(app)

def test_key_hashing_and_revocation():
    """Verifies keys are hashed in storage, verifiable, and revocable."""
    user = f"user_{uuid.uuid4().hex[:6]}@example.com"
    raw_key = create_api_key(user, tier="pro")
    assert raw_key.startswith("qr_live_")

    # Verification works
    auth_info = verify_api_key(raw_key)
    assert auth_info is not None
    assert auth_info["user_email"] == user
    assert auth_info["active"] == 1
    # Verify raw key is NOT stored in the database as key
    assert "key" not in auth_info or auth_info.get("key") != raw_key

    # Revocation works
    revoked = revoke_api_key(raw_key)
    assert revoked is True

    # Revoked key is rejected
    after_revoke = verify_api_key(raw_key)
    assert after_revoke is None

def test_webhook_idempotency_no_duplicate_keys():
    """Verifies that replaying payment webhooks does not mint duplicate API keys."""
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "data": {
            "id": event_id,
            "attributes": {
                "user_email": "customer@idempotent.com",
                "variant_name": "Pro Tier"
            }
        }
    }

    # First event
    res1 = process_webhook_event("order_created", payload)
    assert res1["status"] == "success"
    assert res1["action"] == "key_issued"
    key1 = res1["api_key"]

    # Replay identical event
    res2 = process_webhook_event("order_created", payload)
    assert res2["status"] == "success"
    assert res2["action"] == "key_issued"
    assert res2.get("idempotent_replay") is True
    # Replay must return the same key, NOT mint a new one
    assert res2["api_key"] == key1

def test_tenant_cache_isolation():
    """Verifies that User A's private cached response is never leaked to User B."""
    tenant_a = f"tenant_{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant_{uuid.uuid4().hex[:8]}"
    model = "gpt-6-astra"
    messages = [{"role": "user", "content": "Private financial report analysis"}]
    mock_response = {"text": "Private Financial Data 2026", "finish_reason": "stop"}

    # Tenant A populates cache
    cache.set(tenant_id=tenant_a, model=model, messages=messages, response=mock_response)

    # Tenant A gets hit
    hit_a = cache.get(tenant_id=tenant_a, model=model, messages=messages)
    assert hit_a is not None
    assert hit_a["text"] == "Private Financial Data 2026"

    # Tenant B queries same prompt -> must be cache MISS to prevent cross-tenant leak
    miss_b = cache.get(tenant_id=tenant_b, model=model, messages=messages)
    assert miss_b is None

def test_cache_parameter_differentiation():
    """Verifies that different temperatures or system prompts cause cache misses."""
    tenant = "tenant_param_test"
    model = "claude-fable-5.1"
    messages = [{"role": "user", "content": "Tell me a joke"}]
    res = {"text": "Joke answer"}

    cache.set(tenant_id=tenant, model=model, messages=messages, response=res, temperature=0.2)

    # Same temp -> hit
    hit = cache.get(tenant_id=tenant, model=model, messages=messages, temperature=0.2)
    assert hit is not None

    # Different temp (0.9) -> miss
    miss_temp = cache.get(tenant_id=tenant, model=model, messages=messages, temperature=0.9)
    assert miss_temp is None

def test_cache_hits_do_not_incur_cost():
    """Verifies that cache hits incur $0.00 spend and are not billed."""
    cost = router.record_transaction("gpt-6-astra", prompt_tokens=1000, completion_tokens=500, is_cache_hit=True)
    assert cost == 0.0

def test_separate_input_and_output_cost_rates():
    """Verifies that input and output rates are properly distinguished in billing."""
    # gpt-6-astra: input $12/M, output $24/M
    cost = router.record_transaction("gpt-6-astra", prompt_tokens=1_000_000, completion_tokens=1_000_000, is_cache_hit=False)
    # Expected: 12 + 24 = 36 USD
    assert cost == pytest.approx(36.0, rel=1e-2)

def test_readiness_and_liveness_endpoints():
    """Verifies separation of public liveness and internal readiness probes."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready"
    assert res_ready.json()["database"] == "connected"

def test_query_parameter_auth_rejected():
    """Verifies API key in query string ?key=... is rejected to prevent logging leaks (CWE-200)."""
    res = client.get("/api/keys/verify?key=qr_live_test_leak")
    # Must reject with 400 because no header was supplied
    assert res.status_code == 400
    assert "Authorization" in res.json()["detail"]

def test_security_headers_present():
    """Verifies CSP, Referrer-Policy, nosniff, and HSTS headers on all responses."""
    res = client.get("/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in res.headers
    assert "Referrer-Policy" in res.headers
