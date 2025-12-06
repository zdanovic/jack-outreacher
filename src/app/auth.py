"""Lightweight authentication / authorization helpers (email + one-time code, HS256 token)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import smtplib
import time
from email.message import EmailMessage
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from ..core.config import AuthConfig


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


@dataclass
class AuthUser:
    email: str
    role: str  # "admin" or "client"


class AuthService:
    def __init__(self, cfg: AuthConfig) -> None:
        self.cfg = cfg
        self.enabled = cfg.enabled
        self._pending_codes: dict[str, dict] = {}

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _role_for_email(self, email: str) -> Optional[str]:
        email = self._normalize_email(email)
        domain = email.split("@")[-1] if "@" in email else ""

        domain_allowed = not self.cfg.allowed_domains or domain in self.cfg.allowed_domains
        if not domain_allowed:
            return None

        if email in self.cfg.allowed_admin_emails:
            return "admin"
        if email in self.cfg.allowed_client_emails:
            return "client"
        return None

    def _code_for_window(self, email: str, window: int) -> str:
        payload = f"{self._normalize_email(email)}|{window}|{self.cfg.secret}"
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return digest[:6].upper()

    def validate_code(self, email: str, code: str) -> bool:
        """
        Validate a short code within +/-1 time window to allow for
        clock drift. The code is deterministic from email+secret.
        """
        if not self.enabled:
            return True
        code = code.strip().upper()
        now_window = int(time.time() // self.cfg.code_ttl_seconds)
        for w in (now_window, now_window - 1, now_window + 1):
            expected = self._code_for_window(email, w)
            if hmac.compare_digest(expected, code):
                return True
        return False

    def _generate_code(self) -> str:
        # 6-digit numeric code, resistant to guess (secrets-based).
        return f"{secrets.randbelow(900000) + 100000}"

    def _hash_code(self, code: str) -> str:
        return hmac.new(self.cfg.secret.encode(), code.encode(), hashlib.sha256).hexdigest()

    def _send_code_email(self, email: str, code: str) -> bool:
        """
        Send code via SMTP if configured; otherwise log to stdout (dev mode).
        Returns True on success.
        """
        if not self.cfg.smtp_host:
            # Dev mode: write to file + log for easy retrieval.
            try:
                dest = Path(self.cfg.codes_dev_dir)
                dest.mkdir(parents=True, exist_ok=True)
                fname = dest / f"{self._normalize_email(email).replace('@', '_')}_{int(time.time())}.txt"
                fname.write_text(f"code={code}\nvalid_minutes={self.cfg.code_ttl_seconds // 60}\n", encoding="utf-8")
                print(f"[auth] DEV login code for {email}: {code} (saved to {fname})")
            except Exception as e:
                print(f"[auth] DEV code write failed: {e}")
            return True
        try:
            ttl_minutes = max(1, self.cfg.code_ttl_seconds // 60)
            msg = EmailMessage()
            msg["Subject"] = "Jack OutReacher • One-time sign-in code"
            msg["From"] = self.cfg.smtp_from or self.cfg.smtp_user or "no-reply"
            msg["To"] = email
            msg.set_content(
                f"Your one-time code: {code}\n"
                f"Valid for {ttl_minutes} minutes.\n\n"
                "If you did not request this code, you can safely ignore this email."
            )
            hero = "https://jackoutreacher.org/media/email-bg.jpg"
            wordmark = "https://jackoutreacher.org/media/email-wordmark.png"
            msg.add_alternative(
                f"""
