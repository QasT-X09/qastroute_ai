"""
Qastroute AI - Universal OpenAI-Compatible Provider Adapter.
Direct async HTTP integration for OpenAI, DeepSeek, Groq, Moonshot Kimi, and OpenRouter.
Extracts real upstream token usage and supports true real-time SSE token streaming.
"""

import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx

from .base import ProviderAdapter, ProviderResponse, UsageMetadata, ProviderError

logger = logging.getLogger("qastroute.adapters.openai_compat")

PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1"
}

class OpenAICompatAdapter(ProviderAdapter):
    def __init__(self, provider_name: str, api_key: str, base_url: Optional[str] = None, timeout: float = 45.0):
        super().__init__(name=provider_name, timeout=timeout)
        self.api_key = api_key
        self.base_url = (base_url or PROVIDER_ENDPOINTS.get(provider_name, "https://api.openai.com/v1")).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/models", headers=headers)
                return res.status_code in (200, 401)
        except Exception:
            return False

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
            raise ProviderError(f"Provider {self.name} is not configured with an API key", status_code=503, provider=self.name)

        url = f"{self.base_url}/chat/completions"
        payload_messages = list(messages)
        if system and not any(m.get("role") == "system" for m in payload_messages):
            payload_messages.insert(0, {"role": "system", "content": system})

        payload = {
            "model": model_id,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        for extra_key in ("tools", "tool_choice", "response_format"):
            if extra_key in kwargs and kwargs[extra_key] is not None:
                payload[extra_key] = kwargs[extra_key]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"Upstream {self.name} returned {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                        provider=self.name,
                        is_retryable=resp.status_code in (429, 500, 502, 503, 504)
                    )
                data = resp.json()

        except httpx.RequestError as e:
            raise ProviderError(f"Connection to {self.name} failed: {e}", status_code=503, provider=self.name, is_retryable=True)

        choice = data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "") or ""
        finish_reason = choice.get("finish_reason", "stop")

        # Extract true provider usage metadata
        raw_usage = data.get("usage", {})
        usage = UsageMetadata(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
            cached_tokens=raw_usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        )

        return ProviderResponse(
            text=text,
            model=model_id,
            provider=self.name,
            usage=usage,
            raw=data,
            finish_reason=finish_reason
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
            raise ProviderError(f"Provider {self.name} is not configured with an API key", status_code=503, provider=self.name)

        url = f"{self.base_url}/chat/completions"
        payload_messages = list(messages)
        if system and not any(m.get("role") == "system" for m in payload_messages):
            payload_messages.insert(0, {"role": "system", "content": system})

        payload = {
            "model": model_id,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        err_text = await response.aread()
                        raise ProviderError(
                            f"Upstream {self.name} streaming error {response.status_code}: {err_text.decode('utf-8', 'replace')}",
                            status_code=response.status_code,
                            provider=self.name,
                            is_retryable=response.status_code in (429, 502, 503, 504)
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                ev = json.loads(data_str)
                                choices = ev.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except Exception:
                                pass
        except httpx.RequestError as e:
            raise ProviderError(f"Streaming from {self.name} failed: {e}", status_code=503, provider=self.name, is_retryable=True)
