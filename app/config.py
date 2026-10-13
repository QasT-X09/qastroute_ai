"""
Qastroute AI - Configuration & Environment Policy.
Strictly zero hardcoded secrets. All credentials loaded via os.getenv.
Fails closed in production if required security variables are absent.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("qastroute.config")

# Load local .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Security & Master Admin Tokens
QASTROUTE_API_KEY = os.getenv("QASTROUTE_API_KEY", "qast-live-demo-key" if not IS_PRODUCTION else "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", QASTROUTE_API_KEY)

# Authentication requirement policy
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false" if not IS_PRODUCTION else "true").lower() in ("true", "1", "yes")

# In production, enforce that a real master / admin key is provided and not the default
if IS_PRODUCTION:
    if not QASTROUTE_API_KEY or QASTROUTE_API_KEY == "qast-live-demo-key":
        logger.critical("PRODUCTION FATAL: QASTROUTE_API_KEY cannot be empty or default in production.")
        raise RuntimeError("Production security violation: QASTROUTE_API_KEY must be set to a secure secret.")

# Trusted reverse proxies for forwarded header extraction (CWE-359 protection)
TRUSTED_PROXIES = {
    p.strip() for p in os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1,localhost").split(",") if p.strip()
}

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

# Optional Local FCC multi-model gateway bridge (Free Claude Code on 127.0.0.1:8082)
FCC_LOCAL_GATEWAY = os.getenv("FCC_LOCAL_GATEWAY", "http://127.0.0.1:8082")
ENABLE_LOCAL_BRIDGE = os.getenv("ENABLE_LOCAL_BRIDGE", "true").lower() in ("true", "1", "yes")
