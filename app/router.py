"""
Qastroute AI - Smart Semantic Router & Tier Classifier.
Directs prompts to the optimal model based on complexity, context size, and domain.
Includes input/output cost modeling, tool-awareness, and explainable routing decisions.
"""

import re
from typing import Dict, Any, Tuple, Optional, List

# Comprehensive Model Catalog with real-world cost benchmarks (per 1M tokens)
# Distinguishes separate input and output rates where applicable
MODEL_CATALOG = {
    # ── Ultra-Frontier Reasoning Tier ($15 - $25 / 1M tokens) ──
    "gpt-6.1-sol-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-6.1-sol-pro",
        "description": "OpenAI GPT-6.1 Sol Pro (State-of-the-Art Frontier Logic)",
        "tier": "ultra_frontier",
        "cost_per_m": 25.0,
        "input_cost_per_m": 20.0,
        "output_cost_per_m": 30.0,
        "capabilities": ["reasoning", "tools", "vision"]
    },
    "gpt-6.1-sol": {
        "provider": "openai",
        "real_id": "openai/gpt-6.1-sol",
        "description": "OpenAI GPT-6.1 Sol (Flagship Extended Intelligence)",
        "tier": "ultra_frontier",
        "cost_per_m": 20.0,
        "input_cost_per_m": 15.0,
        "output_cost_per_m": 25.0,
        "capabilities": ["reasoning", "tools", "vision"]
    },
    "gpt-6-astra-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-6-astra-pro",
        "description": "OpenAI GPT-6 Astra Pro (Multimodal Ultra Flagship)",
        "tier": "ultra_frontier",
        "cost_per_m": 22.0,
        "input_cost_per_m": 18.0,
        "output_cost_per_m": 26.0,
        "capabilities": ["reasoning", "tools", "vision"]
    },
    "gpt-6-astra": {
        "provider": "openai",
        "real_id": "openai/gpt-6-astra",
        "description": "OpenAI GPT-6 Astra (Multimodal Flagship)",
        "tier": "flagship",
        "cost_per_m": 18.0,
        "input_cost_per_m": 12.0,
        "output_cost_per_m": 24.0,
        "capabilities": ["reasoning", "tools", "vision"]
    },
    "gpt-5.6-sol-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-5.6-sol-pro",
        "description": "OpenAI GPT-5.6 Sol Pro (High-End Reasoning Engine)",
        "tier": "flagship",
        "cost_per_m": 16.0,
        "input_cost_per_m": 12.0,
        "output_cost_per_m": 20.0,
        "capabilities": ["reasoning", "tools"]
    },
    "gpt-5.6-sol": {
        "provider": "openai",
        "real_id": "openai/gpt-5.6-sol",
        "description": "OpenAI GPT-5.6 Sol (Deep Reasoning)",
        "tier": "flagship",
        "cost_per_m": 12.0,
        "input_cost_per_m": 8.0,
        "output_cost_per_m": 16.0,
        "capabilities": ["reasoning", "tools"]
    },
    "claude-opus-5.5": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-opus-5.5",
        "description": "Anthropic Claude Opus 5.5 (Flagship Complex Reasoning & Math)",
        "tier": "ultra_frontier",
        "cost_per_m": 22.0,
        "input_cost_per_m": 18.0,
        "output_cost_per_m": 26.0,
        "capabilities": ["reasoning", "tools", "math"]
    },
    "claude-fable-5.1": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-fable-5.1",
        "description": "Anthropic Claude Fable 5.1 (High Intelligence Flagship)",
        "tier": "flagship",
        "cost_per_m": 15.0,
        "input_cost_per_m": 10.0,
        "output_cost_per_m": 20.0,
        "capabilities": ["reasoning", "tools", "architecture"]
    },
    "claude-sonnet-5.5": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-sonnet-5.5",
        "description": "Anthropic Claude Sonnet 5.5 (Balanced Workhorse)",
        "tier": "balanced",
        "cost_per_m": 3.0,
        "input_cost_per_m": 2.0,
        "output_cost_per_m": 4.0,
        "capabilities": ["tools", "general"]
    },
    "o3-pro": {
        "provider": "openai",
        "real_id": "openai/o3-pro",
        "description": "OpenAI o3-pro (Extended Chain-of-Thought Reasoning)",
        "tier": "ultra_frontier",
        "cost_per_m": 20.0,
        "input_cost_per_m": 15.0,
        "output_cost_per_m": 25.0,
        "capabilities": ["reasoning", "math"]
    },

    # ── Code & Balanced Workhorses ($0.5 - $1.5 / 1M tokens) ──
    "codestral-latest": {
        "provider": "mistral",
        "real_id": "mistral/codestral-latest",
        "description": "Mistral Codestral (SOTA Dedicated Code Engine)",
        "tier": "code",
        "cost_per_m": 1.0,
        "input_cost_per_m": 0.8,
        "output_cost_per_m": 1.2,
        "capabilities": ["code", "refactoring"]
    },
    "gemini-3.6-flash": {
        "provider": "google",
        "real_id": "gemini/gemini-3.6-flash",
        "description": "Google Gemini 3.6 Flash (Fast Architecture & Huge Context)",
        "tier": "balanced",
        "cost_per_m": 0.5,
        "input_cost_per_m": 0.35,
        "output_cost_per_m": 0.65,
        "capabilities": ["general", "long_context"]
    },

    # ── Mega-Context & Document Tier ($1.5 / 1M tokens) ──
    "kimi-k3": {
        "provider": "moonshot",
        "real_id": "moonshotai/kimi-k3",
        "description": "Kimi Moonshot K3 (2M+ Mega-Context Analysis)",
        "tier": "mega_context",
        "cost_per_m": 1.5,
        "input_cost_per_m": 1.0,
        "output_cost_per_m": 2.0,
        "capabilities": ["mega_context", "documents"]
    },
    "kimi-k2.7-code": {
        "provider": "moonshot",
        "real_id": "moonshotai/kimi-k2.7-code",
        "description": "Kimi Moonshot K2.7 Code Specialist",
        "tier": "code",
        "cost_per_m": 1.2,
        "input_cost_per_m": 0.9,
        "output_cost_per_m": 1.5,
        "capabilities": ["code"]
    },

    # ── Ultra-Low Cost & Fast Tier ($0.1 - $0.8 / 1M tokens) ──
    "deepseek-r1": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-r1",
        "description": "DeepSeek R1 (Advanced Open Reasoning)",
        "tier": "reasoning_cheap",
        "cost_per_m": 0.8,
        "input_cost_per_m": 0.55,
        "output_cost_per_m": 1.05,
        "capabilities": ["reasoning", "math"]
    },
    "deepseek-v3.2": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-v3.2",
        "description": "DeepSeek V3.2 (Cost-Performance Leader)",
        "tier": "budget",
        "cost_per_m": 0.27,
        "input_cost_per_m": 0.14,
        "output_cost_per_m": 0.40,
        "capabilities": ["general", "budget"]
    },
    "deepseek-v3": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-chat",
        "description": "DeepSeek V3 (SOTA Value Flagship)",
        "tier": "budget",
        "cost_per_m": 0.27,
        "input_cost_per_m": 0.14,
        "output_cost_per_m": 0.40,
        "capabilities": ["general", "budget"]
    },
    "groq-gpt120b": {
        "provider": "groq",
        "real_id": "groq/openai/gpt-oss-120b",
        "description": "Groq GPT-OSS-120B (Ultra-Fast 300+ tok/s)",
        "tier": "budget",
        "cost_per_m": 0.15,
        "input_cost_per_m": 0.10,
        "output_cost_per_m": 0.20,
        "capabilities": ["fast", "budget"]
    },
    "nemotron-3-super": {
        "provider": "nvidia",
        "real_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "description": "NVIDIA Nemotron 3 Super 120B (Open Engine)",
        "tier": "budget",
        "cost_per_m": 0.2,
        "input_cost_per_m": 0.1,
        "output_cost_per_m": 0.3,
        "capabilities": ["general"]
    }
}

