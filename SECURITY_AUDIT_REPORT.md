# 🛡️ Cyber Security Audit Report

**Project Target:** `qastroute_ai`  
**Date:** 2026-10-13 21:07:49  
**Auditor Engine:** Cyber Security Auditor (Heuristic SAST + GPT120B)

---

## 📊 Executive Summary
* **Total Files Scanned:** 21
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
**Severity Rating:** **MEDIUM**  

The provided `main.py` is generally well‑structured and follows many best‑practice patterns (typed Pydantic models, explicit CORS whitelist, security‑focused middleware, header‑only API‑key handling).  
However, a few concrete weaknesses could be leveraged by an attacker or could lead to accidental data leakage if the application is deployed with default settings. None of the issues constitute a critical remote‑code‑execution flaw, but they merit remediation to meet OWASP Top 10 expectations and to harden the service for production use.

---

## [VULNERABILITY FINDINGS]

| # | Title (CWE‑ID) | Severity | Location (approx.) | Impact |
|---|----------------|----------|--------------------|--------|
| 1 | **CWE‑285 – Improper Authorization** – *API‑key generation may be unauthenticated in non‑production environments* | **MEDIUM** | `generate_key_endpoint` (lines 73‑87) | An attacker who can reach the endpoint while the service runs with `REQUIRE_AUTH=False` and `IS_PRODUCTION=False` can create privileged API keys without any credential, leading to unauthorized usage and potential billing abuse. |
| 2 | **CWE‑200 – Information Exposure** – *`/api/stats` returns full internal router statistics* | **LOW** | `get_stats` (lines 48‑55) | Internal metrics (e.g., cache hits, request counters) may reveal implementation details that help an attacker craft more precise attacks or enumerate usage patterns. |
| 3 | **CWE‑295 – Improper Certificate Validation / CWE‑306 – Missing Idempotency** – *Webhook handler does not enforce idempotency and trusts the JSON body before signature verification* | **MEDIUM** | `billing_webhook` (lines 99‑122) | A replayed webhook (or a crafted payload with a valid signature) could create duplicate API‑key provisions or trigger unwanted side‑effects, leading to over‑provisioning or billing manipulation. |
| 4 | **CWE‑20 – Improper Input Validation** – *`KeyCreateRequest.user_email` is accepted without validation* | **LOW** | `KeyCreateRequest` model (line 29) | If the email is later interpolated into SQL, logs, or other contexts, an attacker could inject malicious payloads (SQL, command, log injection). |
| 5 | **CWE‑285 – Missing Rate Limiting on Sensitive Endpoints** – *`/api/keys/*` endpoints rely solely on `SecurityMiddleware` (implementation not shown)* | **LOW** | All key‑management routes | If the custom middleware is mis‑configured or disabled, brute‑force attempts to guess or enumerate API keys become easier. |
| 6 | **CWE‑209 – Information Leakage Through Exception Details** – *`billing_webhook` returns raw exception messages for malformed JSON* | **LOW** | `billing_webhook` (lines 115‑119) | Stack‑trace or internal error strings could be exposed to an attacker, revealing implementation details. |
| 7 | **CWE‑400 – Uncontrolled Resource Consumption** – *Streaming endpoints not shown but the `max_tokens` default may allow extremely large payloads* | **LOW** | `OpenAIChatRequest` / `AnthropicMessageRequest` defaults (lines 19‑26) | An attacker could request very large `max_tokens` (if the client overrides defaults) leading to high compute cost and possible denial‑of‑service. |

> **Note:** No hard‑coded secrets, API keys, or private credentials were discovered in this file.

---

## [REMEDIATIONS]

Below are concrete, minimal‑impact patches that address the findings while preserving the existing public API.

### 1. Enforce strict admin authorization for API‑key creation regardless of environment  

