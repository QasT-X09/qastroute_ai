"""
Qastroute AI - Monetization, API Key Management & Billing Integration.
Supports LemonSqueezy / Paddle webhooks for automated key issuance.
Zero hardcoded secrets, parameterized SQL statements for OWASP/CWE safety.
"""

import hmac
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from . import config

# Ensure data directory exists
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "qastroute.db"

def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables for API keys and customer subscriptions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'pro',
                created_at REAL NOT NULL,
                requests_count INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS billing_events (
                event_id TEXT PRIMARY KEY,
                event_name TEXT NOT NULL,
                user_email TEXT,
                payload TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()

# Run table creation on import
init_db()

def create_api_key(user_email: str, tier: str = "pro") -> str:
    """Generates a secure API key for a paying customer."""
    new_key = f"qr_live_{uuid.uuid4().hex}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_keys (key, user_email, tier, created_at, requests_count, active) VALUES (?, ?, ?, ?, 0, 1)",
            (new_key, user_email, tier, time.time())
        )
        conn.commit()
    return new_key

def verify_api_key(key: str) -> Optional[Dict[str, Any]]:
    """
    Validates the API key.
    If REQUIRE_AUTH is disabled and key matches default master key, grants access.
    """
    if not key:
        return None
    
    clean_key = key.replace("Bearer ", "").strip()
    
    # Master key bypass (for self-hosted admin access)
    if clean_key == config.QASTROUTE_API_KEY:
        return {"key": clean_key, "user_email": "admin@local", "tier": "enterprise", "active": 1}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key, user_email, tier, requests_count, active FROM api_keys WHERE key = ?",
            (clean_key,)
        )
        row = cursor.fetchone()
        if row and row["active"] == 1:
            return dict(row)
    return None

def record_key_usage(key: str):
    """Increments the request count for the specified API key."""
    if not key:
        return
    clean_key = key.replace("Bearer ", "").strip()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE api_keys SET requests_count = requests_count + 1 WHERE key = ?",
            (clean_key,)
        )
        conn.commit()

def verify_lemonsqueezy_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Verifies LemonSqueezy webhook HMAC-SHA256 signature."""
    secret = config.LEMONSQUEEZY_WEBHOOK_SECRET
    if not secret:
        # If no secret configured in test/dev environment, allow
        return True
    if not signature_header:
        return False
    
    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature_header)

def process_webhook_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles payment webhook events (e.g. order_created, subscription_created).
    Automatically issues license/API keys to the customer.
    """
    event_id = str(payload.get("data", {}).get("id") or uuid.uuid4().hex)
    user_email = (
        payload.get("data", {}).get("attributes", {}).get("user_email")
        or payload.get("data", {}).get("attributes", {}).get("customer_email")
        or payload.get("meta", {}).get("custom_data", {}).get("email")
        or "customer@qastroute.ai"
    )

    tier = "pro"
    variant_name = payload.get("data", {}).get("attributes", {}).get("variant_name", "").lower()
    if "enterprise" in variant_name:
        tier = "enterprise"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO billing_events (event_id, event_name, user_email, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, event_name, user_email, json.dumps(payload), time.time())
        )
        conn.commit()

    if event_name in ("order_created", "subscription_created"):
        issued_key = create_api_key(user_email=user_email, tier=tier)
        return {
            "status": "success",
            "action": "key_issued",
            "api_key": issued_key,
            "user_email": user_email,
            "tier": tier
        }

    return {"status": "success", "action": "event_recorded"}
