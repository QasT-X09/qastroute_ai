"""
Qastroute AI - Smart Semantic Router & Tier Classifier.
Directs prompts to the optimal model based on complexity, context size, and domain.
"""

import re
from typing import Dict, Any, Tuple

# Comprehensive Model Catalog with real-world cost benchmarks (per 1M tokens)
MODEL_CATALOG = {
    # ── Ultra-Frontier Reasoning Tier ($15 - $25 / 1M tokens) ──
    "gpt-6.1-sol-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-6.1-sol-pro",
        "description": "OpenAI GPT-6.1 Sol Pro (State-of-the-Art Frontier Logic)",
        "tier": "ultra_frontier",
        "cost_per_m": 25.0
    },
    "gpt-6.1-sol": {
        "provider": "openai",
        "real_id": "openai/gpt-6.1-sol",
        "description": "OpenAI GPT-6.1 Sol (Flagship Extended Intelligence)",
        "tier": "ultra_frontier",
        "cost_per_m": 20.0
    },
    "gpt-6-astra-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-6-astra-pro",
        "description": "OpenAI GPT-6 Astra Pro (Multimodal Ultra Flagship)",
        "tier": "ultra_frontier",
        "cost_per_m": 22.0
    },
    "gpt-6-astra": {
        "provider": "openai",
        "real_id": "openai/gpt-6-astra",
        "description": "OpenAI GPT-6 Astra (Multimodal Flagship)",
        "tier": "flagship",
        "cost_per_m": 18.0
    },
    "gpt-5.6-sol-pro": {
        "provider": "openai",
        "real_id": "openai/gpt-5.6-sol-pro",
        "description": "OpenAI GPT-5.6 Sol Pro (High-End Reasoning Engine)",
        "tier": "flagship",
        "cost_per_m": 16.0
    },
    "gpt-5.6-sol": {
        "provider": "openai",
        "real_id": "openai/gpt-5.6-sol",
        "description": "OpenAI GPT-5.6 Sol (Deep Reasoning)",
        "tier": "flagship",
        "cost_per_m": 12.0
    },
    "claude-opus-5.5": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-opus-5.5",
        "description": "Anthropic Claude Opus 5.5 (Flagship Complex Reasoning & Math)",
        "tier": "ultra_frontier",
        "cost_per_m": 22.0
    },
    "claude-fable-5.1": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-fable-5.1",
        "description": "Anthropic Claude Fable 5.1 (High Intelligence Flagship)",
        "tier": "flagship",
        "cost_per_m": 15.0
    },
    "claude-sonnet-5.5": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-sonnet-5.5",
        "description": "Anthropic Claude Sonnet 5.5 (Balanced Workhorse)",
        "tier": "balanced",
        "cost_per_m": 3.0
    },
    "claude-3-7-sonnet": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-3-7-sonnet",
        "description": "Anthropic Claude 3.7 Sonnet (Frontier Hybrid Reasoning & Coding)",
        "tier": "ultra_frontier",
        "cost_per_m": 15.0
    },
    "claude-3-5-sonnet": {
        "provider": "anthropic",
        "real_id": "anthropic/claude-3-5-sonnet-20241022",
        "description": "Anthropic Claude 3.5 Sonnet (High-Intelligence Workhorse)",
        "tier": "flagship",
        "cost_per_m": 15.0
    },
    "gpt-4o": {
        "provider": "openai",
        "real_id": "openai/gpt-4o",
        "description": "OpenAI GPT-4o (Flagship Multimodal Intelligence)",
        "tier": "flagship",
        "cost_per_m": 10.0
    },
    "o1": {
        "provider": "openai",
        "real_id": "openai/o1",
        "description": "OpenAI o1 (Advanced Deep Chain-of-Thought Reasoning)",
        "tier": "ultra_frontier",
        "cost_per_m": 20.0
    },
    "o3-mini": {
        "provider": "openai",
        "real_id": "openai/o3-mini",
        "description": "OpenAI o3-mini (High-Speed Reasoning Champion)",
        "tier": "reasoning_cheap",
        "cost_per_m": 4.4
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "real_id": "google/gemini-2.5-pro",
        "description": "Google Gemini 2.5 Pro (Frontier Multimodal & Mega Context)",
        "tier": "flagship",
        "cost_per_m": 5.0
    },
    "gemini-2.5-flash": {
        "provider": "google",
        "real_id": "google/gemini-2.5-flash",
        "description": "Google Gemini 2.5 Flash (Ultra-Fast 1M+ Context Workhorse)",
        "tier": "balanced",
        "cost_per_m": 0.3
    },
    "qwen-2.5-coder-32b": {
        "provider": "deepseek",
        "real_id": "qwen/qwen-2.5-coder-32b-instruct",
        "description": "Qwen 2.5 Coder 32B (SOTA Open Source Code Specialist)",
        "tier": "code",
        "cost_per_m": 0.8
    },
    "o3-pro": {
        "provider": "openai",
        "real_id": "openai/o3-pro",
        "description": "OpenAI o3-pro (Extended Chain-of-Thought Reasoning)",
        "tier": "ultra_frontier",
        "cost_per_m": 20.0
    },

    # ── Code & Balanced Workhorses ($0.5 - $1.5 / 1M tokens) ──
    "codestral-latest": {
        "provider": "mistral",
        "real_id": "mistral/codestral-latest",
        "description": "Mistral Codestral (SOTA Dedicated Code Engine)",
        "tier": "code",
        "cost_per_m": 1.0
    },
    "gemini-3.6-flash": {
        "provider": "google",
        "real_id": "gemini/gemini-3.6-flash",
        "description": "Google Gemini 3.6 Flash (Fast Architecture & Huge Context)",
        "tier": "balanced",
        "cost_per_m": 0.5
    },

    # ── Mega-Context & Document Tier ($1.5 / 1M tokens) ──
    "kimi-k3": {
        "provider": "moonshot",
        "real_id": "moonshotai/kimi-k3",
        "description": "Kimi Moonshot K3 (2M+ Mega-Context Analysis)",
        "tier": "mega_context",
        "cost_per_m": 1.5
    },
    "kimi-k2.7-code": {
        "provider": "moonshot",
        "real_id": "moonshotai/kimi-k2.7-code",
        "description": "Kimi Moonshot K2.7 Code Specialist",
        "tier": "code",
        "cost_per_m": 1.2
    },

    # ── Ultra-Low Cost & Fast Tier ($0.1 - $0.8 / 1M tokens) ──
    "deepseek-r1": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-r1",
        "description": "DeepSeek R1 (Advanced Open Reasoning)",
        "tier": "reasoning_cheap",
        "cost_per_m": 0.8
    },
    "deepseek-v3.2": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-v3.2",
        "description": "DeepSeek V3.2 (Cost-Performance Leader)",
        "tier": "budget",
        "cost_per_m": 0.27
    },
    "deepseek-v3": {
        "provider": "deepseek",
        "real_id": "deepseek/deepseek-chat",
        "description": "DeepSeek V3 (SOTA Value Flagship)",
        "tier": "budget",
        "cost_per_m": 0.27
    },
    "groq-gpt120b": {
        "provider": "groq",
        "real_id": "groq/openai/gpt-oss-120b",
        "description": "Groq GPT-OSS-120B (Ultra-Fast 300+ tok/s)",
        "tier": "budget",
        "cost_per_m": 0.15
    },
    "nemotron-3-super": {
        "provider": "nvidia",
        "real_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "description": "NVIDIA Nemotron 3 Super 120B (Open Engine)",
        "tier": "budget",
        "cost_per_m": 0.2
    }
}

