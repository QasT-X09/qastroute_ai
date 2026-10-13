# 🚀 Qastroute AI — Global Launch & Distribution Kit

Готовый маркетинговый и промо-пакет для вывода **Qastroute AI** в топ Hacker News, Reddit, GitHub Trending и Product Hunt.

---

## 1. 🌐 Hacker News (Show HN)
- **URL**: https://news.ycombinator.com/submit
- **Title**: `Show HN: Qastroute AI – Open-source Universal AI Gateway and Cost-Optimizer for 2026 Models`
- **Text / Body**:
```markdown
Hey HN!

We built Qastroute AI (https://github.com/QasT-X09/qastroute_ai) — an open-source, dual-protocol AI gateway and cost optimizer designed for the latest 2026 frontier models (GPT-6.1 Sol Pro, Astra Pro, Claude Opus 5.5, Claude Fable 5.1, Kimi K3, and DeepSeek R1).

### Why did we build this?
Most AI developers face two massive pain points:
1. Vendor lock-in: Switching between Anthropic's `/v1/messages` and OpenAI's `/v1/chat/completions` requires refactoring client code or managing multiple wrapper SDKs.
2. Token waste: Overpaying $15/1M tokens to Claude Opus or GPT-6.1 for trivial tasks like JSON formatting, simple greetings, or classification.

### What Qastroute does:
- Universal Dual Protocol: Drop-in replacement for any client (Cursor, Claude Code, Aider, LangChain, OpenAI/Anthropic Python SDKs). Just change `base_url="http://localhost:8000/v1"`.
- Smart Semantic Tiering (`model="auto"`): Analyzes queries in <1ms without calling an LLM. Routes simple prompts to ultra-fast/cheap models (Groq / DeepSeek), code to Codestral, and only spins up Claude Opus 5.5 / GPT-6.1 Sol Pro for deep mathematical proofs or multi-step logic.
- Zero-latency Semantic Caching: Repeat prompts return in ~0.2ms at $0 cost.
- Self-hosted & BYOK: 100% private, runs via Docker, zero hardcoded secrets.

It's completely free and open-source under Apache 2.0. We'd love your feedback, feature requests, and benchmarks!

GitHub: https://github.com/QasT-X09/qastroute_ai
Docs & Demo: http://localhost:8000
```

---

## 2. 🤖 Reddit (r/LocalLLaMA & r/selfhosted)

### Post 1: r/LocalLLaMA
- **Title**: `I built an open-source universal AI gateway with smart auto-routing between DeepSeek, Groq, Claude Opus 5.5, and GPT-6`
- **Body**:
```markdown
Hey everyone,

Whenever I build LLM pipelines or terminal coding agents, my token bill explodes because tools keep sending trivial questions to expensive frontier models.

So I built **Qastroute AI**:
- Full support for both OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) formats.
- `model="auto"` semantic classifier: automatically routes simple prompts to DeepSeek/Groq and heavy reasoning to flagship models.
- Built-in prompt caching with SHA-256 TTL.
- Local fallback bridge to FCC / local Ollama / vLLM endpoints.

Repo: https://github.com/QasT-X09/qastroute_ai

Works natively as a drop-in proxy for Cursor, Claude Code, Aider, and any OpenAI/Anthropic client. Let me know what you think!
```

### Post 2: r/selfhosted
- **Title**: `Self-hosted Universal AI Proxy: Cut your LLM bills by 60%+ with sub-millisecond auto-routing and in-memory caching`
- **Body**:
```markdown
Hi r/selfhosted,

Sharing a tool I made for self-hosting: **Qastroute AI**.
It's a single Docker container that sits between your apps (Nextcloud, OpenWebUI, Cursor, CLI agents) and LLM providers.

Features:
- Docker-ready with single-command launch (`docker compose up -d`)
- In-memory semantic prompt cache (0ms latency on repeated queries)
- Built-in developer dashboard with live latency, token counters, and cost savings telemetry
- 100% BYOK (Bring Your Own Key) architecture with zero vendor lock-in

Docker run:
`docker run -p 8000:8000 qastroute/gateway:latest`

Check it out on GitHub: https://github.com/QasT-X09/qastroute_ai
```

---

## 3. 🐱 Product Hunt Launch Checklist
- **Name**: Qastroute AI
- **Tagline**: The Universal AI Gateway & Smart Cost-Optimizer
- **Pricing**: Free (Open Source) + $29/mo Hosted Pro SaaS
- **Topics**: Artificial Intelligence, Developer Tools, Open Source, Productivity
- **Makers Comment**:
> "Hi Product Hunt! We created Qastroute AI to put an end to runaway LLM bills. With our dual OpenAI & Anthropic protocol proxy and semantic auto-routing, developers automatically route simple queries to fast models and reserve frontier models for complex tasks. Check out our open-source repo or try the hosted version!"

---

## 4. 💳 Монетизация: Подключение платежей (LemonSqueezy / Paddle)

### Как клиенты оплачивают и получают ключи:
1. Вы создаете аккаунт в [LemonSqueezy](https://lemonsqueezy.com) или [Paddle](https://paddle.com).
2. Создаете продукт: **Qastroute Pro ($29/mo)**.
3. В настройках вебхуков LemonSqueezy указываете:
   - URL: `https://your-domain.com/api/webhook/billing`
   - События: `order_created`, `subscription_created`.
4. Вебхук Qastroute автоматически:
   - Получает email покупателя.
   - Генерирует ключ вида `qr_live_xxxxxxxx`.
   - Сохраняет его в локальную базу данных (`data/qastroute.db`).
5. Деньги с LemonSqueezy/Paddle выводятся напрямую на ваш банковский счет (включая мультивалютные счета Kaspi / Halyk / Payoneer / Wise).