```diff
@@
 @app.post("/api/keys/generate")
 def generate_key_endpoint(req: KeyCreateRequest, authorization: Optional[str] = Header(None)):
@@
-    token = normalize_token(authorization)
-    if config.REQUIRE_AUTH or config.IS_PRODUCTION:
-        auth_info = verify_api_key(token) if token else None
-        if not auth_info or not auth_info.get("is_admin"):
-            raise HTTPException(
-                status_code=status.HTTP_403_FORBIDDEN,
-                detail="Administrative privileges required to mint API keys directly."
-            )
+    # -----------------------------------------------------------------
+    # ALWAYS require an admin API key for key‑generation.
+    # In development environments we still enforce the check to avoid
+    # accidental exposure of privileged operations.
+    # -----------------------------------------------------------------
+    token = normalize_token(authorization)
+    auth_info = verify_api_key(token) if token else None
+    if not auth_info or not auth_info.get("is_admin"):
+        raise HTTPException(
+            status_code=status.HTTP_403_FORBIDDEN,
+            detail="Administrative privileges required to mint API keys directly."
+        )
```

### 2. Reduce information exposure in `/api/stats`  

```diff
@@
 @app.get("/api/stats")
 def get_stats():
-    return {
-        **router.stats,
-        "cache": cache.stats(),
-        "models_available": list(MODEL_CATALOG.keys())
-    }
+    # Expose only non‑sensitive operational metrics.
+    safe_stats = {
+        "total_requests": router.stats.get("total_requests", 0),
+        "cache_hits": cache.stats().get("hits", 0),
+        "cache_misses": cache.stats().get("misses", 0),
+        "models_available": list(MODEL_CATALOG.keys()),
+    }
+    return safe_stats
```

### 3. Add idempotency guard and early signature validation for webhooks  

```diff
@@
 async def billing_webhook(request: Request, x_signature: Optional[str] = Header(None)):
@@
-    raw_body = await request.body()
-    if config.LEMONSQUEEZY_WEBHOOK_SECRET:
-        if not verify_lemonsqueezy_signature(raw_body, x_signature):
-            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
-    elif config.IS_PRODUCTION:
-        raise HTTPException(
-            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
-            detail="Webhook secret not configured in production environment."
-        )
-
-    try:
-        payload = await request.json()
-    except Exception:
-        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
+    raw_body = await request.body()
+
+    # --------------------------------------------------------------
+    # 1️⃣ Verify signature *before* any payload parsing.
+    # --------------------------------------------------------------
+    if config.LEMONSQUEEZY_WEBHOOK_SECRET:
+        if not verify_lemonsqueezy_signature(raw_body, x_signature):
+            raise HTTPException(
+                status_code=status.HTTP_400_BAD_REQUEST,
+                detail="Invalid webhook signature"
+            )
+    elif config.IS_PRODUCTION:
+        raise HTTPException(
+            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
+            detail="Webhook secret not configured in production environment."
+        )
+
+    # --------------------------------------------------------------
+    # 2️⃣ Enforce idempotency – store processed event IDs in a fast
+    #    persistent cache (e.g., Redis) and reject duplicates.
+    # --------------------------------------------------------------
+    try:
+        payload = json.loads(raw_body)
+    except Exception:
+        raise HTTPException(
+            status_code=status.HTTP_400_BAD_REQUEST,
+            detail="Invalid JSON payload"
+        )
+
+    event_id = payload.get("event_id") or payload.get("id")
+    if event_id:
+        from .cache

---

### Assessment for `app\security.py`

### [SUMMARY]  
**Severity Rating:** HIGH  
**Risk Overview:** The middleware can be forced to read an unbounded request body for chunk‑ed transfers before enforcing the 5 MiB limit, enabling a denial‑of‑service via memory exhaustion. In addition, the handling of the `X‑Forwarded‑For` header can be abused to spoof client IPs when the immediate peer is a trusted proxy.

---

### [VULNERABILITY FINDINGS]

| # | Title | Severity | Location | Impact |
|---|-------|----------|----------|--------|
| 1 | **CWE‑770 – Uncontrolled Resource Consumption (Chunked Body Read)** | **HIGH** | `SecurityMiddleware.dispatch` – lines handling `transfer‑encoding: chunked` (≈ 45‑66) | An attacker can send a very large chunked request (e.g., several gigabytes). The code calls `await request.body()` **before** checking the size, causing the whole payload to be loaded into memory. This can exhaust RAM, crash the service, or trigger swapping, leading to a denial‑of‑service. |
| 2 | **CWE‑359 – Trusting HTTP Headers for Authentication/Authorization (IP Spoofing)** | **MEDIUM** | `SecurityMiddleware.dispatch` – client‑IP extraction block (≈ 24‑33) | If a trusted reverse‑proxy is in `config.TRUSTED_PROXIES`, the middleware blindly trusts the first value of the `X‑Forwarded‑For` header. An attacker controlling a downstream proxy (or a compromised trusted proxy) can inject any IP, bypassing rate‑limit enforcement and potentially evading other IP‑based controls. |
| 3 | **CWE‑749 – Weak Content‑Security‑Policy (unsafe‑inline)** | **LOW** | `SecurityMiddleware.dispatch` – CSP header construction (≈ 87‑92) | The CSP permits `'unsafe-inline'` for scripts and styles, reducing protection against XSS. While not a direct exploit in this component, it weakens overall application security. |

---

#### 1️⃣ CWE‑770 – Uncontrolled Resource Consumption (Chunked Body Read)

**Why it’s a problem**  
`await request.body()` reads the *entire* request stream into a single `bytes` object before the size check. For a chunked request with no `Content‑Length`, an attacker can stream arbitrarily large data, forcing the process to allocate memory proportional to the payload size.

**Fix – Stream‑wise size enforcement**  

```python
# ------------------- ORIGINAL (lines 45‑66) -------------------
elif request.headers.get("transfer-encoding") == "chunked":
    # For chunked requests without Content-Length header
    try:
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"error": {"message": "Payload too large. Maximum size is 5MB.", "type": "payload_too_large"}}
            )
        has_sent = False
        async def async_receive():
            nonlocal has_sent
            if not has_sent:
                has_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}
        request._receive = async_receive
    except Exception:
        pass
