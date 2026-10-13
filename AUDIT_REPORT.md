# QASTROUTE AI — COMPREHENSIVE ARCHITECTURE & SECURITY AUDIT REPORT

**Date:** 2026-10-13  
**Auditor:** Senior Staff Software Engineer & Application Security Architect (via FCC Multi-Model Orchestra)  
**Target:** `https://github.com/QasT-X09/qastroute_ai`  
**Status:** Audit Completed — Implementation in Progress  

---

## 1. Executive Summary

A comprehensive architectural, security, and reliability audit of the Qastroute AI Gateway codebase was conducted against the standards defined in the Production Hardening Specification. While the gateway demonstrates strong potential with its dual-protocol architecture and dynamic telemetry, critical vulnerabilities and architectural defects were identified:

1. **Security & Authentication:** Insecure default master API keys, optional authentication by default, unauthenticated API key minting endpoint, plaintext key storage, and trust of unverified forwarded headers.
2. **Provider Dispatch & Integrity:** Upstream dispatch silently synthesizes fake mock responses upon failure, uses blocking synchronous I/O in async request handlers, and lacks modular provider adapters.
3. **Usage & Cost Accounting:** Token counts and cost calculations are derived from word-splitting (`split()`) rather than provider-reported or tokenizer-backed token usage, and cache hits are incorrectly billed as upstream spend.
4. **Semantic Caching:** Cache keys lack tenant isolation, allowing cross-tenant response leakage, and omit critical generation parameters (`temperature`, `tools`, `system`).
5. **Streaming:** Streaming is currently simulated post-completion by chunking words with artificial delays rather than true upstream Server-Sent Events (SSE) pass-through.

---

## 2. Vulnerability & Defect Catalog

### SEC-01: Insecure Default Master API Key & Permissive Auth Default
- **Severity:** CRITICAL
- **Location:** `app/config.py` (lines 18-19) & `app/billing.py:verify_api_key` (lines 80-82)
- **Reproduction:** Call `/v1/chat/completions` with header `Authorization: Bearer qast-live-demo-key` or with no header when `REQUIRE_AUTH=False`.
- **Impact:** Complete authorization bypass. Any unauthorized client can access the gateway and consume upstream quota.
- **Remediation:** Remove hardcoded master key default. Fail closed in production if no admin key is configured. Make authentication mandatory for protected endpoints.
- **Verification Test:** Test protected endpoints reject requests without a valid provisioned key, and verify default insecure keys are rejected.

---

### SEC-02: Public Unauthenticated API Key Minting
- **Severity:** HIGH
- **Location:** `app/main.py:generate_key_endpoint` (lines 129-138)
- **Reproduction:** `POST /api/keys/generate` with `{"user_email": "attacker@evil.com", "tier": "enterprise"}`. Key is returned immediately with enterprise tier.
- **Impact:** Any public user can mint unlimited enterprise API keys without payment or admin rights.
- **Remediation:** Require admin authentication for `/api/keys/generate` or restrict key generation strictly to verified payment webhooks.
- **Verification Test:** Unauthenticated requests to `/api/keys/generate` return HTTP 401/403.

---

### SEC-03: Plaintext Storage of API Keys in SQLite Database
- **Severity:** HIGH
- **Location:** `app/billing.py:create_api_key` & `verify_api_key` (lines 35, 60-68, 87)
- **Reproduction:** Inspect `data/qastroute.db` table `api_keys`. Raw keys `qr_live_...` are stored in plaintext.
- **Impact:** Exposure of SQLite database yields all client API keys directly (CWE-312).
- **Remediation:** Store SHA-256 hashes of keys (`key_hash`). Return the plaintext key only once upon generation. Verify keys by comparing hashes.
- **Verification Test:** Database query returns only hashes; verification works against hashed values.

---

### SEC-04: Insecure Webhook Signature Bypass When Secret Is Unset
- **Severity:** HIGH
- **Location:** `app/billing.py:verify_lemonsqueezy_signature` (lines 110-113)
- **Reproduction:** Send POST to `/api/webhook/billing` when `LEMONSQUEEZY_WEBHOOK_SECRET` is unset. Function returns `True` unconditionally.
- **Impact:** Attackers can forge webhook events to mint arbitrary keys without paying (CWE-306).
- **Remediation:** Enforce signature checking strictly. Fail closed if webhook secret is not configured.
- **Verification Test:** Webhook endpoint rejects unsigned or invalid signatures with HTTP 400/401.

---

