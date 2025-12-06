from __future__ import annotations

"""
Metrics store backed by SQLite (via StateDB).

Each increment is applied directly to the `metrics` table in
orchestrator_state.db, keyed by (date, account_id).
"""

import asyncio
from datetime import date

from src.storage.state_db import get_state_db


class MetricsStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._db = get_state_db()

    async def incr(self, account_id: str, field: str, delta: int = 1) -> None:
        """
        Increment a specific metric field for an account for today's date.
        Unknown fields are ignored.
        """
        valid_fields = {
            "cold_sent",
            "cold_failed",
            "replies_received",
            "hot_leads",
            "warm_leads",
            "cold_leads",
            "floodwait_events",
            "warmup_actions",
        }
        if field not in valid_fields:
            return

        today = date.today().isoformat()
        async with self._lock:
            cur = self._db.conn.cursor()
            # Ensure row exists, then increment the selected field.
            cur.execute(
                """
                INSERT INTO metrics (date, account_id)
                VALUES (?, ?)
                ON CONFLICT(date, account_id) DO NOTHING;
                """,
                (today, account_id),
            )
            cur.execute(
                f"""
                UPDATE metrics
                SET {field} = COALESCE({field}, 0) + ?
                WHERE date = ? AND account_id = ?;
                """,
                (delta, today, account_id),
            )
            self._db.conn.commit()

    def get_today_field(self, account_id: str, field: str) -> int:
        """
        Return today's value for a metric field (0 if missing).
        """
        valid_fields = {
            "cold_sent",
            "cold_failed",
            "replies_received",
            "hot_leads",
            "warm_leads",
            "cold_leads",
            "floodwait_events",
            "warmup_actions",
        }
        if field not in valid_fields:
            return 0
        cur = self._db.conn.cursor()
        cur.execute(
            f"SELECT COALESCE({field},0) FROM metrics WHERE date=? AND account_id=?;",
            (date.today().isoformat(), account_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_today_field_sum(self, field: str) -> int:
        """
        Return today's sum across accounts for a metric field.
        """
        valid_fields = {
            "cold_sent",
            "cold_failed",
            "replies_received",
            "hot_leads",
            "warm_leads",
            "cold_leads",
            "floodwait_events",
            "warmup_actions",
        }
        if field not in valid_fields:
            return 0
        cur = self._db.conn.cursor()
        cur.execute(
            f"SELECT COALESCE(SUM({field}),0) FROM metrics WHERE date=?;",
            (date.today().isoformat(),),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


metrics_store = MetricsStore()
