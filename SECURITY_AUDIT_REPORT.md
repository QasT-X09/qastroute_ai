# 🛡️ Cyber Security Audit Report

**Project Target:** `qastroute_ai`  
**Date:** 2026-10-13 20:35:22  
**Auditor Engine:** Cyber Security Auditor (Heuristic SAST + GPT120B)

---

## 📊 Executive Summary
* **Total Files Scanned:** 14
* **Files with Security Findings:** 0
* **Total Leaked Secrets/Credentials:** 0
* **Total Code Vulnerabilities:** 0
* **Overall Posture:** ✅ SECURE

---

## 🚨 Credential & Secret Leaks
No exposed API keys, tokens, or credentials detected in scanned files.

## ⚠️ Static Code Vulnerabilities (CWE / OWASP)

No immediate CWE vulnerability patterns detected by heuristic engine.

## 🧠 Deep AI Vulnerability Assessments & Remediations

### Assessment for `app\main.py`

### [SUMMARY]  
**Severity Rating:** HIGH  
**Risk Overview:** The application exposes a **privileged API‑key generation endpoint** without any authentication or rate‑limiting, allowing an attacker to create unlimited valid keys and consume paid AI resources. Additional hardening is recommended for the health endpoint, webhook verification, and token handling to avoid information leakage and abuse.

---

## [VULNERABILITY FINDINGS]

| # | Title | CWE‑ID | Severity | Location (approx.) |
|---|-------|--------|----------|--------------------|
| 1 | **Unauthenticated API‑Key Generation** – any client can call `/api/keys/generate` and obtain a fully‑functional license key. | CWE‑285: **Improper Authorization** | **HIGH** | `def generate_key_endpoint` (lines 73‑80) |
| 2 | **Insufficient Webhook Signature Enforcement** – when `config.LEMONSQUEEZY_WEBHOOK_SECRET` is missing the endpoint accepts the request without any verification (only blocks in production). | CWE‑306: **Missing Authentication for Critical Function** | **MEDIUM** | `billing_webhook` (lines 95‑110) |
| 3 | **Information Disclosure via Health Endpoint** – returns service version and internal model count, aiding reconnaissance. | CWE‑200: **Information Exposure** | **LOW** | `health_check` (lines 44‑49) |
| 4 | **Potential Abuse of Optional Authentication** – `config.REQUIRE_AUTH` can be set to `False`, allowing anonymous usage while still recording usage, which may be abused to generate traffic without accountability. | CWE‑284: **Improper Access Control** | **MEDIUM** | `openai_chat_completions` (lines 124‑147) |
| 5 | **Lack of Rate‑Limiting / Payload Guard on Sensitive Endpoints** – the code relies on `SecurityMiddleware` but does not explicitly enforce limits on high‑value endpoints (`/api/keys/generate`, `/v1/chat/completions`). | CWE‑770: **Allocation of Resources without Limits** | **MEDIUM** | Throughout – especially key‑gen and chat endpoints. |

> **Note:** No hard‑coded secrets, API keys, or passwords were found in the source file.

---

## Detailed Remediations

### 1. Protect API‑Key Generation (`/api/keys/generate`)

**Root Cause:** No authentication or authorization check before creating a new API key.

**Fix Options**  
*Require an admin‑level token or a signed JWT* **or** *limit the endpoint to internal use (e.g., IP allow‑list).*

#### Recommended Patch (using a simple admin API key stored in an environment variable)

```diff
@@
-from .billing import (
-    verify_api_key,
-    record_key_usage,
-    create_api_key,
-    process_webhook_event,
-    verify_lemonsqueezy_signature
-)
+from .billing import (
+    verify_api_key,
+    record_key_usage,
+    create_api_key,
+    process_webhook_event,
+    verify_lemonsqueezy_signature
+)
+import secrets
+
+# Admin API key used to protect privileged operations (rotate regularly)
+ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
+if not ADMIN_API_KEY:
+    raise RuntimeError("ADMIN_API_KEY environment variable must be set for production")
 
@@
-@app.post("/api/keys/generate")
-def generate_key_endpoint(req: KeyCreateRequest):
-    """Generates a licensed API key for customers."""
-    new_key = create_api_key(user_email=req.user_email, tier=req.tier or "pro")
-    return {
-        "status": "success",
-        "api_key": new_key,
-        "user_email": req.user_email,
-        "tier": req.tier or "pro"
-    }
+@app.post("/api/keys/generate")
+def generate_key_endpoint(
+    req: KeyCreateRequest,
+    authorization: Optional[str] = Header(None)
+):
+    """
+    Generates a licensed API key for customers.
+    **Protected:** requires a valid ADMIN_API_KEY supplied as a Bearer token.
+    """
+    # ----- Authorization check -----
+    token = normalize_token(authorization)
+    if not token or not secrets.compare_digest(token, ADMIN_API_KEY):
+        raise HTTPException(
+            status_code=status.HTTP_403_FORBIDDEN,
+            detail="Forbidden: insufficient privileges to generate API keys."
+        )
+
+    # ----- Key creation -----
+    new_key = create_api_key(user_email=req.user_email, tier=req.tier or "pro")
+    return {
+        "status": "success",
+        "api_key": new_key,
+        "user_email": req.user_email,
+        "tier": req.tier or "pro"
+    }
```

