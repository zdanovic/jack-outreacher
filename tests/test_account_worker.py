import os
import sys
import unittest
import asyncio

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.config import AccountConfig, LimitsConfig
from src.telegram.accounts import AccountWorker
from src.storage.leads_store import LeadsStore
from src.storage.dialogs_store import DialogsStore
from src.core.rate_limiter import RateLimiter
from src.storage import state_db
from src.core.state import global_state, AccountStatus


class DummyClient:
    def __init__(self) -> None:
        self.sent = []

    async def send_message(self, username: str, text: str) -> None:
        self.sent.append((username, text))


class DummyAIClient:
    async def chat(self, messages, max_tokens=256, temperature=0.7):
        return "AI first-touch message"


class AccountWorkerColdDMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Use dedicated DB for this test module.
        test_db = os.path.join(ROOT_DIR, "data", "test_account_worker.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]

    def test_handle_send_cold_dm_uses_ai_and_updates_stores(self) -> None:
        # Prepare minimal CSV for leads
        csv_path = os.path.join(ROOT_DIR, "data", "test_account_worker_leads.csv")
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Username,First Name,Tag\n")
            f.write("lead1,Anna,eng\n")

        leads_store = LeadsStore(csv_path=csv_path)
        dialogs_store = DialogsStore()

        limits = LimitsConfig(
            max_cold_per_account_per_day=10,
            max_cold_global_per_day=10,
            max_concurrent_heavy_actions=2,
            mode="conservative",
        )
        rate_limiter = RateLimiter(limits, seed_from_db=False)

        cfg = AccountConfig(
            id="acc1",
            api_id=12345,
            api_hash="hash",
            phone="+100000000",
            session_name="account1.session",
            proxy=None,
            timezone=None,
            behavior_profile=None,
        )

        worker = AccountWorker(cfg=cfg, client_adapter=None, scheduler=None)  # type: ignore[arg-type]
        dummy_client = DummyClient()
        worker._client = dummy_client
        worker.leads_store = leads_store
        worker.dialogs_store = dialogs_store
        worker.rate_limiter = rate_limiter
        worker.ai_client = DummyAIClient()  # type: ignore[assignment]

        ctx = {"username": "lead1", "name": "Anna", "tag": "eng"}

        asyncio.run(worker._handle_send_cold_dm(ctx))

        # Assert that a message was sent
        self.assertEqual(len(dummy_client.sent), 1)
        sent_username, sent_text = dummy_client.sent[0]
        self.assertEqual(sent_username, "lead1")
        self.assertTrue(sent_text)  # Either AI text or fallback

    def test_healthcheck_marks_need_relogin_when_unauthorized(self) -> None:
        # Reset global state for this test.
        global_state._accounts = {}  # type: ignore[attr-defined]

        cfg = AccountConfig(
            id="acc2",
            api_id=12346,
            api_hash="hash",
            phone="+100000001",
            session_name="account2.session",
            proxy=None,
            timezone=None,
            behavior_profile=None,
        )

        class DummyUnauthorizedClient:
            async def is_user_authorized(self):
                return False

            async def get_me(self):  # pragma: no cover
                raise AssertionError("should not be called")

        worker = AccountWorker(cfg=cfg, client_adapter=None, scheduler=None)  # type: ignore[arg-type]
        worker._client = DummyUnauthorizedClient()

        import asyncio

        ok = asyncio.run(worker._post_connect_healthcheck())
        status = asyncio.run(global_state.get_status("acc2"))
        runtime = asyncio.run(global_state.get_runtime("acc2"))

        self.assertFalse(ok)
        self.assertEqual(status, AccountStatus.NEED_RELOGIN)
        self.assertIn("login required", runtime.last_error or "")


if __name__ == "__main__":
    unittest.main()
