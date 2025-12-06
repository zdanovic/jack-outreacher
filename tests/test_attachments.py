import os
import sys
import unittest
from io import BytesIO

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


class AttachmentsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from src.app.api import app, current_user, admin_required  # type: ignore
            from fastapi.testclient import TestClient  # type: ignore
            from src.app.auth import AuthUser  # type: ignore
        except Exception:
            self.skipTest("FastAPI or TestClient not available.")
            return

        self.AuthUser = AuthUser
        self.app = app
        # Override auth to bypass JWT in tests.
        self.app.dependency_overrides[current_user] = lambda: AuthUser(email="admin@test.com", role="admin")
        self.app.dependency_overrides[admin_required] = lambda: AuthUser(email="admin@test.com", role="admin")
        self.client = TestClient(self.app)

    def test_upload_and_download_attachment(self) -> None:
        content = b"hello attachment"
        files = {"file": ("hello.txt", BytesIO(content), "text/plain")}
        resp = self.client.post("/attachments/upload", files=files)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        att_id = data["id"]

        resp = self.client.get(f"/attachments/{att_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, content)


if __name__ == "__main__":
    unittest.main()