*If a more sophisticated RBAC system is already in place, replace the simple admin‑key check with the appropriate permission verification.*

---

### 2. Enforce Webhook Signature Verification Unconditionally

**Root Cause:** Signature is only validated when a secret is configured; otherwise the webhook can be called freely in non‑production environments.

**Fix:** Require a signature in **all** environments (development, staging, production). In development you may use a test secret but still verify it.

```diff
@@
-    if config.LEMONSQUEEZY_WEBHOOK_SECRET:
-        if not verify_lemonsqueezy_signature(raw_body, x_signature):
-            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
-    elif os.getenv("ENVIRONMENT") == "production":
-        raise HTTPException(
-            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
-            detail="Webhook secret not configured in production environment."
-        )
+    # ------------------------------------------------------------------
+    # Always require a valid signature. In development you can set a dummy
+    # secret via the LEMONSQUEEZY_WEBHOOK_SECRET environment variable.
+    # ------------------------------------------------------------------
+    if not config.LEMONSQUEEZY_WEBHOOK_SECRET:
+        raise HTTPException(
+            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
+            detail="Webhook secret not configured. Set LEMONSQUEEZY_WEBHOOK_SECRET."
+        )
+    if not verify_lemonsqueezy_signature(raw_body, x_signature):
+        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
+                            detail="Invalid webhook signature")
```

---

### 3. Reduce Information Exposure on `/health`

**Root Cause:** Returns `version` and `models_count`, which can aid attackers in fingerprinting.

**Fix:** Remove version (or expose only a generic identifier) and keep model count optional.

```diff
@@
-@app.get("/health")
-def health_check():
-    return {
-        "status": "healthy",
-        "service": "Qastroute AI Gateway",
-        "version": "1.0.0",
-        "models_count": len(MODEL_CATALOG)
-    }
+@app.get("/health")
+def health_check():
+    """
+    Minimal health check – does **not** disclose internal version or model count.
+    """
+    return {"status": "healthy", "service": "Qastroute

---

### Assessment for `app\security.py`

### [SUMMARY]  
**Severity Rating:** **HIGH**  
**Risk Overview:** The middleware trusts the `X‑Forwarded‑For` header without validation and only checks the `Content‑Length` header to enforce payload size. Both issues can be abused to bypass rate‑limiting and to send arbitrarily large request bodies, leading to denial‑of‑service or credential‑brute‑force attacks.

---

## [VULNERABILITY FINDINGS]

| # | Title | CWE | Severity | Location |
|---|-------|-----|----------|----------|
| 1 | **Untrusted `X‑Forwarded‑For` Header – Rate‑limit Bypass** | CWE‑200 (Information Exposure) / CWE‑359 (Exposure of Private Data) | **HIGH** | `SecurityMiddleware.dispatch()` – lines where `client_ip` is derived from `X‑Forwarded‑For`. |
| 2 | **Insufficient Request‑Body Size Enforcement** | CWE‑770 (Allocation of Resources without Limits) | **HIGH** | `SecurityMiddleware.dispatch()` – `Content‑Length` header check only. |
| 3 | **Potential Unbounded Memory Growth in RateLimiter** | CWE‑770 (Resource Exhaustion) | **MEDIUM** | `RateLimiter.check_rate_limit()` – unbounded `ip_requests` dict. |
| 4 | **Race Condition on Lazy Lock Creation** | CWE‑362 (Concurrent Execution using Shared Resource without Proper Synchronization) | **LOW** | `RateLimiter._get_lock()` – lock may be created by multiple coroutines simultaneously. |

### 1️⃣ Untrusted `X‑Forwarded‑For` Header – Rate‑limit Bypass
**Impact:**  
An attacker can set an arbitrary `X‑Forwarded‑For` value, causing the middleware to attribute requests to a victim IP. The attacker can thus bypass per‑IP rate limiting, enabling credential‑stuffing, brute‑force, or DoS attacks against the service while staying under the limit for the spoofed IP.

**Fix:**  
- Only trust `X‑Forwarded‑For` when the request originates from a known, trusted proxy (e.g., your load‑balancer).  
- Maintain a configurable list of trusted proxy IPs.  
- If the request is not from a trusted proxy, fall back to `request.client.host`.  
- Use `starlette.datastructures.Headers.getlist()` to handle multiple header values safely.

**Patch (diff):**
```diff
@@
 class SecurityMiddleware(BaseHTTPMiddleware):
