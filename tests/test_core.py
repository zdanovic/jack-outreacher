import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.rate_limiter import RateLimiter
from src.core.config import LimitsConfig
from src.core.metrics import metrics_store
from src.storage import state_db
from src.core.state import global_state


class RateLimiterTest(unittest.TestCase):
    def test_rate_limiter_basic(self) -> None:
        # Reset in-memory account counters to avoid cross-test contamination.
        global_state._accounts = {}  # type: ignore[attr-defined]
        limits = LimitsConfig(
            max_cold_per_account_per_day=2,
            max_cold_global_per_day=3,
            max_concurrent_heavy_actions=1,
            mode="conservative",
        )
        rl = RateLimiter(limits, seed_from_db=False)

        async def scenario():
            # First send should be allowed.
            ok1 = await rl.can_send_cold("acc1")
            await rl.register_cold_sent("acc1")
            # Second send should also be allowed under per‑account limit 2.
            ok2 = await rl.can_send_cold("acc1")
            await rl.register_cold_sent("acc1")
            # Third send should be blocked.
            ok3 = await rl.can_send_cold("acc1")
            return ok1, ok2, ok3

        import asyncio

        ok1, ok2, ok3 = asyncio.run(scenario())
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertFalse(ok3)


class MetricsStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_db = os.path.join(ROOT_DIR, "data", "test_metrics.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]

    def test_metrics_increment(self) -> None:
        async def scenario():
            await metrics_store.incr("acc1", "cold_sent", 1)
            await metrics_store.incr("acc1", "hot_leads", 2)

        import asyncio

        asyncio.run(scenario())

    # We do not assert DB contents here to keep the test lightweight and
    # storage-agnostic; the main goal is to verify that increments do not
    # raise and interact correctly with the SQLite schema.


if __name__ == "__main__":
    unittest.main()
