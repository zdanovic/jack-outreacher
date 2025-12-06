import os
import sys
import importlib
import unittest
from pathlib import Path


class FakeClient:
    def __init__(self, session_name, api_id=None, api_hash=None):  # noqa: ANN001
        self.session_name = session_name
        self.sent_codes = []
        self.signed = None

    async def connect(self):
        return None

    async def send_code_request(self, phone):  # noqa: ANN001
        self.sent_codes.append(phone)

    async def sign_in(self, phone, code=None, password=None):  # noqa: ANN001
        self.signed = (phone, code, password)

    async def disconnect(self):
        Path(self.session_name).write_text("SESSION_OK")


class AccountLoginFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)

        try:
            import fastapi  # noqa: F401
        except Exception:
            self.skipTest("FastAPI not available in this environment.")
            return

        # Minimal auth to hit admin endpoints
        os.environ["AUTH_SHARED_SECRET"] = "testsecret"
        os.environ["AUTH_ALLOWED_ADMIN_EMAILS"] = "admin@company.com"
        os.environ["AUTH_ALLOWED_CLIENT_EMAILS"] = "client@company.com"
        os.environ["AUTH_ALLOWED_EMAIL_DOMAINS"] = "company.com"
        os.environ["AUTH_TOKEN_TTL_SECONDS"] = "3600"
        os.environ["AUTH_CODE_TTL_SECONDS"] = "900"

        # Account config
        self.session_path = Path("/tmp/testacc.session")
        if self.session_path.exists():
            self.session_path.unlink()
        os.environ["ACCOUNTS"] = "TESTACC"
        os.environ["TESTACC_API_ID"] = "12345"
        os.environ["TESTACC_API_HASH"] = "hash"
        os.environ["TESTACC_PHONE"] = "+10000000000"
        os.environ["TESTACC_SESSION"] = str(self.session_path)

        import src.app.api as api  # type: ignore

        # Patch Telethon with fake client
        api.TelegramClient = FakeClient  # type: ignore[attr-defined]
        api.SessionPasswordNeededError = RuntimeError  # type: ignore[attr-defined]
        api._login_clients.clear()  # type: ignore[attr-defined]
        importlib.reload(api)
        api.TelegramClient = FakeClient  # type: ignore[attr-defined]
        api.SessionPasswordNeededError = RuntimeError  # type: ignore[attr-defined]
        api._login_clients.clear()  # type: ignore[attr-defined]
        self.api = api

    def tearDown(self) -> None:
        for key in list(os.environ.keys()):
            if key.startswith("TESTACC_"):
                os.environ.pop(key, None)
        for key in [
            "AUTH_SHARED_SECRET",
            "AUTH_ALLOWED_ADMIN_EMAILS",
            "AUTH_ALLOWED_CLIENT_EMAILS",
            "AUTH_ALLOWED_EMAIL_DOMAINS",
            "AUTH_TOKEN_TTL_SECONDS",
            "AUTH_CODE_TTL_SECONDS",
            "ACCOUNTS",
        ]:
            os.environ.pop(key, None)
        if self.session_path.exists():
            self.session_path.unlink()
        sys.modules.pop("src.app.api", None)

    def _admin_token(self):
        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return None

        client = TestClient(self.api.app)  # type: ignore[attr-defined]
        auth = self.api._auth  # type: ignore[attr-defined]
        auth.request_code("admin@company.com")
        code = auth._peek_code_for_tests("admin@company.com")  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": "admin@company.com", "code": code})
        self.assertEqual(resp.status_code, 200)
        return client, resp.json()["token"]

    def test_login_creates_session_when_missing(self):
        client, token = self._admin_token()
        if client is None:
            return

        # start login
        resp = client.post(
            "/accounts/TESTACC/login/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "code_sent")

        # verify
        resp = client.post(
            "/accounts/TESTACC/login/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "12345"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "logged_in")
        self.assertTrue(self.session_path.exists())
        self.assertIn("SESSION_OK", self.session_path.read_text())

    def test_login_overwrites_broken_session(self):
        self.session_path.write_text("BROKEN")
        client, token = self._admin_token()
        if client is None:
            return

        resp = client.post(
            "/accounts/TESTACC/login/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)

        resp = client.post(
            "/accounts/TESTACC/login/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "12345"},
        )
        self.assertEqual(resp.status_code, 200)
        content = self.session_path.read_text()
        self.assertNotEqual(content, "BROKEN")
        self.assertIn("SESSION_OK", content)


if __name__ == "__main__":
    unittest.main()
