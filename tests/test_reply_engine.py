import os
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.behavior.reply_engine import ReplyEngine
from src.storage.leads_store import LeadsStore
from src.storage.dialogs_store import DialogsStore
from src.ai.client import AIClient
from src.storage import state_db
from src.storage.dialogs_store import DialogMeta


class DummyAIClient(AIClient):  # type: ignore[misc]
    def __init__(self, text: str) -> None:
        # Bypass parent init
        self._text = text

    async def chat(self, messages, max_tokens=256, temperature=0.7):
        return self._text


class ReplyEngineUnitTest(unittest.TestCase):
    def test_extract_and_clean(self) -> None:
        # Create a minimal dummy instance to access _extract_and_clean.
        dummy_ai = DummyAIClient("x")
        # These stores are not used by _extract_and_clean.
        test_db = os.path.join(ROOT_DIR, "data", "test_reply.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]
        leads_store = LeadsStore(csv_path=os.path.join(ROOT_DIR, "data", "empty.csv"))
        dialogs_store = DialogsStore()
        engine = ReplyEngine(leads_store, dialogs_store, dummy_ai)

        text = (
            "Visible reply text.\n\n"
            "[Internal Analysis - Not Shown to User:\n"
            "Lead Status: hot\n"
            "Sentiment: positive\n"
            "]"
        )
        cleaned, status = engine._extract_and_clean(text)
        self.assertEqual(cleaned, "Visible reply text.")
        self.assertEqual(status, "hot")

    def test_manual_grace_skips_auto_reply(self) -> None:
        dummy_ai = DummyAIClient("ignored")
        test_db = os.path.join(ROOT_DIR, "data", "test_reply.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]
        leads_store = LeadsStore(csv_path=os.path.join(ROOT_DIR, "data", "empty.csv"))

        class DummyDialogs:
            def get(self, _username: str):
                return DialogMeta(
                    username="user1",
                    is_lead=True,
                    manual_replied_at="2099-01-01T00:00:00",
                )

        engine = ReplyEngine(leads_store, DummyDialogs(), dummy_ai)

        class DummyClient:
            async def get_entity(self, _u):  # pragma: no cover
                raise AssertionError("should not be called")

            async def get_messages(self, *_args, **_kwargs):  # pragma: no cover
                raise AssertionError("should not be called")

            async def send_message(self, *_args, **_kwargs):  # pragma: no cover
                raise AssertionError("should not be called")

        with patch("src.behavior.reply_engine.logs_store.log_event", new=AsyncMock()) as mocked_log:
            asyncio.run(engine.handle_incoming("acc1", DummyClient(), "user1", "hello"))
            mocked_log.assert_awaited()
            args, kwargs = mocked_log.call_args
            self.assertEqual(kwargs.get("result"), "skipped")
            self.assertEqual(kwargs.get("info"), "manual_grace_active")


if __name__ == "__main__":
    unittest.main()
