import os
import sys
import unittest
from datetime import datetime

# Ensure project root is on path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.storage import state_db
from src.storage.leads_store import LeadsStore, _normalize_username
from src.storage.dialogs_store import DialogsStore, DialogMeta


class StorageTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Use a dedicated test DB to avoid polluting production state.
        test_db = os.path.join(ROOT_DIR, "data", "test_orchestrator_state.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        state_db.DB_PATH = test_db
        state_db._db_instance = None  # type: ignore[attr-defined]

    def test_leads_seed_and_reserve(self) -> None:
        # Create a small CSV with two leads.
        csv_path = os.path.join(ROOT_DIR, "data", "test_leads.csv")
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Username,First Name,Tag,Source\n")
            f.write("user1,Alex,eng,sourceA\n")
            f.write("@User2,Max,ru,sourceB\n")

        store = LeadsStore(csv_path=csv_path)
        new_leads = store.load_new_leads()
        self.assertEqual(len(new_leads), 2)
        self.assertEqual({l.username for l in new_leads}, {"user1", "user2"})

        # Reserve a lead for account "acc1"
        reserved = store.reserve_lead_for_account("acc1")
        self.assertIsNotNone(reserved)
        self.assertIn(reserved.username, {"user1", "user2"})
        # Mark as contacted
        store.mark_contacted(reserved.username, "acc1")
        # Update status
        store.update_status(reserved.username, "hot")

    def test_dialogs_upsert_and_get(self) -> None:
        dialogs = DialogsStore()
        meta = DialogMeta(
            username="TestUser",
            peer_id=12345,
            is_lead=True,
            lead_id="lead-1",
            first_seen_at=None,
            last_seen_at=None,
            last_account_id="acc1",
        )
        dialogs.upsert(meta)
        fetched = dialogs.get("testuser")
        self.assertIsNotNone(fetched)
        assert fetched
        self.assertEqual(fetched.username, "testuser")
        self.assertTrue(fetched.is_lead)
        self.assertEqual(fetched.peer_id, 12345)


if __name__ == "__main__":
    unittest.main()

