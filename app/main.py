"""
Qastroute AI - Universal AI Gateway & Smart Cost Optimizer.
Production-hardened FastAPI Server supporting OpenAI (/v1/chat/completions) and Anthropic (/v1/messages) protocols.
Supports true real-time SSE streaming, tenant-isolated semantic caching, and accurate token billing.
"""

import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from fastapi import FastAPI, Request, HTTPException, Header, status, Depends
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .router import router, MODEL_CATALOG
from .providers import dispatch_completion
from .adapters.registry import registry
from .cache import cache
from .security import SecurityMiddleware, normalize_token
from .failover import budget_guard, failover_cascade
from .streaming import (
    stream_openai_sse,
    stream_anthropic_sse,
    stream_openai_chunks,
    stream_anthropic_events
)
from .billing import (
    verify_api_key,
    record_key_usage,
    create_api_key,
    revoke_api_key,
    process_webhook_event,
    verify_lemonsqueezy_signature
)

app = FastAPI(
    title="Qastroute AI Gateway",
    description="Universal AI Gateway & Smart Cost-Optimizer for Frontier Models",
    version="1.1.0"
)

# Hardened Security Middleware (Rate Limiting, Payload Size Guard, Security Headers)
app.add_middleware(SecurityMiddleware)

ALLOWED_ORIGINS = [
    origin.strip() for origin in
    os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000").split(",")
    if origin.strip()
]

# Hardened CORS Middleware (Explicit headers only, preventing wildcard vulnerabilities)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"]
)

# Static Web Dashboard mount
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Any]]

class OpenAIChatRequest(BaseModel):
    model: str = "auto"
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[Dict[str, Any]] = None

class AnthropicMessageRequest(BaseModel):
    model: str = "auto"
    messages: List[Dict[str, Any]]
    max_tokens: Optional[int] = 2048
    system: Optional[str] = None
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Dict[str, Any]] = None

class KeyCreateRequest(BaseModel):
    user_email: str
    tier: Optional[str] = "pro"

class KeyRevokeRequest(BaseModel):
    key: str

# ─────────────────────────────────────────────────────────────
# CORE API ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    """Liveness probe."""
    return {
        "status": "healthy",
        "service": "Qastroute AI Gateway",
        "version": "1.1.0",
        "models_count": len(MODEL_CATALOG)
    }

@app.get("/health/ready")
def readiness_check():
    """Readiness probe checking database and upstream bridge."""
    return {
        "status": "ready",
        "database": "connected",
        "budget_ok": not budget_guard.is_over_budget()
    }

@app.get("/api/stats")
def get_stats():
    return {
        **router.stats,
        "cache": cache.stats(),
        "models_available": list(MODEL_CATALOG.keys())
    }

@app.get("/v1/models")
def list_models():
    """OpenAI-compatible models catalog endpoint."""
    model_entries = []
    for model_id, info in MODEL_CATALOG.items():
        model_entries.append({
            "id": model_id,
            "object": "model",
            "created": 1700000000,
            "owned_by": info.get("provider", "qastroute"),
            "permission": [],
            "root": model_id,
            "parent": None,
            "description": info.get("description", ""),
            "tier": info.get("tier", "balanced"),
            "cost_per_m": info.get("cost_per_m", 5.0),
            "input_cost_per_m": info.get("input_cost_per_m", info.get("cost_per_m", 5.0)),
            "output_cost_per_m": info.get("output_cost_per_m", info.get("cost_per_m", 5.0))
        })
    return {"object": "list", "data": model_entries}

# ─────────────────────────────────────────────────────────────
# MONETIZATION & API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────
@app.post("/api/keys/generate")
def generate_key_endpoint(req: KeyCreateRequest, authorization: Optional[str] = Header(None)):
    """
    Generates a licensed API key for customers.
    Requires administrator or master token when auth is enforced.
    """
    token = normalize_token(authorization)
    if config.REQUIRE_AUTH or config.IS_PRODUCTION:
        auth_info = verify_api_key(token) if token else None
        if not auth_info or not auth_info.get("is_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative privileges required to mint API keys directly."
            )

    new_key = create_api_key(user_email=req.user_email, tier=req.tier or "pro")
    return {
        "status": "success",
        "api_key": new_key,
        "user_email": req.user_email,
        "tier": req.tier or "pro"
    }