# ------------------------------------------------------------

# ------------------- PATCH (replace block) -------------------
elif request.headers.get("transfer-encoding", "").lower() == "chunked":
    # For chunked requests without Content‑Length header we read *incrementally*
    # and stop as soon as the configured limit is exceeded.
    try:
        received = 0
        chunks = []

        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": {
                            "message": "Payload too large. Maximum size is 5MB.",
                            "type": "payload_too_large"
                        }
                    },
                )
            chunks.append(chunk)

        # Re‑assemble the body for downstream handlers (only if within limit)
        body = b"".join(chunks)

        # Replace the receive callable so downstream code sees the already‑read body.
        async def _receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _receive
    except Exception:
        # If streaming fails we treat it as a bad request.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"message": "Unable to read request body.", "type": "bad_request"}},
        )
# ------------------------------------------------------------
```

*Key points of the patch*  
* Uses `await request.stream()` (Starlette’s async iterator) to read chunk‑by‑chunk.  
* Stops reading as soon as the cumulative size exceeds `MAX_BODY_BYTES`, returning **413** without ever allocating the full oversized payload.  
* Re‑assembles the body only when it is safely under the limit and injects a lightweight `_receive` callable for downstream handlers.

---

#### 2️⃣ CWE‑359 – Trusting `X‑Forwarded‑For` Header

**Why it’s a problem**  
When the immediate peer (`peer_host`) is listed in `config.TRUSTED_PROXIES`, the code trusts the **first** comma‑separated entry of `X‑Forwarded‑For`. An attacker who can influence that header (e.g., via a compromised proxy) can set any IP address, bypassing per‑IP rate limiting and other IP‑based defenses.

**Fix – Validate the header chain and discard untrusted entries**  

```python
# ------------------- ORIGINAL (lines 24‑33) -------------------
peer_host = request.client.host if request.client else "127.0

---

## 🛡️ General Security Recommendations
1. **Never commit secrets:** Store all API keys and credentials in `.env` files and add `.env` to `.gitignore`.
2. **Input Validation:** Restrict and sanitize all user-supplied inputs using Pydantic, Marshmallow, or strict regex schemas.
3. **Prepared Statements:** Always use parameterized SQL queries or ORM (SQLAlchemy, Prisma) to prevent SQL Injection.
4. **Subprocess Safety:** Never pass `shell=True` to `subprocess` with unsanitized user variables.
