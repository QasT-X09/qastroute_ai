"""
Qastroute AI - Local Free Claude Code (FCC) Adapter.
Non-blocking async HTTP client for local high-throughput multi-model gateway (127.0.0.1:8082).
Supports Codestral, GPT-OSS-120B, Gemini Flash, Nemotron, and Kimi Moonshot.
"""

import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx

from .base import ProviderAdapter, ProviderResponse, UsageMetadata, ProviderError
from .. import config

logger = logging.getLogger("qastroute.adapters.fcc")

class FCCAdapter(ProviderAdapter):
    def __init__(self, base_url: Optional[str] = None, timeout: float = 6.0):
        super().__init__(name="fcc", timeout=timeout)
        self.base_url = (base_url or config.FCC_LOCAL_GATEWAY).rstrip("/")
        self.auth_token = "freecc"

    def _resolve_fcc_model(self, model_id: str) -> str:
        # Map unknown or frontier aliases to confirmed 100% free models on FCC
        supported = {
            "mistral/codestral-latest",
            "groq/openai/gpt-oss-120b",
            "gemini/gemini-3.6-flash",
            "anthropic/open_router/nvidia/nemotron-3-super-120b-a12b:free",
            "anthropic/open_router/google/gemma-4-31b-it:free"
        }
        if model_id in supported:
            return model_id
        if "code" in model_id:
            return "mistral/codestral-latest"
        if "flash" in model_id:
            return "gemini/gemini-3.6-flash"
        return "groq/openai/gpt-oss-120b"

    def is_configured(self) -> bool:
        return config.ENABLE_LOCAL_BRIDGE and bool(self.base_url)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/health")
                return res.status_code == 200
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
        fcc_model = self._resolve_fcc_model(model_id)
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": fcc_model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": messages
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.auth_token,
            "Authorization": f"Bearer {self.auth_token}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        accumulated = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        err_text = await response.aread()
                        raise ProviderError(
                            f"FCC gateway returned error {response.status_code}: {err_text.decode('utf-8', 'replace')}",
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
                                if ev.get("type") == "content_block_delta":
                                    delta = ev.get("delta", {})
                                    text_chunk = delta.get("text", "")
                                    if text_chunk:
                                        accumulated.append(text_chunk)
                            except Exception:
                                pass

        except httpx.RequestError as e:
            raise ProviderError(f"FCC gateway connection failed: {e}", status_code=503, provider=self.name, is_retryable=True)

        full_text = "".join(accumulated).strip()
        if not full_text:
            raise ProviderError("FCC gateway returned empty response", status_code=502, provider=self.name, is_retryable=True)

        # Estimate prompt/completion tokens if upstream doesn't include usage block
        prompt_len = sum(len(str(m.get("content", "")).split()) for m in messages)
        comp_len = len(full_text.split())

        return ProviderResponse(
            text=full_text,
            model=model_id,
            provider=self.name,
            usage=UsageMetadata(prompt_tokens=prompt_len, completion_tokens=comp_len, total_tokens=prompt_len + comp_len)
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
        fcc_model = self._resolve_fcc_model(model_id)
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": fcc_model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": messages
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.auth_token,
            "Authorization": f"Bearer {self.auth_token}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        err_text = await response.aread()
                        raise ProviderError(
                            f"FCC streaming error {response.status_code}: {err_text.decode('utf-8', 'replace')}",
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
                                if ev.get("type") == "content_block_delta":
                                    delta = ev.get("delta", {})
                                    text_chunk = delta.get("text", "")
                                    if text_chunk:
                                        yield text_chunk
                            except Exception:
                                pass
        except httpx.RequestError as e:
            raise ProviderError(f"FCC streaming connection failed: {e}", status_code=503, provider=self.name, is_retryable=True)