BASELINE_COST_PER_M = 15.0  # Industry standard expensive frontier baseline

class SmartRouter:
    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "routed_by_tier": {"flagship": 0, "balanced": 0, "code": 0, "budget": 0, "mega_context": 0},
            "total_tokens_processed": 0,
            "estimated_dollars_saved": 0.0
        }

    def classify_complexity(self, prompt: str) -> Tuple[str, str]:
        """
        Classifies prompt into optimal tier based on length, intent, and complexity signals.
        Returns: (tier_name, selected_model_id)
        """
        total_len = len(prompt)

        # 1. Mega-Context Check (Large documents, logs, book chapters)
        if total_len > 40000:
            return "mega_context", "kimi-k3"

        # 2. Deep Reasoning Signals (Formal logic, mathematical proofs, architectural specs)
        deep_signals = [
            r"\b(prove|theorem|derivation|formal proof)\b",
            r"\b(system architecture|distributed consensus|kernel driver)\b",
            r"\b(reverse engineer|cryptographic analysis)\b"
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in deep_signals):
            return "flagship", "claude-fable-5.1"

        # 3. Dedicated Code Signals
        code_signals = [
            r"\b(def |class |function |const |import |from |SELECT |CREATE TABLE|async def)\b",
            r"\b(refactor|debug|unit test|pytest|npm test|dockerfile|regex)\b",
            r"```[a-z]*\n"
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in code_signals):
            return "code", "codestral-latest"

        # 4. Standard / Simple queries (Summary, translation, casual Q&A, format JSON)
        simple_signals = [
            r"\b(translate|summarize|hello|hi|what is|explain like i'm 5|format as json)\b",
            r"^[\w\s\?\.]{1,120}$"  # short simple questions
        ]
        if any(re.search(pat, prompt, re.IGNORECASE) for pat in simple_signals) or total_len < 300:
            return "budget", "groq-gpt120b"

        # Default balanced
        return "balanced", "gemini-3.6-flash"

    def resolve_model(self, requested_model: str, prompt_text: str) -> Tuple[str, Dict[str, Any], bool]:
        """
        Resolves model alias or auto-routes.
        Returns: (effective_model_id, model_info, was_auto_routed)
        """
        req_clean = requested_model.strip().lower()

        # Auto-Routing requested by client
        if req_clean in ["auto", "smart", "qast-auto", "default", ""]:
            tier, target_model = self.classify_complexity(prompt_text)
            info = MODEL_CATALOG[target_model]
            return target_model, info, True

        # Exact match in catalog
        if req_clean in MODEL_CATALOG:
            return req_clean, MODEL_CATALOG[req_clean], False

        # Fuzzy match for popular aliases
        for key, val in MODEL_CATALOG.items():
            if req_clean in key or key in req_clean:
                return key, val, False

        # Fallback to requested as direct ID
        return requested_model, {
            "provider": "openrouter",
            "real_id": requested_model,
            "description": f"Direct Pass-through: {requested_model}",
            "tier": "custom",
            "cost_per_m": 10.0
        }, False

    def record_transaction(self, model_key: str, est_tokens: int):
        self.stats["total_requests"] += 1
        self.stats["total_tokens_processed"] += est_tokens
        
        info = MODEL_CATALOG.get(model_key, {"tier": "custom", "cost_per_m": 10.0})
        tier = info.get("tier", "custom")
        if tier in self.stats["routed_by_tier"]:
            self.stats["routed_by_tier"][tier] += 1

        # Calculate savings vs baseline frontier price
        actual_cost = (est_tokens / 1_000_000) * info.get("cost_per_m", 5.0)
        baseline_cost = (est_tokens / 1_000_000) * BASELINE_COST_PER_M
        savings = max(0.0, baseline_cost - actual_cost)
        self.stats["estimated_dollars_saved"] += savings

router = SmartRouter()
