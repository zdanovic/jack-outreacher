import os
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.storage.state_db import get_state_db
from src.core.state import AccountStatus


class ManualReplyQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from src.app.api import app, current_user, admin_required  # type: ignore
            from fastapi.testclient import TestClient  # type: ignore
            from src.app.auth import AuthUser  # type: ignore
            from src.app import api as api_module  # type: ignore
        except Exception:
            self.skipTest("FastAPI or TestClient not available.")
            return

        self.api_module = api_module
        # Reset DB to default path to avoid cross-test DB_PATH overrides.
        from src.storage import state_db  # type: ignore
        state_db.DB_PATH = os.path.join(ROOT_DIR, "data", "orchestrator_state.db")
        state_db._db_instance = None  # type: ignore[attr-defined]
        from src.storage import outbox_store as outbox_module  # type: ignore
        outbox_module.outbox_store._db = get_state_db()

        # Override auth
        app.dependency_overrides[current_user] = lambda: AuthUser(email="admin@test.com", role="admin")
        app.dependency_overrides[admin_required] = lambda: AuthUser(email="admin@test.com", role="admin")
        self.client = TestClient(app)

        # Ensure lead exists
        db = get_state_db()
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (username, name, tag, source, status)
            VALUES (?, 'Test', 'eng', 'test', 'hot')
            ON CONFLICT(username) DO NOTHING;
            """,
            ("queued_user",),
        )
        db.conn.commit()

    def test_manual_reply_queued_when_account_paused(self) -> None:
        # Force account status to NEED_RELOGIN to trigger queue path.
        original = self.api_module.global_state.get_status
        self.api_module.global_state.get_status = AsyncMock(return_value=AccountStatus.NEED_RELOGIN)  # type: ignore

        resp = self.client.post(
            "/accounts/demo/dialogs/queued_user/reply",
            json={"text": "hi there"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "queued")
        # Restore
        self.api_module.global_state.get_status = original  # type: ignore

        # Ensure entry in pending_outbox
        db = get_state_db()
        cur = db.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pending_outbox WHERE account_id=? AND username=?", ("demo", "queued_user"))
        count = cur.fetchone()[0]
        self.assertGreater(count, 0)

    def test_pending_outbox_flushes_when_account_online(self) -> None:
        try:
            from src.telegram.accounts import AccountWorker  # type: ignore
            from src.core.config import AccountConfig  # type: ignore
            from src.storage.outbox_store import outbox_store  # type: ignore
            from src.storage.messages_store import messages_store  # type: ignore
            from src.storage.leads_store import LeadsStore  # type: ignore
        except Exception:
            self.skipTest("Core modules not available.")
            return

        # Isolate DB for this test.
        test_db = os.path.join(ROOT_DIR, "data", "test_manual_reply_flush.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        from src.storage import state_db  # type: ignore

        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]
        db = state_db.get_state_db()

        # Re-bind stores to new DB.
        outbox_store._db = db  # type: ignore[attr-defined]
        messages_store._db = db  # type: ignore[attr-defined]

        # Seed a lead row to keep status updates consistent.
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (username, name, tag, source, status)
            VALUES (?, 'Test', 'eng', 'test', 'failed')
            ON CONFLICT(username) DO NOTHING;
            """,
            ("flush_user",),
        )
        db.conn.commit()

        cfg = AccountConfig(
            id="demo",
            api_id=123,
            api_hash="hash",
            phone="+100000000",
            session_name="demo.session",
            proxy=None,
            timezone=None,
            behavior_profile=None,
        )
        worker = AccountWorker(cfg=cfg, client_adapter=None, scheduler=None)  # type: ignore[arg-type]

        class DummyClient:
            def __init__(self) -> None:
                self.sent = []

            async def send_message(self, username: str, text: str) -> None:
                self.sent.append((username, text))

        worker._client = DummyClient()
        worker.leads_store = LeadsStore(csv_path=os.path.join(ROOT_DIR, "data", "empty.csv"))

        outbox_id = outbox_store.add_pending(
            account_id="demo",
            username="flush_user",
            direction="out",
            text="queued text",
        )

        import asyncio

        asyncio.run(worker._flush_pending_outbox())

        # Verify send occurred and outbox marked sent.
        cur.execute("SELECT status FROM pending_outbox WHERE id=?", (outbox_id,))
        status = cur.fetchone()[0]
        self.assertEqual(status, "sent")
        self.assertEqual(len(worker._client.sent), 1)

if __name__ == "__main__":
    unittest.main()