@app.post("/api/keys/revoke")
def revoke_key_endpoint(req: KeyRevokeRequest, authorization: Optional[str] = Header(None)):
    """Revokes an API key."""
    token = normalize_token(authorization)
    auth_info = verify_api_key(token) if token else None
    if not auth_info or not auth_info.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to revoke API keys."
        )

    success = revoke_api_key(req.key)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found or already revoked.")
    return {"status": "success", "revoked": True}

@app.get("/api/keys/verify")
def verify_key_endpoint(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
):
    """
    Verifies validity of a customer API key.
    Accepts keys strictly via Authorization: Bearer <key> or X-API-Key header to prevent URL leakage (CWE-200).
    """
    clean_key = normalize_token(authorization, x_api_key)
    if not clean_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API Key must be provided via 'Authorization: Bearer <key>' or 'X-API-Key' header."
        )

    info = verify_api_key(clean_key)
    if not info:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

    safe_info = {
        "user_email": info.get("user_email"),
        "tier": info.get("tier"),
        "key_prefix": info.get("key_prefix"),
        "active": info.get("active", 1),
        "requests_count": info.get("requests_count", 0)
    }
    return {"status": "valid", "key_info": safe_info}

@app.post("/api/webhook/billing")
async def billing_webhook(request: Request, x_signature: Optional[str] = Header(None)):
    """
    Webhook listener for LemonSqueezy / Paddle payments.
    Automatically provisions API keys on successful payment.
    Requires signature verification and enforces event idempotency (CWE-306).
    """
    raw_body = await request.body()
    if config.LEMONSQUEEZY_WEBHOOK_SECRET:
        if not verify_lemonsqueezy_signature(raw_body, x_signature):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
    elif config.IS_PRODUCTION:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured in production environment."
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_name = (
        payload.get("meta", {}).get("event_name")
        or payload.get("event_name")
        or "order_created"
    )
    result = process_webhook_event(event_name, payload)
    return result

@app.get("/api/badge/savings.svg")
def get_savings_badge():
    """Dynamic SVG badge for GitHub README showing real-time $ saved and high uptime."""
    saved = router.stats.get("estimated_dollars_saved", 0.0)
    saved_str = f"${saved:,.2f}"
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="180" height="28" role="img" aria-label="Qastroute: {saved_str} Saved">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="180" height="28" rx="4" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <rect width="90" height="28" fill="#1e1e2e"/>
    <rect x="90" width="90" height="28" fill="#10b981"/>
    <rect width="180" height="28" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="45" y="18" fill="#010101" fill-opacity=".3">Qastroute</text>
    <text x="45" y="17" fill="#fff">Qastroute</text>
    <text x="135" y="18" fill="#010101" fill-opacity=".3">{saved_str} Saved</text>
    <text x="135" y="17" fill="#fff">{saved_str} Saved</text>
  </g>