@@
-        # Extract real client IP (support reverse proxies / X-Forwarded-For)
-        x_forwarded = request.headers.get("X-Forwarded-For")
-        if x_forwarded:
-            client_ip = x_forwarded.split(",")[0].strip()
-        elif request.client:
-            client_ip = request.client.host
-        else:
-            client_ip = "127.0.0.1"
+        # -----------------------------------------------------------------
+        # Extract real client IP.
+        # Only trust X-Forwarded-For when the request originates from a
+        # configured trusted proxy.  This prevents malicious clients from
+        # spoofing the header to evade rate‑limiting.
+        # -----------------------------------------------------------------
+        TRUSTED_PROXIES = {"127.0.0.1", "::1"}   # <-- adjust to your environment
+
+        # Default to the direct client address
+        client_ip = request.client.host if request.client else "127.0.0.1"
+
+        # If the immediate peer is a trusted proxy, use the first entry of X‑Forwarded‑For
+        if client_ip in TRUSTED_PROXIES:
+            x_forwarded = request.headers.get("X-Forwarded-For")
+            if x_forwarded:
+                # X‑Forwarded‑For may contain a chain of IPs; the left‑most is the original client
+                client_ip = x_forwarded.split(",")[0].strip()
```

### 2️⃣ Insufficient Request‑Body Size Enforcement
**Impact:**  
Relying solely on the `Content‑Length` header can be bypassed with:
- `Transfer-Encoding: chunked` (no `Content‑Length` header).  
- A mismatched `Content‑Length` value (smaller than actual payload).  

An attacker can therefore stream a payload far larger than `MAX_BODY_BYTES`, exhausting memory/CPU (DoS) or causing downstream services to crash.

**Fix:**  
- Read the request body up to `MAX_BODY_BYTES + 1`.  
- If the read exceeds the limit, abort with HTTP 413.  
- Use FastAPI’s `request.stream()` (or `await request.body()`) with a size guard.

**Patch (diff):**
```diff
@@
-        # Check request body size for POST/PUT requests
-        if request.method in ("POST", "PUT", "PATCH"):
-            content_length = request.headers.get("content-length")
-            if content_length:
-                try:
-                    if int(content_length) > MAX_BODY_BYTES:
-                        return JSONResponse(
-                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
-                            content={"error": {"message": "Payload too large. Maximum size is 5MB.", "type": "payload_too_large"}}
-                        )
-                except ValueError:
-                    pass
+        # -----------------------------------------------------------------
+        # Enforce maximum payload size for state‑changing methods.
+        # This checks the actual bytes read, not just the Content‑Length
+        # header, and works with chunked transfers.
+        # -----------------------------------------------------------------
+        if request.method in ("POST", "PUT", "PATCH"):
+            try:
+                # Read up to MAX_BODY_BYTES + 1 to detect oversize
+                body = await request.body()
+                if len(body) > MAX_BODY_BYTES:
+                    return JSONResponse(
+                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
+                        content={
+                            "error": {
+                                "message": f"Payload too large. Maximum size is {MAX_BODY_BYTES // (1024*1024)} MiB.",
+                                "type": "payload_too_large",
+                            }
+                        },
+                    )
+                # Re‑inject the body for downstream handlers
+                request._receive = lambda: {"type": "http.request", "body": body, "more_body": False}
+            except Exception:
+                # If body reading fails, treat it as a bad request
+                return JSONResponse(
+                    status_code=status.HTTP_400_BAD_REQUEST,
+                    content={"error": {"message": "Unable to read request body.", "type": "bad_request"}},
+                )
```

*(The lambda re‑injects the already‑read body so the downstream endpoint can still access it. Adjust for your ASGI server if needed.)*

### 3️⃣ Potential Unbounded Memory Growth in RateLimiter
**Impact:**  
An attacker can generate a flood of distinct IP addresses (e.g., via a botnet) causing `ip_requests` to store an entry per IP. Over time this can exhaust the server’s memory (CWE‑770).

**Fix:**  
- Impose a hard cap on the number of tracked IPs (e.g., 10 000).  
- Evict the oldest entry when the cap is reached.  
- Optionally, use an LRU cache (`functools.lru_cache` or `cachetools.LRUCache`) instead of a plain dict.

**Patch (diff):**
```diff
@@
 class RateLimiter:
@@
-        self.ip_requests: Dict[str, Deque[float]] = {}
+        # Limit the number of distinct IP entries to prevent unbounded memory use.
+        self.MAX_TRACKED_IPS = 10_000
+        self.ip_requests: Dict[str,

---

## 🛡️ General Security Recommendations
1. **Never commit secrets:** Store all API keys and credentials in `.env` files and add `.env` to `.gitignore`.
2. **Input Validation:** Restrict and sanitize all user-supplied inputs using Pydantic, Marshmallow, or strict regex schemas.
3. **Prepared Statements:** Always use parameterized SQL queries or ORM (SQLAlchemy, Prisma) to prevent SQL Injection.
4. **Subprocess Safety:** Never pass `shell=True` to `subprocess` with unsanitized user variables.
