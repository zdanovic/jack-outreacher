import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

const API_BASE = "/api";
const STATUS_OPTS = [
  { id: "hot", label: "Hot", color: "#f97316" },
  { id: "warm", label: "Warm", color: "#fb7185" },
  { id: "deal", label: "Deal", color: "#14b8a6" },
  { id: "failed", label: "Failed", color: "#ef4444" },
];

const BOARD_COLUMNS = [
  { id: "warm", title: "Warm", hint: "AI квалификация / прогретые" },
  { id: "hot", title: "Hot", hint: "Горячие, ждут ответа" },
  { id: "deal", title: "Deal", hint: "Сделка / передано клиенту (только вручную)" },
  { id: "failed", title: "Failed", hint: "Ошибка/очередь: требуется ручная проверка" },
];

function formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusChip({ status }) {
  const meta = STATUS_OPTS.find((s) => s.id === status) || { color: "#64748b", label: status || "unknown" };
  return (
    <span className="status-chip" style={{ borderColor: meta.color, color: meta.color }}>
      {meta.label}
    </span>
  );
}

function accountLabel(accMap, accountId) {
  if (!accountId) return "";
  const acc = accMap[accountId];
  if (!acc) return accountId;
  const digits = (acc.phone || "").replace(/\D/g, "");
  const tail = digits ? digits.slice(-4) : null;
  return (
    <>
      {accountId} {tail ? <span className="account-phone-hint log-phone-hint">(...{tail})</span> : null}
    </>
  );
}