BASELINE_COST_PER_M = 15.0  # Industry standard expensive frontier baseline

class ClassificationResult(tuple):
    """Subclass of tuple (tier, model) with an optional reason attribute."""
    def __new__(cls, tier: str, model: str, reason: str = ""):
        obj = super().__new__(cls, (tier, model))
        obj.reason = reason
        return obj

class SmartRouter:
    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "routed_by_tier": {"flagship": 0, "balanced": 0, "code": 0, "budget": 0, "mega_context": 0},
            "total_tokens_processed": 0,
            "estimated_dollars_saved": 0.0,
            "cache_tokens_saved": 0
        }

    def classify_complexity(self, prompt: str, has_tools: bool = False) -> ClassificationResult:
        """
        Classifies prompt into optimal tier based on length, intent, tool use, and complexity signals.
        Returns: (tier_name, selected_model_id) with .reason attribute.
        """
        total_len = len(prompt)

        # 1. Tools / Structured execution check
        if has_tools:
            return ClassificationResult("flagship", "claude-fable-5.1", "Function/tool calling requires flagship reasoning model")

        # 2. Mega-Context Check (Large documents, logs, book chapters)
        if total_len > 40000:
            return ClassificationResult("mega_context", "kimi-k3", f"Large context ({total_len} chars) routed to 2M context model")

        # 3. Deep Reasoning Signals (Formal logic, mathematical proofs, architectural specs)
        deep_signals = [
            r"\b(prove|theorem|derivation|formal proof)\b",
            r"\b(system architecture|distributed consensus|kernel driver)\b",
            r"\b(reverse engineer|cryptographic analysis)\b"
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in deep_signals):
            return ClassificationResult("flagship", "claude-fable-5.1", "High-complexity mathematical or architectural reasoning detected")

        # 4. Dedicated Code Signals
        code_signals = [
            r"\b(def |class |function |const |import |from |SELECT |CREATE TABLE|async def)\b",
            r"\b(refactor|debug|unit test|pytest|npm test|dockerfile|regex)\b",
            r"```[a-z]*\n"
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in code_signals):
            return ClassificationResult("code", "codestral-latest", "Dedicated code generation or refactoring task identified")

        # 5. Standard / Simple queries (Summary, translation, casual Q&A, format JSON)
        simple_signals = [
            r"\b(translate|summarize|hello|hi|what is|explain like i'm 5|format as json)\b",
            r"^[\w\s\?\.]{1,120}$"
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in simple_signals) or total_len < 300:
            return ClassificationResult("budget", "groq-gpt120b", "Low-complexity query routed to high-speed budget tier")

        # Default balanced
        return ClassificationResult("balanced", "gemini-3.6-flash", "General-purpose query routed to balanced workhorse tier")

    def resolve_model(
        self,
        requested_model: str,
        prompt_text: str,
        has_tools: bool = False
    ) -> Tuple[str, Dict[str, Any], bool, str]:
        """
        Resolves model alias or auto-routes.
        Returns: (effective_model_id, model_info, was_auto_routed, routing_reason)
        """
        req_clean = requested_model.strip().lower()

        # Auto-Routing requested by client
        if req_clean in ["auto", "smart", "qast-auto", "default", ""]:
            res = self.classify_complexity(prompt_text, has_tools=has_tools)
            tier, target_model = res[0], res[1]
            reason = getattr(res, "reason", "Auto-routed by complexity classifier")
            info = MODEL_CATALOG[target_model]
            return target_model, info, True, reason

        # Exact match in catalog
        if req_clean in MODEL_CATALOG:
            return req_clean, MODEL_CATALOG[req_clean], False, f"Explicit model selection: {req_clean}"

        # Fuzzy match for popular aliases
        for key, val in MODEL_CATALOG.items():
            if req_clean in key or key in req_clean:
                return key, val, False, f"Matched alias '{req_clean}' to catalog model '{key}'"

        # Fallback to requested as direct pass-through
        return requested_model, {
            "provider": "openrouter",
            "real_id": requested_model,
            "description": f"Direct Pass-through: {requested_model}",
            "tier": "custom",
            "cost_per_m": 10.0,
            "input_cost_per_m": 8.0,
            "output_cost_per_m": 12.0
        }, False, "Direct pass-through model ID"

    def record_transaction(
        self,
        model_key: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
        is_cache_hit: bool = False
    ) -> float:
        """
        Calculates and records actual cost and savings.
        Returns: actual_cost_usd incurred.
        """
        total_tokens = prompt_tokens + completion_tokens
        self.stats["total_requests"] += 1
        self.stats["total_tokens_processed"] += total_tokens

        info = MODEL_CATALOG.get(model_key, {"tier": "custom", "cost_per_m": 5.0, "input_cost_per_m": 4.0, "output_cost_per_m": 6.0})
        tier = info.get("tier", "custom")
        if tier in self.stats["routed_by_tier"]:
            self.stats["routed_by_tier"][tier] += 1

        baseline_cost = (total_tokens / 1_000_000.0) * BASELINE_COST_PER_M

        if is_cache_hit:
            # Cache hit: $0.00 upstream cost, 100% savings
            self.stats["cache_tokens_saved"] += total_tokens
            self.stats["estimated_dollars_saved"] += baseline_cost
            return 0.0

        # Non-cached: calculate true input and output costs
        input_rate = info.get("input_cost_per_m", info.get("cost_per_m", 5.0))
        output_rate = info.get("output_cost_per_m", info.get("cost_per_m", 5.0))

        actual_cost = ((prompt_tokens / 1_000_000.0) * input_rate) + ((completion_tokens / 1_000_000.0) * output_rate)
        savings = max(0.0, baseline_cost - actual_cost)
        self.stats["estimated_dollars_saved"] += savings
        return actual_cost

router = SmartRouter()
