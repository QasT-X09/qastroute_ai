# 🛡️ Cyber Security Audit Report

**Project Target:** `qastroute_ai`  
**Date:** 2026-10-13 20:28:22  
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

The codebase is generally well‑structured, but there are **critical authorization flaws** that let unauthenticated callers create unlimited API keys and verify keys via URL query parameters. These issues can be exploited to obtain free credentials and bypass any intended billing or usage‑tracking controls, leading to complete service abuse. A few lower‑severity problems (unsafe token handling and optional query‑parameter key acceptance) further increase the attack surface.

---

## [VULNERABILITY FINDINGS]

| # | Title | CWE‑ID | Severity | Location (approx.) | Impact |
|---|-------|--------|----------|--------------------|--------|
| 1 | **Unauthenticated API‑Key Generation** – any client can call `/api/keys/generate` and receive a valid key. | CWE‑639 **Authorization Bypass Through User-Controlled Key** | **HIGH** | `generate_key_endpoint` (lines 78‑87) | An attacker can obtain unlimited API keys, bypass billing, and consume all downstream provider resources, leading to denial‑of‑service and monetary loss. |
| 2 | **API Key Leakage via URL Query Parameter** – endpoint `/api/keys/verify` also accepts `?key=` which can end up in logs, referrers, browser history, etc. | CWE‑200 **Information Exposure** / CWE‑538 **File/Info Exposure Through Debug/Log** | **MEDIUM** | `verify_key_endpoint` (lines 91‑111) | An attacker who can view server logs or network traffic can harvest valid keys, enabling unauthorized access. |
| 3 | **Improper Token Validation & Usage Recording** – `openai_chat_completions` calls `verify_api_key(token)` and `record_key_usage(token)` even when `token` may be `None`. This can raise unexpected exceptions or create empty‑key records. | CWE‑242 **Use of Inherently Dangerous Function** (unchecked value) | **LOW** | `openai_chat_completions` (lines 124‑147) | May cause crashes, denial‑of‑service, or polluted usage metrics, but does not directly lead to privilege escalation. |
| 4 | **Missing Rate‑Limiting on Key‑Generation Endpoint** – no throttling or CAPTCHA, enabling credential‑stuffing attacks. | CWE‑307 **Improper Restriction of Excessive Authentication Attempts** | **LOW** | Same as #1 | Allows automated bulk key creation, amplifying the impact of #1. |

*No hard‑coded secrets, passwords, or private keys were found in the supplied file.*

---

## Detailed Fixes  

### 1️⃣ Protect API‑Key Generation (HIGH)

**What to do**  
- Require a valid, privileged API key (e.g., an “admin” token) or an internal service‑to‑service secret before allowing key creation.  
- Add rate‑limiting (e.g., token‑bucket) to throttle calls.  
- Return **403 Forbidden** when the caller lacks the required privilege.

**Patch (diff)**  

```diff
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
+    **Requires** a privileged API token (e.g., an admin key) when `REQUIRE_AUTH` is enabled.
+    """
+    # ------------------------------------------------------------------
+    # 1️⃣ Enforce privileged authentication
+    # ------------------------------------------------------------------
+    token = normalize_token(authorization)
+    if config.REQUIRE_AUTH:
+        # Only admin‑level keys are allowed to create new keys.
+        auth_info = verify_api_key(token)
+        if not auth_info or not auth_info.get("is_admin"):
+            raise HTTPException(
+                status_code=status.HTTP_403_FORBIDDEN,
+                detail="Insufficient privileges to generate API keys."
+            )
+    else:
+        # In development mode we still block anonymous generation to avoid abuse.
+        raise HTTPException(
+            status_code=status.HTTP_403_FORBIDDEN,
+            detail="API key generation is disabled in non‑authenticated mode."
+        )
+
+    # ------------------------------------------------------------------
+    # 2️⃣ Rate‑limit creation (simple in‑memory token bucket)
+    # ------------------------------------------------------------------
+    if not budget_guard.allow_key_creation(token):
+        raise HTTPException(
+            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
+            detail="Key creation rate limit exceeded."
+        )
+
+    # ------------------------------------------------------------------
+    # 3️⃣ Actual key creation
+    # ------------------------------------------------------------------
+    new_key = create_api_key(user_email=req.user_email, tier=req.tier or "pro")
+    return {
+        "status": "success",
+        "api_key": new_key,
+        "user_email": req.user_email,
+        "tier": req.tier or "pro"
+    }
```

*Notes*  

- `auth_info.get("is_admin")` assumes the `verify_api_key` payload contains a flag indicating privileged accounts; modify as appropriate for your data model.  
- `budget_guard.allow_key_creation` is a new helper you can implement as a lightweight token‑bucket (e.g., `max 5 creations per minute per admin token`).  

---

### 2️⃣ Remove API‑Key from URL Query Parameter (MEDIUM)

**What to do**  
- Delete the `key` query‑parameter path.  
- Accept keys **only** via `Authorization: Bearer …` or `X‑API‑Key` headers.  
- Return **400** if none supplied.

**Patch (diff)**  

