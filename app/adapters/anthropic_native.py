"""
Qastroute AI - Native Anthropic Messages Provider Adapter.
Integrates directly with https://api.anthropic.com/v1/messages.
Extracts true input/output tokens and supports native SSE event streaming.
"""

import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx

from .base import ProviderAdapter, ProviderResponse, UsageMetadata, ProviderError
from .. import config

logger = logging.getLogger("qastroute.adapters.anthropic_native")

class AnthropicAdapter(ProviderAdapter):
    def __init__(self, api_key: Optional[str] = None, timeout: float = 45.0):
        super().__init__(name="anthropic", timeout=timeout)
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        self.base_url = "https://api.anthropic.com/v1"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def health_check(self) -> bool:
        return self.is_configured()

    async def generate(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        if not self.is_configured():
            raise ProviderError("Anthropic API key is not configured", status_code=503, provider=self.name)

        url = f"{self.base_url}/messages"
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"Anthropic returned {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                        provider=self.name,
                        is_retryable=resp.status_code in (429, 500, 502, 503, 504)
                    )
                data = resp.json()

        except httpx.RequestError as e:
            raise ProviderError(f"Connection to Anthropic failed: {e}", status_code=503, provider=self.name, is_retryable=True)

        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

        raw_usage = data.get("usage", {})
        usage = UsageMetadata(
            prompt_tokens=raw_usage.get("input_tokens", 0),
            completion_tokens=raw_usage.get("output_tokens", 0),
            total_tokens=raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0),
            cached_tokens=raw_usage.get("cache_read_input_tokens", 0)
        )

        return ProviderResponse(
            text=text,
            model=model_id,
            provider=self.name,
            usage=usage,
            raw=data,
            finish_reason=data.get("stop_reason", "end_turn")
        )

    async def stream(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        if not self.is_configured():
            raise ProviderError("Anthropic API key is not configured", status_code=503, provider=self.name)

        url = f"{self.base_url}/messages"
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        err_text = await response.aread()
                        raise ProviderError(
                            f"Anthropic streaming error {response.status_code}: {err_text.decode('utf-8', 'replace')}",
                            status_code=response.status_code,
                            provider=self.name,
                            is_retryable=response.status_code in (429, 502, 503, 504)
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                ev = json.loads(data_str)
                                if ev.get("type") == "content_block_delta":
                                    delta = ev.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        yield delta.get("text", "")
                            except Exception:
                                pass
        except httpx.RequestError as e:
            raise ProviderError(f"Streaming from Anthropic failed: {e}", status_code=503, provider=self.name, is_retryable=True)
