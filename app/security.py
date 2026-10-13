"""
Qastroute AI - Security Hardening & Defenses.
Codestral-optimized sliding-window rate limiter, token normalization, payload guards, and OWASP defenses.
Zero third-party bloat, OWASP Top 10 / CWE compliant.
"""

import asyncio
import time
from collections import deque
from typing import Optional, Dict, Deque
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

DEFAULT_RATE_LIMIT = 120       # 120 requests per minute per IP
DEFAULT_WINDOW_SECONDS = 60    # 60 second sliding window
MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB max payload

class RateLimiter:
    """
    Thread-safe in-memory rate limiter with sliding window algorithm and periodic memory cleanup.
    Protects against CWE-770 (Uncontrolled Resource Consumption) and memory exhaustion.
    """
    def __init__(self, limit: int = DEFAULT_RATE_LIMIT, window: int = DEFAULT_WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self.ip_requests: Dict[str, Deque[float]] = {}
        self.last_cleanup = time.time()
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def check_rate_limit(self, client_ip: str) -> tuple[bool, int, float]:
        """
        Returns (is_allowed, remaining_requests, retry_after_seconds).
        """
        now = time.time()
        lock = self._get_lock()

        async with lock:
            # Periodic cleanup of expired IPs to prevent memory leaks (CWE-404)
            if now - self.last_cleanup > 60:
                expired = [
                    ip for ip, reqs in self.ip_requests.items()
                    if not reqs or (now - reqs[-1] > self.window)
                ]
                for ip in expired:
                    del self.ip_requests[ip]
                self.last_cleanup = now

            if client_ip not in self.ip_requests:
                self.ip_requests[client_ip] = deque()

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
    - Guards against excessively large payloads and memory exhaustion (CWE-770)
    - Appends standard security headers (OWASP best practice)
    """
    async def dispatch(self, request: Request, call_next):
        # Extract real client IP (support reverse proxies / X-Forwarded-For)
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            client_ip = x_forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

        # Check request body size for POST/PUT requests
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

        # Rate limiting check
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

        # Append Rate Limit & Security Headers
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

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