### SEC-05: Webhook Replay Vulnerability Granting Duplicate Entitlements
- **Severity:** MEDIUM
- **Location:** `app/billing.py:process_webhook_event` (lines 146-154)
- **Reproduction:** Re-send an identical `order_created` webhook payload with the same `event_id`.
- **Impact:** Multiple duplicate API keys are minted for a single order event.
- **Remediation:** Verify idempotency before key generation: check if `event_id` was already processed; if so, return existing status without generating a new key.
- **Verification Test:** Replaying the same webhook event returns HTTP 200 with idempotent status and no duplicate key generation.

---

### SEC-06: Untrusted X-Forwarded-For Header Rate Limit Bypass
- **Severity:** HIGH
- **Location:** `app/security.py:SecurityMiddleware.dispatch` (lines 81-89)
- **Reproduction:** Send requests with spoofed header `X-Forwarded-For: 1.2.3.4`, changing IP on every request.
- **Impact:** Bypasses per-IP rate limiter completely (CWE-359).
- **Remediation:** Only trust `X-Forwarded-For` from configured `TRUSTED_PROXIES`. Fall back to `request.client.host`.
- **Verification Test:** Spoofed `X-Forwarded-For` from untrusted client host is ignored for rate limiting.

---

### SEC-07: Incomplete Payload Size Enforcement (Chunked Transfer DoS)
- **Severity:** HIGH
- **Location:** `app/security.py:SecurityMiddleware.dispatch` (lines 91-101)
- **Reproduction:** Send POST request with chunked transfer encoding and body > 5MB without `Content-Length`.
- **Impact:** Memory exhaustion / Denial of Service (CWE-770).
- **Remediation:** Read request body stream with a streaming byte cap (`MAX_BODY_BYTES + 1`) and abort with HTTP 413 if exceeded.
- **Verification Test:** Chunked request exceeding 5MB returns HTTP 413.

---

### SEC-08: Token Leakage via URL Query Parameter
- **Severity:** MEDIUM
- **Location:** `app/main.py:verify_key_endpoint` (line 144)
- **Reproduction:** `GET /api/keys/verify?key=qr_live_secret123`.
- **Impact:** Sensitive token logged in web server access logs and browser history (CWE-200).
- **Remediation:** Disallow query parameter tokens; accept only `Authorization: Bearer <key>` or `X-API-Key` headers.
- **Verification Test:** Requests with query parameter `?key=...` return HTTP 400.

---

### PRV-01: Fabrication of Synthetic LLM Responses on Upstream Outage
- **Severity:** CRITICAL
- **Location:** `app/providers.py:dispatch_completion` (lines 101-108)
- **Reproduction:** Disconnect internet or point to non-existent provider. Send request.
- **Impact:** Returns fake synthetic message `"[Description Response] Task processed successfully via Qastroute AI Gateway."` with HTTP 200, concealing upstream failure from callers and violating core integrity rules.
- **Remediation:** When all upstream models and fallbacks fail, raise a standardized structured error (`UpstreamProviderError` / HTTP 502/504) with clear diagnostics.
- **Verification Test:** Mock all providers failing; verify gateway returns HTTP 502 with structured error JSON instead of synthetic completion.

---

### PRV-02: Synchronous Blocking HTTP Calls in Async Handler
- **Severity:** HIGH
- **Location:** `app/providers.py:_try_direct_dispatch` (lines 40-54)
- **Reproduction:** Send multiple concurrent requests under network latency.
- **Impact:** `urllib.request.urlopen` blocks the asyncio event loop thread, stalling all other concurrent client requests and destroying gateway throughput.
- **Remediation:** Use asynchronous non-blocking HTTP client (`httpx.AsyncClient` or `aiohttp.ClientSession`) with connection pooling and timeouts.
- **Verification Test:** Verify async I/O is non-blocking under concurrency.

---

### PRV-03: Lack of Modular Provider Adapters
- **Severity:** HIGH
- **Location:** `app/providers.py`
- **Reproduction:** Attempt to configure upstream OpenAI, Anthropic, or DeepSeek directly without FCC bridge.
- **Impact:** Gateway cannot connect directly to official provider APIs (OpenAI, Anthropic, DeepSeek, Moonshot, Groq, Mistral) with individual credentials and retry policies.
- **Remediation:** Implement explicit `ProviderAdapter` interface (`OpenAIAdapter`, `AnthropicAdapter`, `DeepSeekAdapter`, `FCCAdapter`, `MockAdapter`).
- **Verification Test:** Provider adapters successfully route requests to configured provider endpoints with proper payload conversion and error normalization.

