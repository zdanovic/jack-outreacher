import React from "react";

export default function ClientLanding({ summary, accounts, onLogout, email }) {
  const agg = summary?.metrics || {};
  const status = summary?.status_counts || {};

  return (
    <div className="client-landing">
      <header className="client-header">
        <div>
          <div className="logo">TG Orchestrator</div>
          <div className="subtitle">Client view (read-only)</div>
        </div>
        <div className="user-pill">
          <span>{email}</span>
          <button onClick={onLogout}>Log out</button>
        </div>
      </header>
      <section className="summary-grid">
        <div className="summary-card">
          <div className="label">Accounts total</div>
          <div className="value">{summary?.accounts_total || 0}</div>
          <div className="muted">
            active {status.active || 0} · paused {status.paused || 0}
          </div>
        </div>
        <div className="summary-card">
          <div className="label">Cold sent (today)</div>
          <div className="value">{agg.cold_sent || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Replies (today)</div>
          <div className="value">{agg.replies || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Warmup actions</div>
          <div className="value">{agg.warmup_actions || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Hot leads</div>
          <div className="value">{agg.hot || 0}</div>
          <div className="muted">Warm {agg.warm || 0} · Cold {agg.cold || 0}</div>
        </div>
      </section>
      <section className="client-accounts">
        <h3>Accounts status</h3>
        <div className="client-accounts-grid">
          {accounts.map((acc) => (
            <div key={acc.id} className="client-account-card">
              <div className="title">{acc.id}</div>
              <div className="status">{acc.status}</div>
              <div className="metrics">
                <span>cold {acc.metrics?.cold_sent || 0}</span>
                <span>replies {acc.metrics?.replies_received || 0}</span>
                <span>warm {acc.metrics?.warm_leads || 0}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="privacy-note">
        <p>
          Данные обезличены: без логов, телефонов и переписок. Полная админка доступна только
          админам по рабочей почте.
        </p>
      </section>
    </div>
  );
}