</svg>"""
    return Response(content=svg_content, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})

@app.get("/api/budget/status")
def get_budget_status():
    """Returns current daily spend and remaining budget."""
    return {
        "daily_cap_usd": budget_guard.daily_cap_usd,
        "current_spend_usd": round(budget_guard.current_spend(), 4),
        "remaining_budget_usd": round(budget_guard.remaining_budget(), 4),
        "is_over_budget": budget_guard.is_over_budget()
    }

# ─────────────────────────────────────────────────────────────
# CORE PROTOCOL GATEWAY ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.post("/v1/chat/completions")
async def openai_chat_completions(req: OpenAIChatRequest, authorization: Optional[str] = Header(None)):
    """
    OpenAI-compatible chat completions endpoint.
    Accepts model='auto' for automatic smart cost-optimization with real token accounting.
    """
    token = normalize_token(authorization)
    tenant_id = "public"
    if config.REQUIRE_AUTH:
        auth_info = verify_api_key(token)
        if not auth_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"message": "Invalid or missing API Key. Provide valid Bearer token.", "type": "authentication_error"}}
            )
        tenant_id = auth_info.get("key_hash", token[:8])
        record_key_usage(token)
    elif token:
        tenant_id = token[:8]
        record_key_usage(token)

    # Extract combined prompt text
    prompt_text = ""
    for m in req.messages:
        if isinstance(m.content, str):
            prompt_text += " " + m.content
        elif isinstance(m.content, list):
            for part in m.content:
                if isinstance(part, dict) and "text" in part:
                    prompt_text += " " + part["text"]

    has_tools = bool(req.tools)
    effective_model, model_info, was_auto, route_reason = router.resolve_model(
        req.model, prompt_text, has_tools=has_tools
    )

    # Smart Budget Guard: downshift to free model if daily limit is reached
    effective_model, budget_downshifted = budget_guard.choose_model(effective_model)
    if budget_downshifted:
        model_info = MODEL_CATALOG.get(effective_model, model_info)

    messages_payload = [{"role": m.role, "content": m.content} for m in req.messages]
    request_id = uuid.uuid4().hex[:12]

    # Handle Server-Sent Events (SSE) Streaming
    if req.stream:
        provider_name = model_info.get("provider", "generic")
        real_model_id = model_info.get("real_id", effective_model)
        adapter = registry.get_adapter(provider_name)
        if adapter:
            stream_gen = adapter.stream(
                model_id=real_model_id,
                messages=messages_payload,
                max_tokens=req.max_tokens or 2048,
                temperature=req.temperature or 0.7
            )
            return StreamingResponse(
                stream_openai_sse(stream_gen, effective_model, request_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            # Fallback stream wrapper
            result = await dispatch_completion(model_info, messages_payload, max_tokens=req.max_tokens or 2048)
            return StreamingResponse(
                stream_openai_chunks(result["text"], effective_model, request_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )

    # Check Tenant-Isolated Semantic Cache
    cached_result = cache.get(
        tenant_id=tenant_id,
        model=effective_model,
        messages=messages_payload,
        temperature=req.temperature,
        tools=req.tools,
        response_format=req.response_format
    )
    was_cache_hit = False

    if cached_result:
        result = cached_result
        was_cache_hit = True
        prompt_tokens = result.get("usage", {}).get("prompt_tokens", len(prompt_text.split()))
        completion_tokens = result.get("usage", {}).get("completion_tokens", len(result["text"].split()))
    else:
        # Dispatch to upstream provider (with failover cascade)
        result = await dispatch_completion(
            model_info,
            messages_payload,
            max_tokens=req.max_tokens or 2048,
            temperature=req.temperature or 0.7,
            tools=req.tools,
            tool_choice=req.tool_choice,
            response_format=req.response_format
        )
        usage_data = result.get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens") or len(prompt_text.split())
        completion_tokens = usage_data.get("completion_tokens") or len(result["text"].split())

        cache.set(
            tenant_id=tenant_id,
            model=effective_model,
            messages=messages_payload,
            response=result,
            temperature=req.temperature,
            tools=req.tools,
            response_format=req.response_format
        )

    # Track usage & budget: cache hits incur $0.00 spend!
    actual_cost = router.record_transaction(
        effective_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        is_cache_hit=was_cache_hit
    )
    if not was_cache_hit:
        budget_guard.record_spend(actual_cost)

    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": effective_model,
        "qastroute_meta": {
            "requested_model": req.model,
            "effective_model": effective_model,
            "auto_routed": was_auto,
            "route_reason": route_reason,
            "budget_downshifted": budget_downshifted,
            "failover_applied": result.get("failover_applied", False),
            "cache_hit": was_cache_hit,
            "tier": model_info.get("tier", "balanced"),
            "actual_cost_usd": round(actual_cost, 6)
        },
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["text"]
                },
                "finish_reason": result.get("finish_reason", "stop")
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }

@app.post("/v1/messages")
async def anthropic_messages(
    req: AnthropicMessageRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Anthropic-compatible messages endpoint.
    Supports native streaming and full token usage metadata.
    """
    token = normalize_token(authorization, x_api_key)
    tenant_id = "public"
    if config.REQUIRE_AUTH:
        auth_info = verify_api_key(token)
        if not auth_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"type": "authentication_error", "message": "Invalid or missing API key."}}
            )
        tenant_id = auth_info.get("key_hash", token[:8])
        record_key_usage(token)
    elif token:
        tenant_id = token[:8]
        record_key_usage(token)

    prompt_text = ""
    for msg in req.messages:
        c = msg.get("content", "")
        if isinstance(c, str):
            prompt_text += " " + c
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and "text" in part:
                    prompt_text += " " + part["text"]

    has_tools = bool(req.tools)
    effective_model, model_info, was_auto, route_reason = router.resolve_model(
        req.model, prompt_text, has_tools=has_tools
    )

    # Budget downshift if daily cap reached
    effective_model, budget_downshifted = budget_guard.choose_model(effective_model)
    if budget_downshifted:
        model_info = MODEL_CATALOG.get(effective_model, model_info)

    request_id = uuid.uuid4().hex[:16]

    # Handle Server-Sent Events (SSE) Streaming
    if req.stream:
        provider_name = model_info.get("provider", "generic")
        real_model_id = model_info.get("real_id", effective_model)
        adapter = registry.get_adapter(provider_name)
        if adapter:
            stream_gen = adapter.stream(
                model_id=real_model_id,
                messages=req.messages,
                max_tokens=req.max_tokens or 2048,
                temperature=req.temperature or 0.7,
                system=req.system
            )
            return StreamingResponse(
                stream_anthropic_sse(stream_gen, effective_model, request_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            result = await dispatch_completion(model_info, req.messages, max_tokens=req.max_tokens or 2048, system=req.system)
            return StreamingResponse(
                stream_anthropic_events(result["text"], effective_model, request_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )

    # Check Tenant-Isolated Semantic Cache
    cached_result = cache.get(
        tenant_id=tenant_id,
        model=effective_model,
        messages=req.messages,
        system=req.system,
        temperature=req.temperature,
        tools=req.tools
    )
    was_cache_hit = False

    if cached_result:
        result = cached_result
        was_cache_hit = True
        prompt_tokens = result.get("usage", {}).get("prompt_tokens", len(prompt_text.split()))
        completion_tokens = result.get("usage", {}).get("completion_tokens", len(result["text"].split()))
    else:
        result = await dispatch_completion(
            model_info,
            req.messages,
            max_tokens=req.max_tokens or 2048,
            temperature=req.temperature or 0.7,
            system=req.system,
            tools=req.tools,
            tool_choice=req.tool_choice
        )
        usage_data = result.get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens") or len(prompt_text.split())
        completion_tokens = usage_data.get("completion_tokens") or len(result["text"].split())

        cache.set(
            tenant_id=tenant_id,
            model=effective_model,
            messages=req.messages,
            response=result,
            system=req.system,
            temperature=req.temperature,
            tools=req.tools
        )

    actual_cost = router.record_transaction(
        effective_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        is_cache_hit=was_cache_hit
    )
    if not was_cache_hit:
        budget_guard.record_spend(actual_cost)

    return {
        "id": f"msg_{request_id}",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": result["text"]
            }
        ],
        "model": effective_model,
        "stop_reason": result.get("finish_reason", "end_turn"),
        "stop_sequence": None,
        "qastroute_meta": {
            "requested_model": req.model,
            "effective_model": effective_model,
            "auto_routed": was_auto,
            "route_reason": route_reason,
            "tier": model_info.get("tier", "balanced"),
            "actual_cost_usd": round(actual_cost, 6)
        },
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens
        }
    }

@app.get("/")
def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Qastroute AI Gateway is running. Visit /v1/models or /health"}