```diff
@@
-@app.get("/api/keys/verify")
-def verify_key_endpoint(
-    authorization: Optional[str] = Header(None),
-    x_api_key: Optional[str] = Header(None),
-    key: Optional[str] = None
-):
+@app.get("/api/keys/verify")
+def verify_key_endpoint(
+    authorization: Optional[str] = Header(None),
+    x_api_key: Optional[str] = Header(None)
+):
@@
-    clean_key = normalize_token(authorization, x_api_key) or (key or "").strip()
+    # Only header‑based keys are accepted. Query‑string keys are removed to avoid
+    # accidental logging or referrer leakage.
+

---

### Assessment for `app\security.py`

### [SUMMARY]  
**Severity Rating:** HIGH  

**Risk Overview:** The middleware trusts client‑supplied `X‑Forwarded‑For` headers for rate‑limiting and only checks the `Content‑Length` header to enforce payload size. Both can be spoof‑ed or omitted, allowing attackers to bypass rate limits and upload arbitrarily large bodies, leading to denial‑of‑service (DoS) and resource exhaustion. A minor race condition in lock creation could also let concurrent requests slip through the limiter.

---

### [VULNERABILITY FINDINGS]

| # | Title | Severity | Location | Impact | Fix |
|---|-------|----------|----------|--------|-----|
| 1 | **CWE‑359: Trusting Data from Untrusted Source – X‑Forwarded‑For Spoofing** | HIGH | `SecurityMiddleware.dispatch` (lines 55‑66) | An attacker can send a forged `X‑Forwarded‑For` header with any IP address, evading the per‑IP rate limiter. This enables unlimited requests from a single source, facilitating brute‑force, scraping, or DoS attacks. | Validate the header only when the request is known to have passed through a trusted reverse‑proxy, or ignore it entirely and rely on `request.client.host`. Example diff below. |
| 2 | **CWE‑400 / CWE‑770: Insufficient Payload Size Enforcement** | HIGH | `SecurityMiddleware.dispatch` (lines 70‑84) | The code checks only the `Content‑Length` header. A client can omit or falsify this header and stream a body (e.g., `Transfer‑Encoding: chunked`) larger than 5 MiB, exhausting memory or disk while the server processes the request. | Read the request body (or stream) up to `MAX_BODY_BYTES + 1` and abort with 413 if the limit is exceeded. Also enforce a hard limit on the body size even when `Content‑Length` is missing. |
| 3 | **CWE‑662: Improper Synchronization – Lazy Lock Initialization Race** | MEDIUM | `RateLimiter._get_lock` (lines 31‑38) | Multiple coroutines may simultaneously create separate `asyncio.Lock` objects, leaving the critical section unprotected. This can allow more than `limit` requests to be recorded, effectively bypassing the rate limiter under high concurrency. | Initialise the lock in `__init__` so it is created once, before any coroutine runs. |
| 4 | **CWE‑404: In‑Memory Data Structures – Unbounded Growth Across IPs** (Potential) | LOW | `RateLimiter.check_rate_limit` (lines 46‑58) | The `ip_requests` dictionary grows with every new IP address and is only cleaned when the last request for an IP is older than the window. An attacker can flood the service with many unique IPs (or spoofed IPs) to increase memory usage. | Add a hard cap on the number of tracked IPs (e.g., 10 000) and drop the oldest entries when the cap is exceeded. |
| 5 | **Missing Security Headers – Defense‑in‑Depth** | LOW | `SecurityMiddleware.dispatch` (lines 106‑112) | The middleware sets several hardening headers but omits `Content‑Security‑Policy`, `Referrer-Policy`, and disables the deprecated `X‑XSS‑Protection`. While not an immediate exploit, adding them reduces the attack surface. | Append recommended headers (CSP, Referrer‑Policy) after the response is created. |

---

#### Detailed Fixes  

##### 1. Trusted `X‑Forwarded‑For` handling  
```diff
@@
-        # Extract real client IP (support reverse proxies / X-Forwarded-For)
-        x_forwarded = request.headers.get("X-Forwarded-For")
-        if x_forwarded:
-            client_ip = x_forwarded.split(",")[0].strip()
-        elif request.client:
-            client_ip = request.client.host
-        else:
-            client_ip = "127.0.0.1"
+        # Extract real client IP.
+        # Only trust X-Forwarded-For when the request originated from a known
+        # trusted reverse‑proxy.  The list can be configured via an env‑var or
+        # settings object; here we illustrate a simple hard‑coded example.
+        TRUSTED_PROXIES = {"127.0.0.1", "10.0.0.1"}   # <-- adjust for your env
+
+        client_ip = None
+        if request.client and request.client.host in TRUSTED_PROXIES:
+            # The immediate peer is a trusted proxy – honour X-Forwarded-For.
+            x_forwarded = request.headers.get("X-Forwarded-For")
+            if x_forwarded:
+                client_ip = x_forwarded.split(",")[0].strip()
+        # Fallback to the socket peer IP when we cannot trust the header.
+        if not client_ip:
+            client_ip = request.client.host if request.client else "127.0.0.1"
```

##### 2. Robust payload size enforcement  
```diff
@@
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
+        if request.method in ("POST", "PUT", "PATCH"):
+            # Enforce a hard limit on the request body regardless of the
+            # presence or correctness of the Content‑Length header.
+            try:
+                # `receive` reads the raw ASGI messages; we stream them until the
+                # limit is exceeded.  FastAPI provides `request.body()` which
+                # reads the whole body, so we guard it with a size check.
+                body = await request.body()
+                if len(body) > MAX_BODY_BYTES:
+                    raise ValueError("payload too large")
+                # Replace the original request stream with the already‑read body
+                # so downstream handlers see the same data.
+                request._receive = lambda: {"type": "http.request", "body": body, "more_body": False}
+            except Exception:
+                return JSONResponse(
+                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
+                    content={"error": {"message": "Payload too large. Maximum size is

---

## 🛡️ General Security Recommendations
1. **Never commit secrets:** Store all API keys and credentials in `.env` files and add `.env` to `.gitignore`.
2. **Input Validation:** Restrict and sanitize all user-supplied inputs using Pydantic, Marshmallow, or strict regex schemas.
3. **Prepared Statements:** Always use parameterized SQL queries or ORM (SQLAlchemy, Prisma) to prevent SQL Injection.
4. **Subprocess Safety:** Never pass `shell=True` to `subprocess` with unsanitized user variables.
