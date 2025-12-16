import React, { useState } from "react";

const API_BASE = "/api";

export default function AccountLoginPanel({ account, authToken, csrfToken, refreshAccounts }) {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  const headers = {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };

  const sendCode = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const resp = await fetch(`${API_BASE}/accounts/${encodeURIComponent(account.id)}/login/start`, {
        method: "POST",
        credentials: "include",
        headers,
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t || "Failed to send code");
      }
      setMessage("Код отправлен в Telegram. Введи его ниже.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const body = { code };
      if (password) body.password = password;
      const resp = await fetch(`${API_BASE}/accounts/${encodeURIComponent(account.id)}/login/verify`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t || "Failed to verify code");
      }
      setMessage("Успешный логин. Сессия сохранена.");
      refreshAccounts?.();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  const pause = async () => {
    await fetch(`${API_BASE}/accounts/${encodeURIComponent(account.id)}/pause`, {
      method: "POST",
      credentials: "include",
      headers,
    }).catch(() => {});
    refreshAccounts?.();
  };

  const resume = async () => {
    await fetch(`${API_BASE}/accounts/${encodeURIComponent(account.id)}/resume`, {
      method: "POST",
      credentials: "include",
      headers,
    }).catch(() => {});
    refreshAccounts?.();
  };

  return (
    <section className="settings-panel">
      <div className="settings-header">
        <div>
          <h3>Account login & control</h3>
          <p className="muted">Отправь код, подтверди логин, пауза/возврат. Работает только для выбранного аккаунта.</p>
        </div>
        <div className="account-controls">
          <button onClick={pause} disabled={loading}>Pause</button>
          <button onClick={resume} disabled={loading}>Resume</button>
        </div>
      </div>

      <div className="login-controls">
        <button onClick={sendCode} disabled={loading}>Send code</button>
      </div>
      <div className="login-form">
        <label>
          Code
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="SMS/Telegram code"
          />
        </label>
        <label>
          2FA password (optional)
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="If account has 2FA"
          />
        </label>
        <button onClick={verifyCode} disabled={loading || !code}>Verify</button>
      </div>
      {message && <div className="muted">{message}</div>}
    </section>
  );
}
