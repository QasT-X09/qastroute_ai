"""
Qastroute AI - Test Suite.
Validates Smart Routing, Model Catalog, and OpenAI/Anthropic dual API protocol compatibility.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.router import router, MODEL_CATALOG

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Qastroute AI Gateway"
    assert data["models_count"] > 0

def test_models_catalog():
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    model_ids = [m["id"] for m in data["data"]]
    assert "claude-opus-5.5" in model_ids
    assert "claude-fable-5.1" in model_ids
    assert "gpt-6-astra" in model_ids
    assert "deepseek-r1" in model_ids
    assert "kimi-k3" in model_ids

def test_smart_router_classification():
    # Simple query should route to budget tier
    tier_simple, model_simple = router.classify_complexity("Hello, what is 2+2?")
    assert tier_simple == "budget"
    assert model_simple == "groq-gpt120b"

    # Code query should route to code tier
    tier_code, model_code = router.classify_complexity("def bubble_sort(arr): return sorted(arr)")
    assert tier_code == "code"
    assert model_code == "codestral-latest"

    # Deep reasoning should route to flagship tier
    tier_deep, model_deep = router.classify_complexity("Provide a formal mathematical proof for the theorem")
    assert tier_deep == "flagship"
    assert model_deep == "claude-fable-5.1"

    # Mega context should route to mega_context tier
    large_doc = "Data " * 10000
    tier_mega, model_mega = router.classify_complexity(large_doc)
    assert tier_mega == "mega_context"
    assert model_mega == "kimi-k3"

def test_openai_chat_completions_auto():
    payload = {
        "model": "auto",
        "messages": [
            {"role": "user", "content": "Format as JSON: name is Alice, age is 25"}
        ],
        "max_tokens": 100
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert "qastroute_meta" in data
    assert data["qastroute_meta"]["auto_routed"] is True

def test_anthropic_messages_endpoint():
    payload = {
        "model": "claude-fable-5.1",
        "messages": [
            {"role": "user", "content": "Write a short poem about stars."}
        ],
        "max_tokens": 100
    }
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["type"] == "message"
    assert data["model"] == "claude-fable-5.1"

def test_stats_tracking():
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "estimated_dollars_saved" in data
    assert "cache" in data

def test_cache_hit_on_repeat_request():
    payload = {
        "model": "deepseek-v3",
        "messages": [
            {"role": "user", "content": "What is the capital of France?"}
        ]
    }
    # First request: Cache miss
    res1 = client.post("/v1/chat/completions", json=payload)
    assert res1.status_code == 200
    assert res1.json()["qastroute_meta"]["cache_hit"] is False

    # Second request: Immediate Cache hit
    res2 = client.post("/v1/chat/completions", json=payload)
    assert res2.status_code == 200
    assert res2.json()["qastroute_meta"]["cache_hit"] is True
    assert res2.json()["choices"][0]["message"]["content"] == res1.json()["choices"][0]["message"]["content"]

def test_api_key_generation_and_verification():
    # Generate key
    res = client.post("/api/keys/generate", json={"user_email": "developer@qastroute.ai", "tier": "pro"})
    assert res.status_code == 200
    data = res.json()
    assert "api_key" in data
    assert data["api_key"].startswith("qr_live_")
    assert data["tier"] == "pro"

    # Verify key via header (CWE-200 compliance)
    res_verify = client.get("/api/keys/verify", headers={"Authorization": f"Bearer {data['api_key']}"})
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "valid"

def test_security_headers_and_rate_limit():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"

def test_billing_webhook_order_created():
    webhook_payload = {
        "meta": {
            "event_name": "order_created"
        },
        "data": {
            "id": "order_99812",
            "attributes": {
                "user_email": "founder@startup.io",
                "variant_name": "Qastroute Enterprise Plan"
            }
        }
    }
    response = client.post("/api/webhook/billing", json=webhook_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "key_issued"
    assert data["api_key"].startswith("qr_live_")
    assert data["tier"] == "enterprise"
    assert data["user_email"] == "founder@startup.io"

def test_openai_streaming_sse():
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": "Write a count from 1 to 5"}],
        "stream": True
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body_text = response.text
    assert "data: " in body_text
    assert "data: [DONE]" in body_text

def test_anthropic_streaming_sse():
    payload = {
        "model": "claude-fable-5.1",
        "messages": [{"role": "user", "content": "Hello streaming"}],
        "stream": True
    }
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body_text = response.text
    assert "event: message_start" in body_text
    assert "event: content_block_delta" in body_text

def test_savings_badge_svg():
    response = client.get("/api/badge/savings.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert "<svg" in response.text
    assert "Saved" in response.text

def test_budget_status_endpoint():
    response = client.get("/api/budget/status")
    assert response.status_code == 200
    data = response.json()
    assert "daily_cap_usd" in data
    assert "current_spend_usd" in data
    assert "remaining_budget_usd" in data
    assert "is_over_budget" in data

def test_failover_cascade_mapping():
    from app.failover import failover_cascade
    fallbacks = failover_cascade.get_fallbacks("claude-opus-5.5")
    assert len(fallbacks) > 0
    assert "gpt-6.1-sol-pro" in fallbacks



