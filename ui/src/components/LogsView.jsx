import React, { useMemo, useState } from "react";
import { createPortal } from "react-dom";

const API_BASE = "/api";

function formatTs(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function LogsView({ logs, authToken, csrfToken, accounts = [], t = (k) => k }) {
  const [modal, setModal] = useState(null); // {account_id, target, messages, loading, error}
  const headers = {
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };

  const phoneTailMap = useMemo(() => {
    const map = {};
    accounts.forEach((acc) => {
      const digits = (acc.phone || "").replace(/\D/g, "");
      if (digits) {
        map[acc.id] = digits.slice(-4);
      }
    });
    return map;
  }, [accounts]);

  const renderAccountLabel = (accountId) => {
    if (!accountId) return "";
    const tail = phoneTailMap[accountId];
    if (!tail) return accountId;
    return (
      <>
        {accountId} <span className="account-phone-hint log-phone-hint">(...{tail})</span>
      </>
    );
  };

  const handleRowClick = async (log) => {
    if (!log.account_id || !log.target) return;
    setModal({ account_id: log.account_id, target: log.target, messages: [], loading: true, error: null });
    try {
      const resp = await fetch(
        `${API_BASE}/accounts/${encodeURIComponent(log.account_id)}/dialogs/${encodeURIComponent(log.target)}/messages`,
        { headers, credentials: "include" }
      );
      const data = await resp.json();
      setModal((prev) => ({ ...prev, messages: data, loading: false }));
    } catch (err) {
      setModal((prev) => ({ ...prev, loading: false, error: err.message || "Failed to load messages" }));
    }
  };

  const statusBadge = (result) => {
    const r = (result || "").toLowerCase();
    const cls =
      r === "ok" || r === "success"
        ? "log-badge ok"
        : r === "error"
        ? "log-badge error"
        : r === "queued"
        ? "log-badge queued"
        : "log-badge";
    return <span className={cls}>{result}</span>;
  };

  const closeModal = () => setModal(null);

  return (
    <section className="logs-view">
      <h2>{t("logs_title")}</h2>
      <div className="logs-table">
        <table>
          <thead>
            <tr>
            <th title={t("col_time_hint")}>{t("col_time")}</th>
              <th title={t("col_account_hint")}>{t("col_account")}</th>
              <th title={t("col_action_hint")}>{t("col_action")}</th>
              <th title={t("col_target_hint")}>{t("col_target")}</th>
              <th title={t("col_result_hint")}>{t("col_result")}</th>
              <th title={t("col_info_hint")}>{t("col_info")}</th>
            </tr>
          </thead>
          <tbody>
            {[...logs].reverse().map((e, idx) => (
              <tr key={idx} className="log-row" onClick={() => handleRowClick(e)}>
                <td>{formatTs(e.ts)}</td>
                <td>{renderAccountLabel(e.account_id)}</td>
                <td>{e.action_type}</td>
                <td>{e.target}</td>
                <td>{statusBadge(e.result)}</td>
                <td>{e.info}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal &&
        typeof document !== "undefined" &&
        createPortal(
          <LogModal
            modal={modal}
            onClose={closeModal}
            authToken={authToken}
            renderAccountLabel={renderAccountLabel}
            refreshMessages={async () => {
              if (!modal.account_id || !modal.target) return;
              try {
                const resp = await fetch(
                  `${API_BASE}/accounts/${encodeURIComponent(modal.account_id)}/dialogs/${encodeURIComponent(
                    modal.target
                  )}/messages`,
                  { headers, credentials: "include" }
                );
                const data = await resp.json();
                setModal((prev) => ({ ...prev, messages: data, loading: false }));
              } catch (err) {
                setModal((prev) => ({ ...prev, loading: false, error: err.message || "Failed to load messages" }));
              }
            }}
          />,
          document.body
        )}
    </section>
  );
}

function LogModal({ modal, onClose, authToken, renderAccountLabel, refreshMessages }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const headers = authToken ? { Authorization: `Bearer ${authToken}`, "Content-Type": "application/json" } : {};

  const sendReply = async () => {
    if (!text.trim()) return;
    setSending(true);
    setError(null);
    try {
      const resp = await fetch(
        `${API_BASE}/accounts/${encodeURIComponent(modal.account_id)}/dialogs/${encodeURIComponent(modal.target)}/reply`,
        {
          method: "POST",
          headers,
          credentials: "include",
          body: JSON.stringify({ text }),
        }
      );
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t || "Failed to send reply");
      }
      setText("");
      await refreshMessages();
    } catch (err) {
      setModal((prev) => ({ ...prev, loading: false, error: err.message || "Failed to load messages" }));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">
              {renderAccountLabel ? renderAccountLabel(modal.account_id) : modal.account_id} → {modal.target}
            </div>
            <div className="modal-subtitle">История диалога и ручной ответ</div>
          </div>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          {modal.loading && <div className="muted">Загружаю…</div>}
          {modal.error && <div className="error">{modal.error}</div>}
          {!modal.loading && (
            <div className="dialog-history">
              {(modal.messages || []).map((m, idx) => (
                <div
                  key={idx}
                  className={
                    "dialog-message " + (m.direction === "out" ? "dialog-out" : "dialog-in")
                  }
                >
                  <div className="dialog-meta">
                    <span>{m.direction === "out" ? "Мы" : "Лид"}</span>
                    <span>{formatTs(m.ts)}</span>
                  </div>
                  <div className="dialog-text">{m.text}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="modal-footer">
          <textarea
            placeholder="Написать вручную…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {error && <div className="error">{error}</div>}
          <div className="modal-actions">
            <button onClick={sendReply} disabled={sending || !text.trim()}>
              {sending ? "Sending..." : "Send manual reply"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
