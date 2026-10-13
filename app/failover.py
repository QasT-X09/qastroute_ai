"""
Qastroute AI - Zero-Downtime Failover Cascade & Smart Budget Guard.
Architected via FCC Multi-Model Orchestra (Codestral + GPT-OSS-120B).
Zero hardcoded credentials, SQLite-persisted daily quotas.
"""

import os
import time
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

# Fallback Cascade Routing Map for Frontier 2026 Models
DEFAULT_FAILOVER_CHAINS: Dict[str, List[str]] = {
    "claude-opus-5.5": ["gpt-6.1-sol-pro", "deepseek-r1", "groq-gpt120b"],
    "claude-fable-5.1": ["gpt-6-astra", "deepseek-r1", "groq-gpt120b"],
    "claude-sonnet-5.5": ["gpt-6-astra", "deepseek-v3", "groq-gpt120b"],
    "gpt-6.1-sol-pro": ["claude-opus-5.5", "deepseek-r1", "groq-gpt120b"],
    "gpt-6-astra": ["claude-sonnet-5.5", "deepseek-v3", "groq-gpt120b"],
    "kimi-k3": ["claude-sonnet-5.5", "deepseek-r1", "groq-gpt120b"],
    "deepseek-r1": ["codestral-latest", "groq-gpt120b"],
    "codestral-latest": ["groq-gpt120b"],
    "groq-gpt120b": []
}

class FailoverCascade:
    """Manages automatic failover routing when primary providers fail."""
    def __init__(self, chains: Optional[Dict[str, List[str]]] = None):
        self.chains = chains or DEFAULT_FAILOVER_CHAINS

    def get_fallbacks(self, model: str) -> List[str]:
        return self.chains.get(model, ["groq-gpt120b"])

failover_cascade = FailoverCascade()


class BudgetGuard:
    """
    Enforces daily spend ceilings. Automatically downshifts traffic to free/budget
    models (Groq / Codestral) when daily spending cap is reached.
    """
    def __init__(self, db_path: Optional[Path] = None, daily_cap_usd: Optional[float] = None):
        if db_path is None:
            data_dir = Path(__file__).resolve().parent.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "qastroute.db"
        self.db_path = db_path
        self.daily_cap_usd = daily_cap_usd or float(os.getenv("DAILY_BUDGET_CAP_USD", "50.0"))
        self.free_models = ["groq-gpt120b", "codestral-latest"]
        self._lock = threading.Lock()
        self._cache: Dict[str, float] = {}
        self._ensure_db()
        self._load_today()

    def _ensure_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_spend (
                    date TEXT PRIMARY KEY,
                    amount REAL NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def _today_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_today(self):
        today = self._today_str()
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT amount FROM daily_spend WHERE date = ?", (today,))
            row = cursor.fetchone()
            self._cache[today] = float(row[0]) if row else 0.0

    def record_spend(self, cost_usd: float):
        if cost_usd <= 0:
            return
        today = self._today_str()
        with self._lock, sqlite3.connect(str(self.db_path)) as conn:
            new_amount = self._cache.get(today, 0.0) + cost_usd
            self._cache[today] = new_amount
            conn.execute(
                "INSERT INTO daily_spend (date, amount) VALUES (?, ?) ON CONFLICT(date) DO UPDATE SET amount = ?",
                (today, new_amount, new_amount)
            )
            conn.commit()

    def current_spend(self) -> float:
        return self._cache.get(self._today_str(), 0.0)

    def is_over_budget(self) -> bool:
        return self.current_spend() >= self.daily_cap_usd

    def remaining_budget(self) -> float:
        return max(0.0, self.daily_cap_usd - self.current_spend())

    def choose_model(self, requested_model: str) -> tuple[str, bool]:
        """
        Returns (effective_model, budget_guard_activated).
        If over daily cap, downshifts to free model.
        """
        if self.is_over_budget():
            # Auto-downshift to zero-cost local/Groq model
            return self.free_models[0], True
        return requested_model, False

budget_guard = BudgetGuard()
