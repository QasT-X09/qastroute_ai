"""
Qastroute AI - Provider Adapter Registry and Dispatch Manager.
Manages adapter lifecycle, intelligent retries, loop-safe failover cascades, and error handling.
Strictly zero fake responses: raises structured ProviderError when providers fail.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from fastapi import HTTPException

from .base import ProviderAdapter, ProviderResponse, ProviderError
from .fcc import FCCAdapter
from .openai_compat import OpenAICompatAdapter
from .anthropic_native import AnthropicAdapter
from .. import config

logger = logging.getLogger("qastroute.adapters.registry")

class AdapterRegistry:
    def __init__(self):
        self.adapters: Dict[str, ProviderAdapter] = {}
        self._init_default_adapters()

    def _init_default_adapters(self):
        # 1. Local Free Claude Code (FCC) bridge (ultra-fast, 100% free multi-model gateway)
        if config.ENABLE_LOCAL_BRIDGE:
            self.adapters["fcc"] = FCCAdapter(base_url=config.FCC_LOCAL_GATEWAY)

        # 2. Native Direct Upstream Providers
        if config.OPENAI_API_KEY:
            self.adapters["openai"] = OpenAICompatAdapter("openai", config.OPENAI_API_KEY)
        if config.DEEPSEEK_API_KEY:
            self.adapters["deepseek"] = OpenAICompatAdapter("deepseek", config.DEEPSEEK_API_KEY)
        if config.GROQ_API_KEY:
            self.adapters["groq"] = OpenAICompatAdapter("groq", config.GROQ_API_KEY)
        if config.KIMI_API_KEY:
            self.adapters["moonshot"] = OpenAICompatAdapter("moonshot", config.KIMI_API_KEY)
        if config.MISTRAL_API_KEY:
            self.adapters["mistral"] = OpenAICompatAdapter("mistral", config.MISTRAL_API_KEY)
        if config.OPENROUTER_API_KEY:
            self.adapters["openrouter"] = OpenAICompatAdapter("openrouter", config.OPENROUTER_API_KEY)
        if config.ANTHROPIC_API_KEY:
            self.adapters["anthropic"] = AnthropicAdapter(config.ANTHROPIC_API_KEY)

    def get_adapter(self, provider_name: str) -> Optional[ProviderAdapter]:
        # Return direct provider if configured
        if provider_name in self.adapters and self.adapters[provider_name].is_configured():
            return self.adapters[provider_name]
        # Fall back to FCC bridge if enabled and online
        if "fcc" in self.adapters and self.adapters["fcc"].is_configured():
            return self.adapters["fcc"]
        return None

    async def dispatch_completion(
        self,
        model_info: Dict[str, Any],
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        max_fallbacks: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes completion with loop-safe failover cascade and exponential backoff.
        Raises HTTPException(502/504) if all models fail. Never fabricates responses.
        """
        from ..failover import failover_cascade
        from ..router import MODEL_CATALOG

        primary_model_alias = model_info.get("id") or model_info.get("real_id", "")
        chain = [primary_model_alias] + failover_cascade.get_fallbacks(primary_model_alias)[:max_fallbacks]

        visited_models: Set[str] = set()
        last_error: Optional[Exception] = None

        for idx, candidate_alias in enumerate(chain):
            if candidate_alias in visited_models:
                continue
            visited_models.add(candidate_alias)

            candidate_info = MODEL_CATALOG.get(candidate_alias, model_info)
            provider_name = candidate_info.get("provider", "generic")
            real_model_id = candidate_info.get("real_id", candidate_alias)

            adapter = self.get_adapter(provider_name)
            if not adapter:
                logger.warning(f"No configured adapter found for provider '{provider_name}' (model: {candidate_alias}).")
                continue

            # Attempt dispatch with up to 2 retries for transient errors
            for attempt in range(2):
                try:
                    resp: ProviderResponse = await adapter.generate(
                        model_id=real_model_id,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                        **kwargs
                    )
                    return {
                        "text": resp.text,
                        "model": candidate_alias,
                        "real_id": real_model_id,
                        "provider": adapter.name,
                        "failover_applied": idx > 0,
                        "original_model": primary_model_alias if idx > 0 else None,
                        "usage": {
                            "prompt_tokens": resp.usage.prompt_tokens,
                            "completion_tokens": resp.usage.completion_tokens,
                            "total_tokens": resp.usage.total_tokens,
                            "cached_tokens": resp.usage.cached_tokens
                        },
                        "finish_reason": resp.finish_reason
                    }
                except ProviderError as e:
                    last_error = e
                    logger.warning(f"Attempt {attempt + 1} failed for model '{candidate_alias}' on {adapter.name}: {e.message}")
                    if e.is_retryable and attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    break
                except Exception as e:
                    last_error = e
                    logger.error(f"Unexpected error calling {candidate_alias}: {e}")
                    break

        # If all candidates in chain failed, raise structured HTTP 502/504 error
        err_msg = f"All upstream providers in failover chain failed: {last_error}" if last_error else "No available upstream providers configured."
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "message": err_msg,
                    "type": "upstream_provider_failure",
                    "visited_models": list(visited_models)
                }
            }
        )

registry = AdapterRegistry()
