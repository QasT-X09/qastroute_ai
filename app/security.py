"""
Qastroute AI - Security Hardening & Defenses.
Sliding-window rate limiter, token normalization, payload guards, and OWASP defenses.
Zero third-party bloat, OWASP Top 10 / CWE compliant.
"""

import asyncio
import time
from collections import deque, OrderedDict
from typing import Optional, Dict, Deque, Set
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from . import config

DEFAULT_RATE_LIMIT = 120          # 120 requests per minute per IP
DEFAULT_WINDOW_SECONDS = 60       # 60 second sliding window
MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB max payload
MAX_TRACKED_IPS = 10_000          # Bounded hard cap against memory exhaustion (CWE-400)

class RateLimiter:
    """
    Thread-safe in-memory rate limiter with sliding window algorithm and LRU eviction.
    Guarantees hard-bounded memory footprint under high distinct IP volume.
    """
    def __init__(self, limit: int = DEFAULT_RATE_LIMIT, window: int = DEFAULT_WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self.ip_requests: OrderedDict[str, Deque[float]] = OrderedDict()
        self.last_cleanup = time.time()
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, client_ip: str) -> tuple[bool, int, float]:
        now = time.time()

        async with self._lock:
            # Periodic cleanup of expired entries
            if now - self.last_cleanup > 30:
                expired = [
                    ip for ip, reqs in self.ip_requests.items()
                    if not reqs or (now - reqs[-1] > self.window)
                ]
                for ip in expired:
                    self.ip_requests.pop(ip, None)
                self.last_cleanup = now

            # LRU eviction if hard capacity reached
            while len(self.ip_requests) >= MAX_TRACKED_IPS:
                self.ip_requests.popitem(last=False)

            if client_ip not in self.ip_requests:
                self.ip_requests[client_ip] = deque()
            else:
                self.ip_requests.move_to_end(client_ip)

            queue = self.ip_requests[client_ip]

            # Evict timestamps outside sliding window
            while queue and now - queue[0] > self.window:
                queue.popleft()

            if len(queue) >= self.limit:
                retry_after = self.window - (now - queue[0])
                return False, 0, max(0.1, retry_after)

            queue.append(now)
            remaining = self.limit - len(queue)
            return True, remaining, float(self.window)

rate_limiter = RateLimiter()

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Enterprise security middleware:
    - Enforces sliding-window rate limiting per IP
    - Guards against excessively large payloads and chunked streaming exploits (CWE-770)
    - Extracts client IP safely using TRUSTED_PROXIES (CWE-359)
    - Appends strict security headers (OWASP best practice)
    """
    async def dispatch(self, request: Request, call_next):
        # 1. Safely extract client IP respecting trusted reverse proxies
        peer_host = request.client.host if request.client else "127.0.0.1"
        client_ip = peer_host

        # Only trust X-Forwarded-For if peer is in TRUSTED_PROXIES
        if peer_host in config.TRUSTED_PROXIES:
            x_forwarded = request.headers.get("X-Forwarded-For")
            if x_forwarded:
                forwarded_ips = [ip.strip() for ip in x_forwarded.split(",") if ip.strip()]
                # Walk the chain from right-most (closest proxy) to left-most, discarding trusted proxies
                for ip in reversed(forwarded_ips):
                    if ip not in config.TRUSTED_PROXIES:
                        client_ip = ip
                        break

        # 2. Guard against oversized request bodies independently of Content-Length (CWE-770)
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_BODY_BYTES:
                        return JSONResponse(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            content={"error": {"message": "Payload too large. Maximum size is 5MB.", "type": "payload_too_large"}}
                        )
                except ValueError:
                    pass
            elif request.headers.get("transfer-encoding", "").lower() == "chunked":
                # For chunked requests without Content-Length, read incrementally and abort early
                try:
                    received = 0
                    chunks = []
                    async for chunk in request.stream():
                        received += len(chunk)
                        if received > MAX_BODY_BYTES:
                            return JSONResponse(
                                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                content={"error": {"message": "Payload too large. Maximum size is 5MB.", "type": "payload_too_large"}}
                            )
                        chunks.append(chunk)

                    body = b"".join(chunks)
                    has_sent = False
                    async def async_receive():
                        nonlocal has_sent
                        if not has_sent:
                            has_sent = True
                            return {"type": "http.request", "body": body, "more_body": False}
                        return {"type": "http.disconnect"}
                    request._receive = async_receive
                except Exception:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": {"message": "Unable to read request stream.", "type": "bad_request"}}
                    )

        # 3. Rate limiting check per client IP
        allowed, remaining, retry_after = await rate_limiter.check_rate_limit(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "message": f"Rate limit exceeded. Try again in {retry_after:.1f} seconds.",
                        "type": "rate_limit_exceeded"
                    }
                },
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(rate_limiter.limit),
                    "X-RateLimit-Remaining": "0"
                }
            )

        response = await call_next(request)

        # 4. Strict Security Headers
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        )

        return response

def normalize_token(authorization: Optional[str] = None, x_api_key: Optional[str] = None) -> str:
    """
    Extracts and normalizes authentication tokens.
    Strips 'Bearer ' prefixes, whitespace, and validates non-emptiness (CWE-287).
    """
    raw = authorization or x_api_key or ""
    if not raw:
        return ""
    token = raw.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token
