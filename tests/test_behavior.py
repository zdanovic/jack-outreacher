import os
import sys
import unittest
import asyncio

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.behavior.warmup_engine import WarmupEngine
from src.behavior.actions import ActionType
from src.behavior.outreach_engine import OutreachEngine
from src.storage.leads_store import LeadsStore
from src.core.rate_limiter import RateLimiter
from src.core.config import LimitsConfig
from src.storage import state_db


class WarmupEngineTest(unittest.TestCase):
    def test_initial_and_batch_actions(self) -> None:
        engine = WarmupEngine(["acc1", "acc2"])
        initial = engine.initial_actions()
        self.assertEqual(len(initial), 2)
        self.assertTrue(all(a.type is ActionType.IDLE for a in initial))

        batch = engine.plan_warmup_batch_for_account("acc1")
        self.assertGreaterEqual(len(batch), 2)
        types = {a.type for a in batch}
        self.assertIn(ActionType.READ_CHANNEL, types)
        self.assertIn(ActionType.IDLE, types)


class OutreachEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Reset state DB to a dedicated test file.
        test_db = os.path.join(ROOT_DIR, "data", "test_orchestrator_state_behavior.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]

    def test_plan_batch_for_account(self) -> None:
        # Prepare leads CSV
        csv_path = os.path.join(ROOT_DIR, "data", "test_leads_behavior.csv")
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Username,First Name,Tag\n")
            f.write("lead1,Anna,eng\n")
            f.write("lead2,Oleg,ru\n")

        leads_store = LeadsStore(csv_path=csv_path)
        limits = LimitsConfig(
            max_cold_per_account_per_day=10,
            max_cold_global_per_day=10,
            max_concurrent_heavy_actions=2,
            mode="conservative",
        )
        rate_limiter = RateLimiter(limits)
        engine = OutreachEngine(leads_store=leads_store, rate_limiter=rate_limiter)

        actions = asyncio.run(engine.plan_batch_for_account("acc1", max_per_batch=2))
        self.assertLessEqual(len(actions), 2)
        for a in actions:
            self.assertEqual(a.account_id, "acc1")
            self.assertIs(a.type, ActionType.SEND_COLD_DM)


if __name__ == "__main__":
    unittest.main()
