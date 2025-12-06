import os
import sys
import unittest
from datetime import date

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


class MetricsStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate DB
        from src.storage import state_db  # type: ignore
        self.test_db = os.path.join(ROOT_DIR, "data", "test_metrics.db")
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        state_db.DB_PATH = self.test_db
        state_db._db_instance = None  # type: ignore[attr-defined]
        from src.core.metrics import MetricsStore

        self.store = MetricsStore()
        self.db = self.store._db.conn  # type: ignore[attr-defined]

    def test_increment_is_accumulated_single_row(self) -> None:
        today = date.today().isoformat()
        # Two increments for same account/field
        for _ in range(2):
            import asyncio

            asyncio.run(self.store.incr("acc1", "cold_sent", 1))

        cur = self.db.cursor()
        cur.execute("SELECT cold_sent, COUNT(*) FROM metrics WHERE date=? AND account_id=?", (today, "acc1"))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        cold_sent, count = row
        self.assertEqual(count, 1)
        self.assertEqual(cold_sent, 2)

    def tearDown(self) -> None:
        if os.path.exists(self.test_db):
            os.remove(self.test_db)


if __name__ == "__main__":
    unittest.main()
