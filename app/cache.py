"""
Qastroute AI - Enterprise Prompt & Response Caching Layer.
Tenant-isolated, parameter-aware semantic cache with TTL, max-capacity eviction, and zero data leakage.
"""

import hashlib
import json
import time
from typing import Optional, Dict, Any, List

MAX_CACHE_ENTRIES = 5000

class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
        self.bypasses = 0

    def _hash_key(
        self,
        tenant_id: str,
        model: str,
        messages: list,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
        response_format: Optional[dict] = None
    ) -> str:
        """
        Creates a deterministic SHA-256 hash including tenant scope and all generation settings.
        Prevents cross-tenant cache leakage (CWE-200) and generation setting collisions.
        """
        normalized_messages = []
        for m in messages:
            if isinstance(m, dict):
                normalized_messages.append({"role": m.get("role", ""), "content": m.get("content", "")})
            else:
                normalized_messages.append(str(m))

        components = {
            "tenant_id": tenant_id or "public",
            "model": model.strip().lower(),
            "messages": normalized_messages,
            "system": system or "",
            "temperature": round(temperature, 2) if temperature is not None else 0.7,
            "tools": tools or [],
            "response_format": response_format or {}
        }

        serialized = json.dumps(components, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(
        self,
        tenant_id: str,
        model: str,
        messages: list,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
        response_format: Optional[dict] = None,
        bypass_cache: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieves cached response if valid and not expired."""
        if bypass_cache:
            self.bypasses += 1
            return None

        key = self._hash_key(tenant_id, model, messages, system, temperature, tools, response_format)
        entry = self.cache.get(key)
        if not entry:
            self.misses += 1
            return None

        # Check TTL
        if time.time() - entry["timestamp"] > self.ttl:
            del self.cache[key]
            self.misses += 1
            return None

        self.hits += 1
        return entry["response"]

    def set(
        self,
        tenant_id: str,
        model: str,
        messages: list,
        response: Dict[str, Any],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
        response_format: Optional[dict] = None
    ):
        """Caches response if not simulated or failed."""
        if not response or response.get("simulation") or response.get("error"):
            return

        # Bound cache size to prevent memory leaks (CWE-400)
        if len(self.cache) >= MAX_CACHE_ENTRIES:
            # Evict oldest entry
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]

        key = self._hash_key(tenant_id, model, messages, system, temperature, tools, response_format)
        self.cache[key] = {
            "timestamp": time.time(),
            "response": response
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "cached_entries": len(self.cache),
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "cache_bypasses": self.bypasses,
            "hit_ratio": round(self.hits / max(1, self.hits + self.misses), 3)
        }

cache = ResponseCache()