<!DOCTYPE html>
<html>
  <head>
    <meta name="color-scheme" content="light dark">
    <style>
      :root {{
        --bg: #050914;
        --panel: #0f152a;
        --border: #1f2a44;
        --text: #e8f0ff;
        --muted: #c6d2e6;
        --shadow: 0 24px 60px rgba(0,0,0,0.55);
      }}
      @media (prefers-color-scheme: light) {{
        :root {{
          --bg: #f4f6fb;
          --panel: #ffffff;
          --border: #dbe4ff;
          --text: #0b1020;
          --muted: #4a587a;
          --shadow: 0 18px 40px rgba(0,0,0,0.12);
        }}
      }}
    </style>
  </head>
  <body style="margin:0;padding:0;background:var(--bg);color:var(--text);font-family:'Inter','Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:var(--bg);padding:28px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:var(--panel) url('{hero}') center/cover no-repeat;border:1px solid var(--border);border-radius:22px;box-shadow:var(--shadow);overflow:hidden;backdrop-filter:blur(10px);">
            <tr>
              <td style="padding:30px 32px 12px 32px;text-align:center;background:linear-gradient(180deg,rgba(10,16,32,0.7),rgba(10,16,32,0.65));">
                <img src="{wordmark}" width="220" alt="Jack OutReacher" style="display:block;margin:0 auto 6px auto;max-width:90%;filter:drop-shadow(0 8px 18px rgba(0,0,0,0.45));" />
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 8px 32px;text-align:center;">
                <div style="font-size:20px;font-weight:700;color:var(--text);margin-bottom:6px;letter-spacing:0.2px;">Your one-time code</div>
                <div style="font-size:14px;color:var(--muted);line-height:1.6;">Use this code to sign in. It expires in {ttl_minutes} minutes.</div>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 32px 18px 32px;text-align:center;">
                <div style="display:inline-block;padding:16px 28px;border-radius:18px;background:linear-gradient(120deg,#ff6a1f,#ff7f3f 35%,#09c7ff);color:#ffffff;font-size:30px;font-weight:800;letter-spacing:6px;font-family:'SFMono-Regular',Consolas,'Liberation Mono',monospace;box-shadow:0 14px 32px rgba(0,0,0,0.35),0 6px 18px rgba(9,199,255,0.25);">
                  {code}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 30px 32px;text-align:center;">
                <div style="font-size:13px;color:var(--muted);line-height:1.6;">
                  If you didn’t request this code, no action is needed. It will auto-expire shortly.
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
                """,
                subtype="html",
            )
            with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=10) as server:
                if self.cfg.smtp_use_tls:
                    server.starttls()
                if self.cfg.smtp_user and self.cfg.smtp_password:
                    server.login(self.cfg.smtp_user, self.cfg.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[auth] Failed to send email code: {e}")
            return False

    def request_code(self, email: str) -> bool:
        """
        Generate and deliver a one-time code to the given email.
        Returns True on success (even if email is not allowed, we return True to avoid leaks).
        """
        role = self._role_for_email(email)
        if role is None:
            # Do not reveal existence; pretend sent.
            return True
        now = time.time()
        code = self._generate_code()
        hashed = self._hash_code(code)
        self._pending_codes[email] = {
            "hash": hashed,
            "expires_at": now + self.cfg.code_ttl_seconds,
            "attempts": 0,
            "sent_at": now,
            "role": role,
            "code_plain": code,  # kept in-memory for delivery/testing only
        }
        return self._send_code_email(email, code)

    def _verify_pending_code(self, email: str, code: str) -> Optional[str]:
        """
        Verify a submitted code against pending store.
        Returns role on success.
        """
        rec = self._pending_codes.get(email)
        if not rec:
            return None
        now = time.time()
        if now > rec.get("expires_at", 0):
            self._pending_codes.pop(email, None)
            return None
        if rec.get("attempts", 0) >= self.cfg.max_code_attempts:
            self._pending_codes.pop(email, None)
            return None
        hashed = self._hash_code(code.strip())
        if not hmac.compare_digest(hashed, rec.get("hash", "")):
            rec["attempts"] = rec.get("attempts", 0) + 1
            return None
        role = rec.get("role")
        self._pending_codes.pop(email, None)
        return role

    def issue_token(self, email: str, role: str) -> str:
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": self._normalize_email(email), "role": role, "exp": now + self.cfg.token_ttl_seconds}
        signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
        sig = hmac.new(self.cfg.secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url(sig)}"

    def verify_token(self, token: str) -> Optional[AuthUser]:
        if not self.enabled:
            return AuthUser(email="insecure@local", role="admin")
        try:
            header_b64, payload_b64, sig_b64 = token.split(".")
        except ValueError:
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(self.cfg.secret.encode(), signing_input, hashlib.sha256).digest()
        try:
            provided_sig = _b64url_decode(sig_b64)
        except Exception:
            return None
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        try:
            payload = json.loads(_b64url_decode(payload_b64))
        except Exception:
            return None
        exp = payload.get("exp")
        if exp and int(time.time()) > int(exp):
            return None
        email = payload.get("sub")
        role = payload.get("role")
        if not email or not role:
            return None
        # Ensure the email is still permitted for the role.
        allowed_role = self._role_for_email(email)
        if allowed_role != role:
            return None
        return AuthUser(email=email, role=role)

    def login(self, email: str, code: str) -> Optional[str]:
        """
        Validate email + one-time code and return a signed token if allowed.
        """
        role = self._verify_pending_code(email, code)
        if not role:
            return None
        return self.issue_token(email, role)

    def _peek_code_for_tests(self, email: str) -> Optional[str]:  # pragma: no cover - testing helper
        rec = self._pending_codes.get(email)
        return rec.get("code_plain") if rec else None

if __name__ == "__main__":
    # Helper CLI to generate a login code for a given email.
    import os
    import argparse
    from ..core.config import load_app_config

    parser = argparse.ArgumentParser(description="Generate login code for email.")
    parser.add_argument("--email", required=True, help="Work email to authorize.")
    args = parser.parse_args()

    cfg = load_app_config().auth
    svc = AuthService(cfg)
    if not svc.enabled:
        print("Auth is disabled (AUTH_SHARED_SECRET missing).")
        raise SystemExit(1)
    sent = svc.request_code(args.email)
    if sent:
        code = svc._peek_code_for_tests(args.email)
        print(f"One-time code for {args.email}: {code}")
    else:
        print("Failed to generate/send code.")
