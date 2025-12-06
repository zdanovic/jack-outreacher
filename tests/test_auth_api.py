import os
import sys
import importlib
import unittest


class AuthAndApiTest(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure project root on sys.path
        ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)

        # FastAPI is optional in some environments; skip if missing
        try:
            import fastapi  # noqa: F401
        except Exception:
            self.skipTest("FastAPI not available in this environment.")
            return

        self._admin_email = "admin@company.com"
        self._client_email = "client@client.com"

        # Auth env
        os.environ["AUTH_SHARED_SECRET"] = "testsecret"
        os.environ["AUTH_ALLOWED_ADMIN_EMAILS"] = self._admin_email
        os.environ["AUTH_ALLOWED_CLIENT_EMAILS"] = self._client_email
        os.environ["AUTH_ALLOWED_EMAIL_DOMAINS"] = "company.com,client.com"
        os.environ["AUTH_CODE_TTL_SECONDS"] = "900"
        os.environ["AUTH_TOKEN_TTL_SECONDS"] = "3600"
        # Minimal accounts config (can be empty; endpoints should still respond)
        os.environ["ACCOUNTS"] = ""

        # Reload API to pick up env changes and rebuild config/auth
        import src.app.api as api  # type: ignore

        importlib.reload(api)
        self.api = api

    def tearDown(self) -> None:
        # Clean up env so other tests are not affected
        for key in [
            "AUTH_SHARED_SECRET",
            "AUTH_ALLOWED_ADMIN_EMAILS",
            "AUTH_ALLOWED_CLIENT_EMAILS",
            "AUTH_ALLOWED_EMAIL_DOMAINS",
            "AUTH_CODE_TTL_SECONDS",
            "AUTH_TOKEN_TTL_SECONDS",
            "ACCOUNTS",
        ]:
            os.environ.pop(key, None)

        # Remove cached modules so future imports can read fresh env
        for mod in ["src.app.api"]:
            sys.modules.pop(mod, None)

    def test_auth_service_roles_and_login(self) -> None:
        svc = self.api._auth  # type: ignore[attr-defined]
        admin_email = self._admin_email
        client_email = self._client_email
        bad_email = "intruder@other.com"

        self.assertEqual(svc._role_for_email(admin_email), "admin")  # type: ignore[attr-defined]
        self.assertEqual(svc._role_for_email(client_email), "client")  # type: ignore[attr-defined]
        self.assertIsNone(svc._role_for_email(bad_email))  # type: ignore[attr-defined]

        svc.request_code(admin_email)
        admin_code = svc._peek_code_for_tests(admin_email)  # type: ignore[attr-defined]
        token = svc.login(admin_email, admin_code or "")
        self.assertIsNotNone(token)
        user = svc.verify_token(token)  # type: ignore[arg-type]
        self.assertIsNotNone(user)
        self.assertEqual(user.role, "admin")

    def test_api_protection_and_roles(self) -> None:
        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return

        client = TestClient(self.api.app)  # type: ignore[attr-defined]

        # Without token -> 401
        resp = client.get("/accounts")
        self.assertEqual(resp.status_code, 401)

        # Admin login via email code -> token
        admin_email = self._admin_email
        self.api._auth.request_code(admin_email)  # type: ignore[attr-defined]
        admin_code = self.api._auth._peek_code_for_tests(admin_email)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": admin_email, "code": admin_code})
        self.assertEqual(resp.status_code, 200)
        admin_token = resp.json()["token"]

        # Admin can access /accounts
        resp = client.get("/accounts", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # Admin can read and update settings
        resp = client.get("/settings", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(resp.status_code, 200)
        settings = resp.json()
        self.assertIn("warmup", settings)

        resp = client.put(
            "/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"warmup": {"batch_interval_min": 100, "batch_interval_max": 200}},
        )
        self.assertEqual(resp.status_code, 200)
        updated = resp.json()
        self.assertEqual(updated.get("warmup", {}).get("batch_interval_min"), 100)

        # Client token can access landing but not /accounts
        client_email = self._client_email
        self.api._auth.request_code(client_email)  # type: ignore[attr-defined]
        client_code = self.api._auth._peek_code_for_tests(client_email)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": client_email, "code": client_code})
        self.assertEqual(resp.status_code, 200)
        client_token = resp.json()["token"]

        resp = client.get("/landing/summary", headers={"Authorization": f"Bearer {client_token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics", resp.json())

        resp = client.get("/accounts", headers={"Authorization": f"Bearer {client_token}"})
        self.assertEqual(resp.status_code, 403)

    def test_login_requires_email_and_code(self) -> None:
        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return

        client = TestClient(self.api.app)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={})
        self.assertIn(resp.status_code, (400, 422))


if __name__ == "__main__":
    unittest.main()
