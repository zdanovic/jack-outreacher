import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

class ApiSmokeTest(unittest.TestCase):
    def test_endpoints_import_and_basic_responses(self) -> None:
        try:
            from src.app.api import app
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI or TestClient not available in this environment.")
            return

        from src.app.api import current_user, admin_required  # type: ignore
        from src.app.auth import AuthUser  # type: ignore

        # Override auth dependencies to avoid 401 in tests
        app.dependency_overrides[current_user] = lambda: AuthUser(email="admin@test.com", role="admin")
        app.dependency_overrides[admin_required] = lambda: AuthUser(email="admin@test.com", role="admin")

        client = TestClient(app)
        headers = {}

        # /accounts should always respond with a list (possibly empty)
        resp = client.get("/accounts", headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)

        # /logs/events should respond with a list (possibly empty)
        resp = client.get("/logs/events", headers=headers)
        self.assertEqual(resp.status_code, 200)
        logs = resp.json()
        self.assertIsInstance(logs, list)


if __name__ == "__main__":
    unittest.main()
