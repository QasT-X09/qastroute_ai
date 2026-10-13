# 🛡️ Cyber Security Audit Report

**Project Target:** `qastroute_ai`  
**Date:** 2026-10-13 21:19:47  
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

**### [SUMMARY]**  
**Severity Rating:** **MEDIUM**  
**Risk Overview:** The application is generally well‑structured and uses a custom security middleware, but a few logical oversights could allow unauthorized creation of API keys and expose potentially sensitive internal information. No hard‑coded secrets were discovered.

---

## **[VULNERABILITY FINDINGS]**

| # | Title | CWE‑ID | Severity | Location |
|---|-------|--------|----------|----------|
| 1 | **Unauthenticated API‑Key Generation in Development Mode** | CWE‑284: Improper Access Control | **HIGH** | `generate_key_endpoint` (lines 73‑88) |
| 2 | **Insufficient Validation of User‑Provided Email** | CWE‑20: Improper Input Validation | **MEDIUM** | `KeyCreateRequest` model (lines 43‑45) |
| 3 | **Verbose Error Messages May Leak Operational Details** | CWE‑200: Information Exposure | **LOW** | `billing_webhook` (lines 123‑137) and other `HTTPException` details |
| 4 | **Potential Logging of API Keys via Response Body** | CWE‑532: Information Exposure Through Log Files | **LOW** | `generate_key_endpoint` response (lines 84‑88) |
| 5 | **Missing Explicit Rate‑Limiting on Sensitive Endpoints** | CWE‑307: Improper Restriction of Excessive Authentication Attempts | **MEDIUM** (design‑time) | Not a line‑specific bug, but an omission in the current file |

> **Note:** All other examined code paths (CORS handling, webhook signature verification, token normalization, etc.) follow secure‑by‑design practices and do **not** contain exploitable flaws.

---

### **1️⃣ Unauthenticated API‑Key Generation in Development Mode**

**Impact**  
If `config.REQUIRE_AUTH` is **False** *and* `config.IS_PRODUCTION` is **False** (the typical development setting), any client can call **POST `/api/keys/generate`** and receive a fresh privileged API key. An attacker could thus obtain unlimited free usage or elevate privileges when the same code is promoted without toggling the flags.

**Fix** – Enforce admin verification **independent** of environment flags, and make the endpoint explicitly require an admin token.  

```diff
@@
-    if config.REQUIRE_AUTH or config.IS_PRODUCTION:
-        auth_info = verify_api_key(token) if token else None
-        if not auth_info or not auth_info.get("is_admin"):
-            raise HTTPException(
-                status_code=status.HTTP_403_FORBIDDEN,
-                detail="Administrative privileges required to mint API keys directly."
-            )
+    # ------------------------------------------------------------------
+    # ALWAYS require an admin API key to mint new keys.
+    # Development environments may set a dedicated admin token via the
+    # environment variable `ADMIN_API_KEY`.  The check below does **not**
+    # depend on `REQUIRE_AUTH` or `IS_PRODUCTION` so that accidental
+    # exposure of the endpoint cannot happen when code is promoted.
+    # ------------------------------------------------------------------
+    auth_info = verify_api_key(token) if token else None
+    if not auth_info or not auth_info.get("is_admin"):
+        raise HTTPException(
+            status_code=status.HTTP_403_FORBIDDEN,
+            detail="Administrative privileges required to mint API keys."
+        )
```

*If the application truly needs an “open‑registration” mode, expose a separate **self‑service** endpoint that issues keys with limited privileges, and keep this admin‑only endpoint locked down.*

---

### **2️⃣ Insufficient Validation of User‑Provided Email**

**Impact**  
`KeyCreateRequest.user_email` is declared as a plain `str`. Down‑stream storage (e.g., a database) may be vulnerable to SQL/NoSQL injection, log injection, or malformed email values if the field is not validated.

**Fix** – Use Pydantic’s `EmailStr` (or a custom regex) to enforce a proper e‑mail format.

```diff
@@
-from pydantic import BaseModel, Field
+from pydantic import BaseModel, Field, EmailStr
@@
-class KeyCreateRequest(BaseModel):
-    user_email: str
-    tier: Optional[str] = "pro"
+class KeyCreateRequest(BaseModel):
+    # Enforce RFC‑5322‑compliant e‑mail addresses.
+    user_email: EmailStr
+    tier: Optional[str] = "pro"
```

