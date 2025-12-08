import asyncio
import datetime as _dt
from typing import Dict

from .config import LimitsConfig
from .state import global_state
from .metrics import metrics_store


class RateLimiter:
    """
    Simple in‑memory rate limiter for cold DMs and heavy actions.

    This is intentionally conservative and focuses on daily limits.
    More granular (per‑minute) limits can be added later if needed.
    """

    def __init__(self, limits: LimitsConfig, seed_from_db: bool = True) -> None:
        self._limits = limits
        self._lock = asyncio.Lock()
        # Seed from persisted metrics to avoid resets on restart.
        self._global_cold_sent_today: int = metrics_store.get_today_field_sum("cold_sent") if seed_from_db else 0
        self._last_reset_date: str = self._today_str()
        self._seed_from_db = seed_from_db

    @staticmethod
    def _today_str() -> str:
        return _dt.date.today().isoformat()

    async def _maybe_reset(self) -> None:
        today = self._today_str()
        if today != self._last_reset_date:
            async with self._lock:
                if today != self._last_reset_date:
                    self._last_reset_date = today
                    if self._seed_from_db:
                        self._global_cold_sent_today = metrics_store.get_today_field_sum("cold_sent")
                        seed_fn = lambda acc_id: metrics_store.get_today_field(acc_id, "cold_sent")
                    else:
                        self._global_cold_sent_today = 0
                        seed_fn = lambda _acc_id: 0
                    # Reset per-account counters to today's persisted values (or zero if not seeding).
                    await global_state.reset_cold_sent_counts(seed_fn)

    async def can_send_cold(self, account_id: str) -> bool:
        """
        Check whether the given account is allowed to send a new cold DM
        under the current daily limits.
        """
        await self._maybe_reset()
        async with self._lock:
            # Global limit check
            if self._global_cold_sent_today >= self._limits.max_cold_global_per_day:
                return False

        # Per‑account limit check delegated to GlobalState counters.
        current = await global_state.ensure_account(account_id)
        if self._seed_from_db and current.cold_sent_today == 0:
            # Seed from persisted metrics for today.
            seeded = metrics_store.get_today_field(account_id, "cold_sent")
            await global_state.set_cold_sent_today(account_id, seeded)
            current = await global_state.ensure_account(account_id)
        if current.cold_sent_today >= self._limits.max_cold_per_account_per_day:
            return False
        return True

    async def register_cold_sent(self, account_id: str) -> None:
        await self._maybe_reset()
        async with self._lock:
            self._global_cold_sent_today += 1
        await global_state.increment_cold_sent(account_id, 1)

    def update_limits(self, limits: LimitsConfig) -> None:
        """
        Update limit values at runtime (used by settings overrides).
        """
        self._limits = limits
