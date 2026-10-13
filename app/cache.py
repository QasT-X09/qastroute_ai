"""
Qastroute AI - Enterprise Prompt & Response Caching Layer.
Zero-latency ($0.00 cost) cache for identical and repetitive LLM queries.
"""

import hashlib
import time
from typing import Optional, Dict, Any

class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _hash_key(self, model: str, messages: list) -> str:
        serialized = f"{model}::" + "::".join([f"{m.get('role', '')}:{m.get('content', '')}" for m in messages if isinstance(m, dict)])
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, model: str, messages: list) -> Optional[Dict[str, Any]]:
        key = self._hash_key(model, messages)
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

    def set(self, model: str, messages: list, response: Dict[str, Any]):
        key = self._hash_key(model, messages)
        self.cache[key] = {
            "timestamp": time.time(),
            "response": response
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "cached_entries": len(self.cache),
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "hit_ratio": round(self.hits / max(1, self.hits + self.misses), 3)
        }

cache = ResponseCache()
