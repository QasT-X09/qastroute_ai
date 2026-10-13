"""
Qastroute AI - Provider Adapter Base Interface.
Defines normalized contracts for LLM providers: generation, streaming, usage extraction, and error normalization.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator

@dataclass
class UsageMetadata:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

@dataclass
class ProviderResponse:
    text: str
    model: str
    provider: str
    usage: UsageMetadata
    raw: Dict[str, Any] = field(default_factory=dict)
    finish_reason: Optional[str] = "stop"

class ProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502, provider: str = "unknown", is_retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider = provider
        self.is_retryable = is_retryable

class ProviderAdapter(ABC):
    """Abstract Base Class for all external and local AI model providers."""

    def __init__(self, name: str, timeout: float = 30.0):
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the necessary API key or endpoint is configured."""
        pass

    @abstractmethod
    async def generate(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Executes non-streaming completion."""
        pass

    @abstractmethod
    async def stream(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Yields raw text delta chunks as they arrive from upstream."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifies connection health to the upstream provider."""
        pass
