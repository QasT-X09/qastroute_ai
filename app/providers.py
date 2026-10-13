"""
Qastroute AI - Universal Upstream Provider Dispatcher with Failover Cascade.
Routes normalized requests to target LLM providers (Anthropic, OpenAI, DeepSeek, Kimi, Groq, FCC).
Includes automatic zero-downtime failover to backup models and non-blocking asynchronous HTTP handling.
Strictly zero synthetic or fabricated responses on upstream failure.
"""

from typing import Dict, Any, List, Optional
from .adapters.registry import registry

async def dispatch_completion(
    model_info: Dict[str, Any],
    messages: List[Dict[str, Any]],
    max_tokens: int = 2048,
    temperature: float = 0.7,
    system: Optional[str] = None,
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Dispatches request to upstream provider adapters with zero-downtime failover cascade.
    Uses non-blocking async HTTP client and extracts true usage metrics.
    """
    return await registry.dispatch_completion(
        model_info=model_info,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        **kwargs
    )
