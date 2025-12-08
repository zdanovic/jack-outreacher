import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, Optional

from ..storage.state_db import get_state_db


class AccountStatus(Enum):
    """High‑level lifecycle state for an account worker."""

    ACTIVE = auto()
    PAUSED = auto()
    NEED_RELOGIN = auto()
    DISABLED = auto()
    BANNED = auto()


@dataclass
class AccountRuntimeState:
    """Mutable runtime counters and status flags for an account."""

    # Start in PAUSED until a worker successfully connects and explicitly
    # marks the account as ACTIVE. This avoids scheduling warmup actions
    # before the Telegram client is ready.
    status: AccountStatus = AccountStatus.PAUSED
    cold_sent_today: int = 0
    last_error: Optional[str] = None
    ban_reason: Optional[str] = None
    flood_wait_until: Optional[float] = None


class GlobalState:
    """
    In‑memory global state for the orchestrator.

    This is intentionally simple for the first iteration. When the
    system matures we can add periodic persistence and richer metrics
    without changing the public API.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._accounts: Dict[str, AccountRuntimeState] = {}
        self._db = get_state_db()

    async def ensure_account(self, account_id: str) -> AccountRuntimeState:
        async with self._lock:
            state = self._accounts.get(account_id)
            if state is None:
                persisted = self._db.get_account_runtime(account_id)
                if persisted:
                    try:
                        status = AccountStatus[persisted["status"]] if persisted.get("status") else AccountStatus.PAUSED
                    except Exception:
                        status = AccountStatus.PAUSED
                    state = AccountRuntimeState(
                        status=status,
                        last_error=persisted.get("last_error"),
                        ban_reason=persisted.get("ban_reason"),
                        flood_wait_until=persisted.get("floodwait_until"),
                    )
                else:
                    state = AccountRuntimeState()
                self._accounts[account_id] = state
            return state

    async def set_status(self, account_id: str, status: AccountStatus) -> None:
        state = await self.ensure_account(account_id)
        async with self._lock:
            state.status = status
            self._db.upsert_account_runtime(
                account_id=account_id,
                status=status.name,
                last_error=state.last_error,
                ban_reason=state.ban_reason,
                floodwait_until=state.flood_wait_until,
            )

    async def get_status(self, account_id: str) -> AccountStatus:
        state = await self.ensure_account(account_id)
        return state.status


    async def set_last_error(self, account_id: str, error: Optional[str]) -> None:
        state = await self.ensure_account(account_id)
        async with self._lock:
            state.last_error = error
            self._db.upsert_account_runtime(
                account_id=account_id,
                status=state.status.name,
                last_error=error,
                ban_reason=state.ban_reason,
                floodwait_until=state.flood_wait_until,
            )

    async def set_ban_reason(self, account_id: str, reason: Optional[str]) -> None:
        state = await self.ensure_account(account_id)
        async with self._lock:
            state.ban_reason = reason
            if reason:
                state.status = AccountStatus.BANNED
            self._db.upsert_account_runtime(
                account_id=account_id,
                status=state.status.name,
                last_error=state.last_error,
                ban_reason=state.ban_reason,
                floodwait_until=state.flood_wait_until,
            )

    async def set_floodwait(self, account_id: str, seconds_from_now: Optional[float]) -> None:
        state = await self.ensure_account(account_id)
        async with self._lock:
            if seconds_from_now is None:
                state.flood_wait_until = None
            else:
                import time
                state.flood_wait_until = time.time() + max(0.0, seconds_from_now)
            self._db.upsert_account_runtime(
                account_id=account_id,
                status=state.status.name,
                last_error=state.last_error,
                ban_reason=state.ban_reason,
                floodwait_until=state.flood_wait_until,
            )

    async def get_runtime(self, account_id: str) -> AccountRuntimeState:
        return await self.ensure_account(account_id)

    async def increment_cold_sent(self, account_id: str, delta: int = 1) -> int:
        state = await self.ensure_account(account_id)
        async with self._lock:
            state.cold_sent_today += delta
            return state.cold_sent_today

    async def set_cold_sent_today(self, account_id: str, value: int) -> None:
        state = await self.ensure_account(account_id)
        async with self._lock:
            state.cold_sent_today = value

    async def reset_cold_sent_counts(self, seed_fn: Optional[Callable[[str], int]] = None) -> None:
        """
        Reset per-account cold_sent_today counters, optionally seeding
        from an external source (e.g., persisted metrics).
        """
        async with self._lock:
            for acc_id, state in self._accounts.items():
                seeded = seed_fn(acc_id) if seed_fn else 0
                state.cold_sent_today = int(seeded) if seeded is not None else 0


global_state = GlobalState()
