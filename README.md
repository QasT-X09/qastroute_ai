# 🚀 Qastroute AI — The Universal AI Gateway & Smart Cost-Optimizer

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Status: Production Ready](https://img.shields.io/badge/Status-Production%20Ready-success.svg)]()
[![Cost Savings](https://img.shields.io/badge/Cost%20Savings-70--80%25-10b981.svg)]()
[![Dual Protocol](https://img.shields.io/badge/Protocol-OpenAI%20%7C%20Anthropic-3b82f6.svg)]()
[![Failover](https://img.shields.io/badge/Failover-Zero--Downtime-8b5cf6.svg)]()

> **Cut your enterprise LLM bills by 70–80% with zero code changes.**  
> Drop-in replacement for OpenAI and Anthropic SDKs. Single unified API gateway for **Claude 3.7 Sonnet, GPT-4o, o3-mini, Gemini 2.5 Flash, DeepSeek R1/V3, and Qwen 2.5 Coder**.

---

## ⚡ The Problem: The 20,000 USD/Month Frontier Model Tax
Most software engineering teams send **100% of their prompts** to expensive frontier models (costing 15 to 25 USD per 1M tokens) like Claude 3.7 Sonnet or GPT-4o.  
In reality, **over 70% of production prompts** are simple JSON formatting, classification, basic translations, or boilerplate queries that cost-effective workhorse models (DeepSeek V3, Gemini 2.5 Flash, Groq) solve with identical accuracy at **1/100th of the cost**.

## 💡 The Solution: Qastroute AI
Qastroute AI sits between your application and AI providers. It analyzes prompt complexity in **1 millisecond** and automatically routes each query to the most cost-effective model.

```
                              ┌───► Anthropic (Claude 3.7 Sonnet / Claude 3.5 Sonnet)
                              ├───► OpenAI (GPT-4o / o3-mini / o1)
[ Your App / Cursor / IDE ] ──► [ Qastroute AI Gateway ] ├───► Google (Gemini 2.5 Flash / Pro — 1M+ Context)
                              ├───► DeepSeek (R1 Reasoning / V3)
                              └───► Mistral & Qwen (Codestral / Qwen 2.5 Coder)
```

---

## 🌟 Key Features

* **✨ Smart Semantic Auto-Tiering (`model="auto"`):**
  * Simple formatting / greetings → Routed to ultra-fast DeepSeek V3 / Groq (0.15 to 0.27 USD per 1M tokens)
  * Coding tasks / refactoring → Routed to Qwen 2.5 Coder & Codestral (0.80 to 1.00 USD per 1M tokens)
  * Mega documents (>40k chars) → Routed to Gemini 2.5 Flash / Kimi (1M+ context)
  * Deep mathematical proofs / architecture → Routed to Claude 3.7 Sonnet / o3-mini / o1 (15 to 20 USD per 1M tokens)
* **🔄 Dual Protocol Support:** 100% compatible with both OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) SDKs.
* **🛡️ Zero-Downtime Failover Cascade:** Automatically reroutes requests to equivalent backup models if an upstream provider hits rate limits (429) or outages (503).
* **⚡ Server-Sent Events (SSE) Streaming:** Native `stream: true` token-by-token output compatible with Cursor, Claude Code, and Aider.
* **🛑 Smart Budget Guard:** Configurable daily spend caps that automatically downshift traffic to free models when limits are hit.
* **📊 Live Web Dashboard & Badges:** Real-time counter of dollars saved, token metrics, visual testing playground, and dynamic SVG badges.
* **🔒 Enterprise Security Hardening:** Sliding-window rate limiter per IP, payload size guards, and strict OWASP/CWE compliance.

---

## 🚀 Quickstart (30 Seconds)

### 1. Install & Run
```bash
git clone https://github.com/QasT-X09/qastroute_ai.git
cd qastroute_ai
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at `http://localhost:8000` to access the **Live Dashboard and Playground**.

---

## 💻 1-Line Integration

### Python (OpenAI SDK)
```python
from openai import OpenAI

# Change exactly 1 line: point base_url to Qastroute
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="qast-live-demo-key"
)

response = client.chat.completions.create(
    model="auto",  # Or specify 'claude-3-7-sonnet', 'gpt-4o', 'deepseek-r1'
    messages=[{"role": "user", "content": "Format this list into JSON: Apple, Banana, Cherry"}]
)

print(response.choices[0].message.content)
```

### Python (Anthropic SDK)
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="qast-live-demo-key"
)

message = client.messages.create(
    model="claude-3-7-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a distributed consensus proof"}]
)

print(message.content[0].text)
```

---

## 📋 Supported Model Matrix

| Model Alias | Provider | Best Used For | Typical Cost / 1M |
|---|---|---|---|
| `claude-3-7-sonnet` | Anthropic | Frontier Hybrid Reasoning & Complex Code | ~15.00 USD |
| `claude-3-5-sonnet` | Anthropic | High-Intelligence Workhorse | ~15.00 USD |
| `gpt-4o` | OpenAI | Flagship Multimodal Intelligence | ~10.00 USD |
| `o1` | OpenAI | Advanced Deep Chain-of-Thought Reasoning | ~20.00 USD |
| `o3-mini` | OpenAI | High-Speed Reasoning Champion | ~4.40 USD |
| `gemini-2.5-pro` | Google | SOTA Multimodal & Mega-Context Analysis | ~5.00 USD |
| `gemini-2.5-flash` | Google | Ultra-Fast 1M+ Context Workhorse | ~0.30 USD |
| `qwen-2.5-coder-32b` | Alibaba / DeepSeek | SOTA Dedicated Code Generation | ~0.80 USD |
| `codestral-latest` | Mistral | High-Throughput Code Engine | ~1.00 USD |
| `deepseek-r1` | DeepSeek | Open Reasoning Champion | ~0.80 USD |
| `deepseek-v3` | DeepSeek | High-Performance General Tasks | ~0.27 USD |
| `groq-gpt120b` | Groq | Ultra-Fast 300+ tok/s Simple Tasks | ~0.15 USD |

---

## 📄 License
MIT License. Free for personal and commercial open-source usage.