---

### **3️⃣ Verbose Error Messages May Leak Operational Details**

**Impact**  
Returning internal configuration states (e.g., “Webhook secret not configured in production environment”) can help an attacker confirm that the server is running in production and that a secret is missing, aiding reconnaissance.

**Fix** – Replace detailed internal messages with generic ones, and log the specifics internally.

```diff
@@
-        raise HTTPException(
-            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
-            detail="Webhook secret not configured in production environment."
-        )
+        # Log the mis‑configuration for ops staff; expose a generic error to the client.
+        logger.error("Missing LemonSqueezy webhook secret in production")
+        raise HTTPException(
+            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
+            detail="Internal server error."
+        )
```

Apply the same pattern to any other `detail` strings that reveal configuration or implementation specifics.

---

### **4️⃣ Potential Logging of API Keys via Response Body**

**Impact**  
The freshly created API key is returned in the JSON response. If the server or any upstream reverse proxy logs full request/response bodies (common in development), the key may be written to log files, creating a credential leak.

**Fix** – Keep the key in the response **only** for the immediate client, and encourage the client to store it securely. Add a server‑side note to suppress body logging for this endpoint (depends on logging framework) and optionally mask the key in logs.

```diff
@@
-    return {
-        "status": "success",
-        "api_key": new_key,
-        "user_email": req.user_email,
-        "tier": req.tier or "pro"
-    }
+    # NOTE: The raw API key is returned only once.  Ensure that any request/response
+    # logging middleware excludes the `api_key` field to avoid persisting it.
+    return {
+        "status": "success",
+        "api_key": new_key,
+        "user_email": req.user_email,
+        "tier": req.tier

---

### Assessment for `app\security.py`

### [SUMMARY]  
**Severity Rating:** **HIGH**  
**Risk Overview:** The middleware trusts the `X‑Forwarded‑For` header without sufficient validation, allowing IP spoof‑spoofing and rate‑limit evasion. In addition, the Content‑Security‑Policy header weakens XSS defenses by permitting `'unsafe‑inline'` scripts/styles.

---

## [VULNERABILITY FINDINGS]

| # | Title | Severity | Location |
|---|-------|----------|----------|
| 1 | **CWE‑359: Improper Validation of X‑Forwarded‑For Header (IP Spoofing)** | **HIGH** | `SecurityMiddleware.dispatch` – lines where `client_ip` is derived from `X‑Forwarded‑For`. |
| 2 | **CWE‑79: Weak Content‑Security‑Policy (unsafe‑inline)** | **MEDIUM** | `SecurityMiddleware.dispatch` – CSP header construction (last few lines). |
| 3 | **CWE‑404: In‑Memory Rate Limiter Not Shared Across Workers** | **LOW** | `RateLimiter` class – in‑memory data structures. |
| 4 | **CWE‑770: Incomplete Payload Size Enforcement (GET/DELETE etc.)** | **LOW** | `SecurityMiddleware.dispatch` – payload‑size guard limited to POST/PUT/PATCH. |

### 1. CWE‑359 – Improper Validation of `X‑Forwarded‑For` Header  
**Impact:** An attacker can send a request from a trusted proxy IP (or from any IP if the proxy list is mis‑configured) with a forged `X‑Forwarded‑For` value, causing the middleware to treat the attacker’s address as a trusted client. This defeats rate‑limiting and any IP‑based access controls.  

**Why it’s a problem:**  
* The code trusts the first entry of the header (`client_ip = x_forwarded.split(",")[0].strip()`) as the real client IP **without** validating the number of hops or that the header was added by a trusted reverse‑proxy only.  
* If a trusted proxy forwards the request unchanged, a malicious client can simply set the header themselves (e.g., via `curl -H "X-Forwarded-For: 1.2.3.4"`).  

**Fix:** Use a robust “trusted‑proxy chain” parsing routine that discards any untrusted entries and only trusts the left‑most IP that is **not** in the trusted‑proxy list. Prefer a vetted library such as `werkzeug.middleware.proxy_fix.ProxyFix` or implement a safe parser.

```python
# --- security.py (replace the IP extraction block) ---
# 1. Safely extract client IP respecting trusted reverse proxies
peer_host = request.client.host if request.client else "127.0.0.1"
client_ip = peer_host

