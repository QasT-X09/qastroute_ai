"""
Qastroute AI - Configuration & Environment Policy.
Strictly zero hardcoded secrets. All credentials loaded via os.getenv.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Master Gateway Auth Token (Required for clients accessing Qastroute)
QASTROUTE_API_KEY = os.getenv("QASTROUTE_API_KEY", "qast-live-demo-key")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")

# LemonSqueezy / Paddle Webhook Secret
LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")

# Upstream Provider Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Fallback FCC local gateway endpoint if running locally
FCC_LOCAL_GATEWAY = os.getenv("FCC_LOCAL_GATEWAY", "http://127.0.0.1:8082")
