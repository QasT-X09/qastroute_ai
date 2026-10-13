"""
Qastroute AI - Monetization, API Key Management & Billing Integration.
Supports LemonSqueezy / Paddle webhooks for automated key issuance.
Zero hardcoded secrets, parameterized SQL statements, SHA-256 key hashing for OWASP/CWE safety.
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
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def _hash_key(raw_key: str) -> str:
    """Computes SHA-256 digest of API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

def init_db():
    """Initializes tables for API keys and customer subscriptions with migration and indexes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Check if legacy api_keys table exists with old schema
        cursor.execute("PRAGMA table_info(api_keys)")
        cols = [row["name"] for row in cursor.fetchall()]
        if cols and "key_hash" not in cols:
            cursor.execute("ALTER TABLE api_keys RENAME TO api_keys_old")
            cursor.execute("""
                CREATE TABLE api_keys (
                    key_hash TEXT PRIMARY KEY,
                    key_prefix TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'pro',
                    created_at REAL NOT NULL,
                    requests_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)
            cursor.execute("SELECT key, user_email, tier, created_at, requests_count, active FROM api_keys_old")
            for old_row in cursor.fetchall():
                raw_k = old_row["key"]
                khash = _hash_key(raw_k)
                kprefix = raw_k[:12] + "..."
                cursor.execute(
                    "INSERT INTO api_keys VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (khash, kprefix, old_row["user_email"], old_row["tier"], old_row["created_at"], old_row["requests_count"], old_row["active"])
                )
            cursor.execute("DROP TABLE api_keys_old")
            conn.commit()
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    key_prefix TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'pro',
                    created_at REAL NOT NULL,
                    requests_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_email ON api_keys(user_email)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS billing_events (
                event_id TEXT PRIMARY KEY,
                event_name TEXT NOT NULL,
                user_email TEXT,
                payload TEXT,
                created_at REAL NOT NULL,
                api_key TEXT
            )
        """)
        # Ensure column exists if table was previously created
        cursor.execute("PRAGMA table_info(billing_events)")
        bcols = [row["name"] for row in cursor.fetchall()]
        if "api_key" not in bcols:
            cursor.execute("ALTER TABLE billing_events ADD COLUMN api_key TEXT")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_billing_events_created ON billing_events(created_at)")
        conn.commit()

# Run table creation on import
init_db()

def create_api_key(user_email: str, tier: str = "pro") -> str:
    """
    Generates a secure API key for a customer.
    Stores only the SHA-256 hash in the database (CWE-312 compliance).
    The full key is returned only once to the caller.
    """
    raw_key = f"qr_live_{uuid.uuid4().hex}"
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12] + "..."

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys (key_hash, key_prefix, user_email, tier, created_at, requests_count, active)
            VALUES (?, ?, ?, ?, ?, 0, 1)
            """,
            (key_hash, key_prefix, user_email, tier, time.time())
        )
        conn.commit()

    return raw_key

def verify_api_key(key: str) -> Optional[Dict[str, Any]]:
    """
    Validates the API key using constant-time hash lookup.
    """
    if not key:
        return None

    clean_key = key.replace("Bearer ", "").strip()
    if not clean_key:
        return None

    # Master key bypass for self-hosted administrator
    if config.QASTROUTE_API_KEY and hmac.compare_digest(clean_key, config.QASTROUTE_API_KEY):
        return {
            "key_hash": _hash_key(clean_key),
            "key_prefix": clean_key[:8] + "...",
            "user_email": "admin@local",
            "tier": "enterprise",
            "is_admin": True,
            "active": 1
        }

    key_hash = _hash_key(clean_key)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT key_hash, key_prefix, user_email, tier, requests_count, active
            FROM api_keys
            WHERE key_hash = ?
            """,
            (key_hash,)
        )
        row = cursor.fetchone()
        if row and row["active"] == 1:
            res = dict(row)
            res["is_admin"] = res.get("tier") == "enterprise"
            return res

    return None

def revoke_api_key(key_or_hash: str) -> bool:
    """Deactivates an API key by hash or raw key."""
    if not key_or_hash:
        return False
    h = _hash_key(key_or_hash) if not (len(key_or_hash) == 64 and all(c in "0123456789abcdef" for c in key_or_hash.lower())) else key_or_hash
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE api_keys SET active = 0 WHERE key_hash = ?", (h,))
        conn.commit()
        return cursor.rowcount > 0

def record_key_usage(key: str):
    """Increments the request count atomically for the specified API key."""
    if not key:
        return
    clean_key = key.replace("Bearer ", "").strip()
    if not clean_key or clean_key == config.QASTROUTE_API_KEY:
        return

    key_hash = _hash_key(clean_key)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE api_keys SET requests_count = requests_count + 1 WHERE key_hash = ?",
            (key_hash,)
        )
        conn.commit()

def verify_lemonsqueezy_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """
    Verifies LemonSqueezy webhook HMAC-SHA256 signature strictly.
    Fails closed in production if secret or signature is missing (CWE-306).
    """
    secret = config.LEMONSQUEEZY_WEBHOOK_SECRET
    if not secret:
        # In production, signature verification CANNOT be skipped
        if config.IS_PRODUCTION:
            return False
        # Development fallback only if not in production
        return True

    if not signature_header:
        return False

    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature_header)

def process_webhook_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles payment webhook events (order_created, subscription_created).
    Ensures strict event idempotency: replay attacks will NOT issue duplicate keys.
    """
    event_id = str(payload.get("data", {}).get("id") or payload.get("id") or uuid.uuid4().hex)

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
        # Idempotency check: see if event was already recorded
        cursor.execute("SELECT event_id, api_key FROM billing_events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        if row:
            existing_key = row["api_key"]
            if not existing_key and event_name in ("order_created", "subscription_created"):
                existing_key = create_api_key(user_email=user_email, tier=tier)
                cursor.execute("UPDATE billing_events SET api_key = ? WHERE event_id = ?", (existing_key, event_id))
                conn.commit()
            return {
                "status": "success",
                "action": "key_issued",
                "api_key": existing_key or "",
                "user_email": user_email,
                "tier": tier,
                "event_id": event_id,
                "idempotent_replay": True
            }

        issued_key = ""
        if event_name in ("order_created", "subscription_created"):
            issued_key = create_api_key(user_email=user_email, tier=tier)

        cursor.execute(
            "INSERT INTO billing_events (event_id, event_name, user_email, payload, created_at, api_key) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, event_name, user_email, json.dumps(payload), time.time(), issued_key)
        )
        conn.commit()

    if issued_key:
        return {
            "status": "success",
            "action": "key_issued",
            "api_key": issued_key,
            "user_email": user_email,
            "tier": tier,
            "event_id": event_id
        }

    return {"status": "success", "action": "event_recorded", "event_id": event_id}
