"""
Qastroute AI - Universal AI Gateway & Smart Cost Optimizer.
FastAPI Server supporting both OpenAI (/v1/chat/completions) and Anthropic (/v1/messages) protocols.
"""

import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, Header, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .router import router, MODEL_CATALOG
from .providers import dispatch_completion
from .cache import cache
from .billing import (
    verify_api_key,
    record_key_usage,
    create_api_key,
    process_webhook_event,
    verify_lemonsqueezy_signature
)

app = FastAPI(
    title="Qastroute AI Gateway",
    description="Universal AI Gateway & Smart Cost-Optimizer for Claude Opus 5.5, GPT-6 Astra, Kimi K3, and DeepSeek",
    version="1.0.0"
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000").split(",")

# Secure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
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
    content: str

class OpenAIChatRequest(BaseModel):
    model: str = "auto"
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False

class AnthropicMessageRequest(BaseModel):
    model: str = "auto"
    messages: List[Dict[str, Any]]
    max_tokens: Optional[int] = 2048
    system: Optional[str] = None
    stream: Optional[bool] = False

class KeyCreateRequest(BaseModel):
    user_email: str
    tier: Optional[str] = "pro"

# ─────────────────────────────────────────────────────────────
# CORE API ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Qastroute AI Gateway",
        "version": "1.0.0",
        "models_count": len(MODEL_CATALOG)
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
            "cost_per_m": info.get("cost_per_m", 5.0)
        })
    return {"object": "list", "data": model_entries}

# ─────────────────────────────────────────────────────────────
# MONETIZATION & API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────
@app.post("/api/keys/generate")
def generate_key_endpoint(req: KeyCreateRequest):
    """Generates a licensed API key for customers."""
    new_key = create_api_key(user_email=req.user_email, tier=req.tier or "pro")
    return {
        "status": "success",
        "api_key": new_key,
        "user_email": req.user_email,
        "tier": req.tier or "pro"
    }

@app.get("/api/keys/verify")
def verify_key_endpoint(key: str):
    """Verifies validity of a customer API key."""
    info = verify_api_key(key)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return {"status": "valid", "key_info": info}

@app.post("/api/webhook/billing")
async def billing_webhook(request: Request, x_signature: Optional[str] = Header(None)):
    """
    Webhook listener for LemonSqueezy / Paddle payments.
    Automatically provisions API keys on successful payment.
    """
    raw_body = await request.body()
    if config.LEMONSQUEEZY_WEBHOOK_SECRET:
        if not verify_lemonsqueezy_signature(raw_body, x_signature):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_name = (
        payload.get("meta", {}).get("event_name")
        or payload.get("event_name")
        or "order_created"
    )
    result = process_webhook_event(event_name, payload)
    return result


@app.post("/v1/chat/completions")
async def openai_chat_completions(req: OpenAIChatRequest, authorization: Optional[str] = Header(None)):
    """
    OpenAI-compatible chat completions endpoint.
    Accepts model='auto' for automatic smart cost-optimization.
    """
    # Enforce API Key authentication if REQUIRE_AUTH is true
    token = authorization or ""
    if config.REQUIRE_AUTH:
        auth_info = verify_api_key(token)
        if not auth_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"message": "Invalid or missing API Key. Visit dashboard or subscribe to get an active key.", "type": "authentication_error"}}
            )
        record_key_usage(token)
    elif token:
        record_key_usage(token)

    # Extract combined prompt text for complexity classification
    prompt_text = " ".join([m.content for m in req.messages if isinstance(m.content, str)])
    
    # Smart routing
    effective_model, model_info, was_auto = router.resolve_model(req.model, prompt_text)
    
    messages_payload = [{"role": m.role, "content": m.content} for m in req.messages]
    
    # Check Semantic Cache for repeat query (0 latency, $0 cost)
    cached_result = cache.get(effective_model, messages_payload)
    was_cache_hit = False
    if cached_result:
        result = cached_result
        was_cache_hit = True
    else:
        # Dispatch to upstream provider
        result = await dispatch_completion(model_info, messages_payload, max_tokens=req.max_tokens or 2048)
        cache.set(effective_model, messages_payload, result)
    
    # Track metrics
    est_tokens = len(prompt_text.split()) + len(result["text"].split())
    router.record_transaction(effective_model, est_tokens)

    # Format into OpenAI Response Schema
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": effective_model,
        "qastroute_meta": {
            "requested_model": req.model,
            "effective_model": effective_model,
            "auto_routed": was_auto,
            "cache_hit": was_cache_hit,
            "tier": model_info.get("tier", "balanced")
        },
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["text"]
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(prompt_text.split()),
            "completion_tokens": len(result["text"].split()),
            "total_tokens": est_tokens
        }
    }

@app.post("/v1/messages")
async def anthropic_messages(req: AnthropicMessageRequest, x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    """
    Anthropic-compatible messages endpoint.
    Supports Claude Opus 5.5, Fable 5.1, and all universal models via Anthropic SDK.
    """
    token = x_api_key or authorization or ""
    if config.REQUIRE_AUTH:
        auth_info = verify_api_key(token)
        if not auth_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"type": "authentication_error", "message": "Invalid or missing API key."}}
            )
        record_key_usage(token)
    elif token:
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

    effective_model, model_info, was_auto = router.resolve_model(req.model, prompt_text)
    
    # Check Semantic Cache for repeat query
    cached_result = cache.get(effective_model, req.messages)
    was_cache_hit = False
    if cached_result:
        result = cached_result
        was_cache_hit = True
    else:
        result = await dispatch_completion(model_info, req.messages, max_tokens=req.max_tokens or 2048)
        cache.set(effective_model, req.messages, result)
    
    est_tokens = len(prompt_text.split()) + len(result["text"].split())
    router.record_transaction(effective_model, est_tokens)

    # Anthropic Messages Response Schema
    return {
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": result["text"]
            }
        ],
        "model": effective_model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "qastroute_meta": {
            "requested_model": req.model,
            "effective_model": effective_model,
            "auto_routed": was_auto,
            "tier": model_info.get("tier", "balanced")
        },
        "usage": {
            "input_tokens": len(prompt_text.split()),
            "output_tokens": len(result["text"].split())
        }
    }

@app.get("/")
def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Qastroute AI Gateway is running. Visit /v1/models or /health"}
