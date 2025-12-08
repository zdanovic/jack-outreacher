from __future__ import annotations

import random
import time
from typing import List, Callable, Dict, Any

from .actions import Action, ActionType
from ..storage.leads_store import LeadsStore
from ..core.rate_limiter import RateLimiter


SEND_INTERVAL_MIN = 900.0   # 15 minutes
SEND_INTERVAL_MAX = 3600.0  # 60 minutes


class OutreachEngine:
    """
    Simple outreach planner that schedules SEND_COLD_DM actions
    based on available leads and rate limits.

    This initial version uses a static, safe test message instead of
    AI‑generated content to validate the full cycle.
    """

    def __init__(
        self,
        leads_store: LeadsStore,
        rate_limiter: RateLimiter,
        settings_provider: Callable[[], Dict[str, Any]] | None = None,
    ) -> None:
        self._leads = leads_store
        self._rate_limiter = rate_limiter
        self._settings_provider = settings_provider

    async def plan_batch_for_account(self, account_id: str, max_per_batch: int = 1) -> List[Action]:
        """
        Reserve up to `max_per_batch` leads for the account and produce
        SEND_COLD_DM actions with gentle timing jitter.
        """
        cfg = self._settings_provider() if self._settings_provider else {}
        outreach_cfg = cfg.get("outreach", {}) if isinstance(cfg, dict) else {}

        if outreach_cfg.get("enabled") is False:
            return []

        send_min = float(outreach_cfg.get("send_interval_min", SEND_INTERVAL_MIN))
        send_max = float(outreach_cfg.get("send_interval_max", SEND_INTERVAL_MAX))
        max_batch = int(outreach_cfg.get("max_per_batch", max_per_batch))
        max_per_batch = max_batch or max_per_batch

        # Avoid lining up multiple sends at the same second for different accounts.
        base_delay_jitter = random.uniform(0.0, 30.0)

        actions: List[Action] = []
        for _ in range(max_per_batch):
            if not await self._rate_limiter.can_send_cold(account_id):
                break
            lead = self._leads.reserve_lead_for_account(account_id)
            if not lead:
                break

            delay = random.uniform(send_min, send_max)
            earliest = time.time() + delay + base_delay_jitter
            actions.append(
                Action(
                    account_id=account_id,
                    type=ActionType.SEND_COLD_DM,
                    earliest_start_ts=earliest,
                    context={
                        "username": lead.username,
                        "name": lead.name,
                        "tag": lead.tag,
                        "source": lead.source,
                    },
                )
            )
        return actions

    def next_batch_interval(self) -> float:
        """
        Interval between outreach planning cycles.
        """
        cfg = self._settings_provider() if self._settings_provider else {}
        outreach_cfg = cfg.get("outreach", {}) if isinstance(cfg, dict) else {}
        send_min = float(outreach_cfg.get("send_interval_min", SEND_INTERVAL_MIN))
        send_max = float(outreach_cfg.get("send_interval_max", SEND_INTERVAL_MAX))
        return random.uniform(send_min, send_max)
