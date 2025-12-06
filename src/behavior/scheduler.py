import asyncio
import time
from typing import Dict, List, Optional

from .actions import Action


class GlobalScheduler:
    """
    Extremely simple scheduler placeholder.

    For now this acts as a per‑account queue that always yields IDLE‑like
    gaps; later we will add real generation of warmup / outreach / reply
    actions and integrate rate limiting.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._queues: Dict[str, List[Action]] = {}

    async def add_action(self, action: Action) -> None:
        async with self._lock:
            q = self._queues.setdefault(action.account_id, [])
            q.append(action)

    async def next_action(self, account_id: str) -> Optional[Action]:
        async with self._lock:
            q = self._queues.get(account_id, [])
            if not q:
                return None
            action = q.pop(0)
        # Ensure we never run before earliest_start_ts.
        now = time.time()
        if action.earliest_start_ts > now:
            await asyncio.sleep(action.earliest_start_ts - now)
        return action


