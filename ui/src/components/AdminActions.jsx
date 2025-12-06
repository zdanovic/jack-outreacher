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
      <div className="settings-actions-inline">
        <div className="settings-header">
          <div>
            <h3>Admin actions</h3>
            <p className="muted">
              При смене списка аккаунтов сделай рестарт orchestrator/API через process manager.
            </p>
          </div>
        </div>
        <div className="settings-actions-buttons">
          <button onClick={restart} disabled={loading}>
            {loading ? "Sending…" : "Restart"}
          </button>
          {message && <div className="muted">{message}</div>}
        </div>
      </div>
    </section>
  );
}