# Only trust X-Forwarded-For if the immediate peer is a known proxy
if peer_host in config.TRUSTED_PROXIES:
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        # X-Forwarded-For may contain a chain: client, proxy1, proxy2, ...
        # Split and trim whitespace
        forwarded_ips = [ip.strip() for ip in x_forwarded.split(",")]
        # Walk the chain from right‑most (closest proxy) to left‑most
        # Discard any IP that is itself a trusted proxy
        for ip in reversed(forwarded_ips):
            if ip not in config.TRUSTED_PROXIES:
                client_ip = ip
                break
        # If all entries are trusted proxies, fall back to the immediate peer
```

*Optional:* If you use FastAPI + Starlette, you can wrap the app with `ProxyHeadersMiddleware` from `starlette.middleware.proxy_headers` and configure `trusted_hosts` appropriately.

---

### 2. CWE‑79 – Weak Content‑Security‑Policy (allows `'unsafe-inline'`)  
**Impact:** The CSP permits inline JavaScript and CSS, which defeats the browser’s XSS mitigation. An attacker who can inject script content (e.g., via reflected XSS or a stored payload) can execute it despite the header.  

**Fix:** Remove `'unsafe-inline'` from both `script-src` and `style-src`. If you need to allow a small set of trusted inline scripts, consider using nonces or hashes instead.

```python
# --- security.py (replace the CSP header) ---
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}'; "      # generate a per‑response nonce
    "style-src 'self' 'nonce-{nonce}'; "       # same nonce can be reused for style
    "img-src 'self' data:; "
    "connect-src 'self'"
)
```

*Implementation note:* Generate a random base64 nonce per request (e.g., `nonce = secrets.token_urlsafe(16)`) and inject it into the header as shown. Ensure any templates that need inline scripts/style include `nonce="{{ nonce }}"`.

If you cannot use nonces, simply drop the `'unsafe-inline'` directives:

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'"
)
```

---

### 3. CWE‑404 – In‑Memory Rate Limiter Not Shared Across Workers  
**Impact:** When the FastAPI application runs with multiple worker processes (e.g., via Uvicorn/Gunicorn), each process maintains its own `RateLimiter` instance. An attacker can bypass the per‑IP limit by distributing requests across workers, effectively multiplying the allowed request count.  

**Fix (low‑severity but recommended):** Move the rate‑limiting state to a shared store such as Redis or Memcached. Below is a minimal change that swaps the in‑memory `OrderedDict` for a Redis sorted‑set implementation (requires `redis` library).

```python
# --- Add at top of file ---
import aioredis

# Initialize a singleton Redis client (adjust connection settings as needed)
redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)

# --- Replace RateLimiter implementation with Redis‑backed version ---
class RateLimiter:
    def __init__(self, limit: int = DEFAULT_RATE_LIMIT, window: int = DEFAULT_WINDOW_SECONDS):
        self.limit = limit
        self.window = window

    async def check_rate_limit(self, client_ip: str) -> tuple[bool, int, float]:
        now = time.time()
        key = f"rl:{client_ip}"
        # Add current timestamp
        await redis.zadd(key, {now: now})
        # Remove timestamps older than the window
        await redis.zremrangebyscore(key, 0, now - self.window)
        # Get current count
        cnt = await redis.zcard(key)
        # Set TTL to auto‑expire idle keys
        await redis.expire(key, self.window * 2)

        if cnt > self.limit:
            earliest = await redis.zrange(key, 0, 0, withscores=True)
            retry_after = self.window - (now - float(earliest[0][1]))
            return False, 0, max(0.1, retry_after)

        remaining = self.limit - cnt
        return True, remaining, float(self.window)
```

If adding Redis is overkill for the deployment, at minimum document the limitation so operators understand the risk.

---

### 4. CWE‑770 – Incomplete Payload Size Enforcement  
**Impact:** Only `POST`, `PUT

---

## 🛡️ General Security Recommendations
1. **Never commit secrets:** Store all API keys and credentials in `.env` files and add `.env` to `.gitignore`.
2. **Input Validation:** Restrict and sanitize all user-supplied inputs using Pydantic, Marshmallow, or strict regex schemas.
3. **Prepared Statements:** Always use parameterized SQL queries or ORM (SQLAlchemy, Prisma) to prevent SQL Injection.
4. **Subprocess Safety:** Never pass `shell=True` to `subprocess` with unsanitized user variables.