---

### ROUT-01: Naive Keyword and Length-Based Complexity Classification
- **Severity:** MEDIUM
- **Location:** `app/router.py:classify_complexity` (lines 169-202)
- **Reproduction:** Send short coding snippet without keywords, or high-reasoning prompt under 300 chars.
- **Impact:** Routes complex queries to budget models, causing degraded response quality.
- **Remediation:** Implement multi-factor classifier taking into account presence of code patterns, structured outputs, tool definitions, and system prompts.
- **Verification Test:** Structured input and tool calls are properly routed to capable models.

---

### COST-01: Inaccurate Word-Count Token and Cost Billing
- **Severity:** HIGH
- **Location:** `app/main.py:openai_chat_completions` (lines 275-278) & `anthropic_messages` (lines 367-370)
- **Reproduction:** Send prompt with non-whitespace tokens or code.
- **Impact:** Billing and budget tracking are inaccurate. Discrepancies between actual upstream token consumption and billing data.
- **Remediation:** Extract actual `usage` fields from upstream provider responses (`prompt_tokens`, `completion_tokens`). Maintain separate input/output cost rates in catalog.
- **Verification Test:** Usage recorded in response and budget matches provider-returned usage data.

---

### COST-02: Charging and Counting Cache Hits as Upstream Spend
- **Severity:** HIGH
- **Location:** `app/main.py:openai_chat_completions` (lines 274-278)
- **Reproduction:** Send duplicate request resulting in cache hit.
- **Impact:** Gateway increments spend metrics and daily budget caps on 0-cost cache hits, penalizing users and skewing savings metrics.
- **Remediation:** Bypass spend tracking on cache hits (`cost = 0.0`), recording only cache hit metrics.
- **Verification Test:** Repeat request does not increment `current_spend_usd` in `budget_guard`.

---

### CACHE-01: Cross-Tenant Cache Leakage (Missing Authorization Scope in Cache Key)
- **Severity:** HIGH
- **Location:** `app/cache.py:ResponseCache._hash_key` (lines 17-19)
- **Reproduction:** User A sends a private prompt. User B sends the identical prompt. User B receives User A's cached response.
- **Impact:** Data leak across tenants / clients.
- **Remediation:** Include tenant ID / API key identifier in cache key hash, and allow cache opt-out (`no-cache`).
- **Verification Test:** User B does not hit cache created by User A unless explicitly marked public.

---

### CACHE-02: Generation Parameters Ignored in Cache Key
- **Severity:** MEDIUM
- **Location:** `app/cache.py:ResponseCache._hash_key`
- **Reproduction:** Send request with `temperature=0.0`, then with `temperature=1.0` or different `system` instructions.
- **Impact:** Stale response returned ignoring parameter changes.
- **Remediation:** Hash model, messages, system prompt, temperature, tools, and response format.
- **Verification Test:** Different temperature or system prompt produces cache miss.

---

### STRM-01: Fake Post-Completion Word-Delay Streaming
- **Severity:** HIGH
- **Location:** `app/streaming.py` & `app/main.py` (lines 271, 283-288)
- **Reproduction:** Send streaming request (`stream: true`). Inspect gateway behavior.
- **Impact:** Gateway waits for the entire upstream response to complete, buffers it, and then simulates chunks with 10ms delays. High time-to-first-token (TTFT) and violates true streaming.
- **Remediation:** Implement real upstream SSE generator that streams events as they arrive from upstream providers.
- **Verification Test:** Measure TTFT and verify chunks are yielded asynchronously from the upstream stream.

---

## 3. Implementation Roadmap

The refactoring will be executed systematically across the following phases:
- **Phase 2:** Security hardening (auth, key hashing, webhook idempotency, trusted proxies, body guards).
- **Phase 3:** Provider adapter architecture (`ProviderAdapter`, async HTTP client, provider catalog).
- **Phase 4:** Reliable routing, loop-safe fallback, and structured error responses.
- **Phase 5:** Accurate token accounting, input/output cost separation, and atomic budget guard.
- **Phase 6:** Tenant-isolated semantic caching with full parameter hashing.
- **Phase 7:** True asynchronous streaming pass-through for OpenAI and Anthropic formats.
- **Phase 8:** Complete API schema compatibility (tools, system prompts, error schemas).
- **Phase 9-10:** Observability metrics, health checks, SQLite concurrency hardening.
- **Phase 11-13:** Test suite expansion, security audit pass, and documentation.
