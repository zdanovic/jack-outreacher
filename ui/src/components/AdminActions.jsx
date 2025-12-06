import React, { useState } from "react";

const API_BASE = "/api";

export default function AdminActions({ authToken }) {
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  const restart = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const resp = await fetch(`${API_BASE}/admin/restart`, {
        method: "POST",
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      });
      const data = await resp.json();
      setMessage(data.message || "Sent restart request. Restart via process manager.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="settings-panel">
      <div className="settings-header">
        <div>
          <h3>Admin actions</h3>
          <p className="muted">
            При смене списка аккаунтов сделай рестарт orchestrator/API через process manager.
            Если задан ADMIN_RESTART_COMMAND, кнопка ниже запустит его.
          </p>
        </div>
        <button onClick={restart} disabled={loading}>
          {loading ? "Sending…" : "Restart hint"}
        </button>
      </div>
      {message && <div className="muted">{message}</div>}
    </section>
  );
}
