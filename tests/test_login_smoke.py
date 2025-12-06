import os
import sys
import time
import importlib
import unittest


class LoginSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)

        try:
            import fastapi  # noqa: F401
        except Exception:
            self.skipTest("FastAPI not available in this environment.")
            return
        self._admin_email = "admin@company.com"
        self._client_email = "client@company.com"

    def tearDown(self) -> None:
        for key in [
            "AUTH_SHARED_SECRET",
            "AUTH_ALLOWED_ADMIN_EMAILS",
            "AUTH_ALLOWED_CLIENT_EMAILS",
            "AUTH_ALLOWED_EMAIL_DOMAINS",
            "AUTH_PASSWORDLESS",
            "AUTH_TOKEN_TTL_SECONDS",
            "AUTH_CODE_TTL_SECONDS",
            "ACCOUNTS",
        ]:
            os.environ.pop(key, None)
        sys.modules.pop("src.app.api", None)

    def _reload_api(self):
        import src.app.api as api  # type: ignore
        importlib.reload(api)
        return api

    def _configure_env(self, token_ttl: str = "3600") -> None:
        os.environ["AUTH_SHARED_SECRET"] = "smokesecret"
        os.environ["AUTH_ALLOWED_ADMIN_EMAILS"] = self._admin_email
        os.environ["AUTH_ALLOWED_CLIENT_EMAILS"] = self._client_email
        os.environ["AUTH_ALLOWED_EMAIL_DOMAINS"] = "company.com"
        os.environ["AUTH_TOKEN_TTL_SECONDS"] = token_ttl
        os.environ["AUTH_CODE_TTL_SECONDS"] = "900"
        os.environ["ACCOUNTS"] = ""

    def test_auth_disabled_allows_access(self) -> None:
        os.environ.pop("AUTH_SHARED_SECRET", None)
        os.environ["ACCOUNTS"] = ""
        api = self._reload_api()
        api._config.auth.enabled = False  # type: ignore[attr-defined]
        api._auth.enabled = False  # type: ignore[attr-defined]

        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return

        client = TestClient(api.app)  # type: ignore[attr-defined]
        resp = client.get("/accounts")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_email_code_login_and_roles(self) -> None:
        self._configure_env()
        api = self._reload_api()

        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return

        client = TestClient(api.app)  # type: ignore[attr-defined]

        api._auth.request_code(self._admin_email)  # type: ignore[attr-defined]
        admin_code = api._auth._peek_code_for_tests(self._admin_email)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": self._admin_email, "code": admin_code})
        self.assertEqual(resp.status_code, 200)
        admin_token = resp.json()["token"]

        resp = client.get("/accounts", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(resp.status_code, 200)

        api._auth.request_code(self._client_email)  # type: ignore[attr-defined]
        client_code = api._auth._peek_code_for_tests(self._client_email)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": self._client_email, "code": client_code})
        self.assertEqual(resp.status_code, 200)
        client_token = resp.json()["token"]

        resp = client.get("/accounts", headers={"Authorization": f"Bearer {client_token}"})
        self.assertEqual(resp.status_code, 403)

    def test_email_code_token_expiry(self) -> None:
        self._configure_env(token_ttl="1")
        api = self._reload_api()

        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception:
            self.skipTest("FastAPI TestClient not available.")
            return

        client = TestClient(api.app)  # type: ignore[attr-defined]

        api._auth.request_code(self._admin_email)  # type: ignore[attr-defined]
        admin_code = api._auth._peek_code_for_tests(self._admin_email)  # type: ignore[attr-defined]
        resp = client.post("/auth/login", json={"email": self._admin_email, "code": admin_code})
        self.assertEqual(resp.status_code, 200)
        internal = resp.json()["token"]

        resp = client.get("/accounts", headers={"Authorization": f"Bearer {internal}"})
        self.assertEqual(resp.status_code, 200)

        time.sleep(2)
        resp = client.get("/accounts", headers={"Authorization": f"Bearer {internal}"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