export default function LeadsView({ authToken, csrfToken, accounts = [], t = (key) => key }) {
  const STATUS_OPTS = [
    { id: "hot", label: t("status_hot"), color: "#f97316" },
    { id: "warm", label: t("status_warm"), color: "#fb7185" },
    { id: "deal", label: t("status_deal"), color: "#14b8a6" },
    { id: "failed", label: t("status_failed"), color: "#ef4444" },
  ];

  const BOARD_COLUMNS = [
    { id: "warm", title: t("col_warm"), hint: t("col_warm_hint") },
    { id: "hot", title: t("col_hot"), hint: t("col_hot_hint") },
    { id: "deal", title: t("col_deal"), hint: t("col_deal_hint") },
    { id: "failed", title: t("col_failed"), hint: t("col_failed_hint") },
  ];

  const [statuses, setStatuses] = useState(new Set(["hot", "warm", "deal", "failed"]));
  const [days, setDays] = useState(90);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [leads, setLeads] = useState([]);
  const [modal, setModal] = useState(null); // {lead, messages, loading, error}
  const [dragging, setDragging] = useState(null); // username being dragged
  const [contextMenu, setContextMenu] = useState(null); // {x, y, lead}

  const headers = {
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };
  const accMap = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a])), [accounts]);

  const toggleStatus = (id) => {
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      if (next.size === 0) {
        return new Set([id]); // keep at least one
      }
      return next;
    });
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams();
        qs.set("statuses", Array.from(statuses).join(","));
        qs.set("since_days", days);
        qs.set("limit", 200);
        if (search.trim()) qs.set("search", search.trim());
        const resp = await fetch(`${API_BASE}/leads?${qs.toString()}`, { headers, credentials: "include" });
        if (resp.status === 404) {
          // API not yet restarted with /leads route; degrade gracefully.
          if (!cancelled) {
            setLeads([]);
            setError("Leads endpoint недоступен — перезапусти API, чтобы обновить маршруты.");
          }
          return;
        }
        if (!resp.ok) throw new Error(`Failed to load leads: ${resp.status}`);
        const data = await resp.json();
        if (!cancelled) setLeads(data);
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load leads");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [statuses, days, search, authToken]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateLeadStatus = async (lead, newStatus) => {
    try {
      const resp = await fetch(`${API_BASE}/leads/${encodeURIComponent(lead.username)}/status`, {
        method: "POST",
        credentials: "include",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!resp.ok) throw new Error(`Failed to update status: ${resp.status}`);
      const updated = await resp.json();
      setLeads((prev) =>
        prev.map((l) => (l.username === updated.username ? { ...l, status: updated.status } : l))
      );
    } catch (err) {
      setError(err.message || "Failed to update status");
    }
  };

  const openLead = async (lead) => {
    const accountId = lead.last_account_id || accounts[0]?.id;
    setModal({ lead, messages: [], loading: true, error: null, accountId });
    if (!accountId) {
      setModal((prev) => ({ ...prev, loading: false, error: t("error") }));
      return;
    }
    try {
      const resp = await fetch(
        `${API_BASE}/accounts/${encodeURIComponent(accountId)}/dialogs/${encodeURIComponent(lead.username)}/messages`,
        { headers, credentials: "include" }
      );
      const data = await resp.json();
      setModal((prev) => ({ ...prev, messages: data, loading: false }));
    } catch (err) {
      setModal((prev) => ({ ...prev, loading: false, error: err.message || t("error") }));
    }
  };

  return (
    <section className="leads-view">
      <div className="leads-panel">
        <div className="leads-header">
          <div>
            <h2>{t("leads_title")}</h2>
          </div>
          <div className="leads-filters">
            <div className="filter-block" title={t("filter_last_contact")}>
              <div className="filter-label">{t("filter_last_contact")}</div>
              <div className="filter-group">
                {[7, 30, 90, 180, 365].map((d) => (
                  <button
                    key={d}
                    className={days === d ? "chip chip-active" : "chip"}
                    onClick={() => setDays(d)}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>
            <div className="filter-block search-block" title={t("filter_search")}>
              <div className="filter-label">{t("filter_search")}</div>
              <input
                className="lead-search"
                placeholder={t("filter_search_ph")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="kanban-board">
        {BOARD_COLUMNS.map((col) => {
          const items = leads.filter((l) => l.status === col.id);
          return (
            <div
              key={col.id}
              className={"kanban-column" + (dragging ? " kanban-dropping" : "")}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!dragging) return;
                const lead = leads.find((l) => l.username === dragging);
                if (lead && lead.status !== col.id) {
                  updateLeadStatus(lead, col.id);
                }
                setDragging(null);
              }}
            >
              <div className="kanban-head">
                <div>
                  <div className="kanban-title">{col.title}</div>
                  <div className="kanban-subtitle">{col.hint}</div>
                </div>
                <div className="kanban-count">{items.length}</div>
              </div>
              <div className="kanban-list">
                {items.map((lead) => (
                  <div
                    key={lead.username}
                    className="lead-card"
                    draggable
                    onDragStart={() => setDragging(lead.username)}
                    onDragEnd={() => setDragging(null)}
                    onClick={() => openLead(lead)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setContextMenu({ x: e.clientX, y: e.clientY, lead });
                    }}
                  >
                    <LeadCardContent lead={lead} accMap={accMap} t={t} palette={STATUS_OPTS} />
                  </div>
                ))}
                {items.length === 0 && <div className="muted small">Пусто</div>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="filter-block filter-block-inline" title={t("statuses_title")}>
        <div className="filter-label">{t("statuses_title")}</div>
        <div className="filter-group">
          {STATUS_OPTS.map((s) => (
            <button
              key={s.id}
              className={statuses.has(s.id) ? "chip chip-active" : "chip"}
              onClick={() => toggleStatus(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="leads-list">
        <h3>All touches</h3>
        {loading && <div className="muted">Загрузка…</div>}
        {error && <div className="error">{error}</div>}
        {!loading && !error && leads.length === 0 && <div className="muted">Нет лидов по фильтрам</div>}
        {!loading &&
          !error &&
          leads.map((lead) => (
                  <div
                    key={lead.username}
                    className="lead-card lead-card-compact"
                    draggable
                    onDragStart={() => setDragging(lead.username)}
                    onDragEnd={() => setDragging(null)}
                    onClick={() => openLead(lead)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setContextMenu({ x: e.clientX, y: e.clientY, lead });
                    }}
                  >
                    <LeadCardContent lead={lead} accMap={accMap} t={t} palette={STATUS_OPTS} />
                  </div>
                ))}
      </div>

      {modal &&
        typeof document !== "undefined" &&
        createPortal(
          <LeadModal
            modal={modal}
            onClose={() => setModal(null)}
            renderAccount={(id) => accountLabel(accMap, id)}
            authToken={authToken}
            csrfToken={csrfToken}
            refreshLead={() => openLead(modal.lead)}
          />,
          document.body
        )}

      {contextMenu &&
        typeof document !== "undefined" &&
        createPortal(
          <>
            <div className="context-menu-backdrop" onClick={() => setContextMenu(null)} />
            <div
              className="context-menu"
              style={{ top: contextMenu.y, left: contextMenu.x }}
            >
              <div className="context-menu-title">@{contextMenu.lead.username}</div>
              <div className="context-menu-subtitle">Выбери статус</div>
              <div className="context-menu-items">
                {STATUS_OPTS.map((s) => (
                  <button
                    key={s.id}
                    className={contextMenu.lead.status === s.id ? "context-item active" : "context-item"}
                    onClick={() => {
                      updateLeadStatus(contextMenu.lead, s.id);
                      setContextMenu(null);
                    }}
                  >
                    <span className="legend-dot" style={{ background: s.color }} />
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          </>,
          document.body
        )}
    </section>
  );
}

function LeadCardContent({ lead, accMap, t, palette }) {
  const primaryName =
    (lead.first_name || lead.last_name) && (lead.first_name + " " + lead.last_name).trim().length > 0
      ? `${lead.first_name || ""} ${lead.last_name || ""}`.trim()
      : lead.name || lead.username;
  const bioPreview = lead.bio ? (lead.bio.length > 80 ? `${lead.bio.slice(0, 80)}…` : lead.bio) : "";
  return (
    <>
      <div className="lead-main">
        <div className="lead-name">{primaryName}</div>
        <div className="lead-username">@{lead.username}</div>
      </div>
      <div className="lead-meta">
        <StatusChip status={lead.status} t={t} palette={palette} />
        {lead.source ? <span className="lead-source chip-soft">{lead.source}</span> : null}
        <span className="lead-tag">{lead.tag || "n/a"}</span>
        <span className="lead-time">{formatTs(lead.last_contacted_at)}</span>
        <span className="lead-account">{accountLabel(accMap, lead.last_account_id)}</span>
        {lead.fail_reason ? <span className="lead-fail">{lead.fail_reason}</span> : null}
      </div>
      {bioPreview ? <div className="lead-bio">{bioPreview}</div> : null}
    </>
  );
}

function LeadModal({ modal, onClose, renderAccount, authToken, csrfToken, refreshLead }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const headers = {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };

  const sendReply = async () => {
    if (!text.trim()) return;
    setSending(true);
    setError(null);
    try {
      const resp = await fetch(
        `${API_BASE}/accounts/${encodeURIComponent(modal.accountId)}/dialogs/${encodeURIComponent(modal.lead.username)}/reply`,
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
      await refreshLead();
    } catch (err) {
      setError(err.message || "Failed to send reply");
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
              @{modal.lead.username} — {modal.lead.name || "No name"}
            </div>
            <div className="modal-subtitle">
              {renderAccount(modal.accountId)} · {modal.lead.status} · {modal.lead.tag}
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          {modal.loading && <div className="muted">Загружаю диалог…</div>}
          {modal.error && <div className="error">{modal.error}</div>}
          {!modal.loading && !modal.error && (
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
