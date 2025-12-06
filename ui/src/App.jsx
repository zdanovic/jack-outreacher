import React, { useEffect, useState } from "react";
import AccountsPanel from "./components/AccountsPanel.jsx";
import MetricsDashboard from "./components/MetricsDashboard.jsx";
import LogsView from "./components/LogsView.jsx";
import LoginView from "./components/LoginView.jsx";
import ClientLanding from "./components/ClientLanding.jsx";
import SettingsPanel from "./components/SettingsPanel.jsx";
import AccountLoginPanel from "./components/AccountLoginPanel.jsx";
import AdminActions from "./components/AdminActions.jsx";
import LeadsView from "./components/LeadsView.jsx";
import VideoBackground from "./components/VideoBackground.jsx";

function accountDisplay(acc) {
  if (!acc) return "";
  const digits = (acc.phone || "").replace(/\D/g, "");
  const tail = digits ? digits.slice(-4) : "";
  return tail ? `${acc.id} (...${tail})` : acc.id;
}

function accountStatusMeta(acc, t) {
  const status = (acc?.status || "").toUpperCase();
  if (acc?.enabled === false) return { label: t("status_disabled"), cls: "status-disabled", title: t("status_title_disabled") };
  if (status === "ACTIVE") return { label: t("status_active"), cls: "status-active", title: t("status_title_active") };
  if (status === "PAUSED") return { label: t("status_paused"), cls: "status-paused", title: t("status_title_paused") };
  if (status === "NEED_RELOGIN") return { label: t("status_login"), cls: "status-login", title: t("status_title_login") };
  if (status === "BANNED") return { label: t("status_banned"), cls: "status-banned", title: t("status_title_banned") };
  return { label: status || t("status_unknown"), cls: "status-paused", title: t("status_title_unknown") };
}
const API_BASE = "/api";
const translations = {
  en: {
    dashboard: "Dashboard",
    leads: "Leads",
    admin: "Admin",
    accountPrefix: "Account",
    today: "Today",
    cold_sent: "Cold sent",
    replies: "Replies",
    hot: "Hot leads",
    warm: "Warm leads",
    chart_outreach: "Outreach",
    chart_outreach_sub: "Outgoing + replies by day",
    chart_leads: "Lead heat",
    chart_leads_sub: "Hot / warm over time",
    chart_warmup: "Warmup & risk",
    chart_warmup_sub: "Warmup actions and floodwaits",
    latest: "Latest",
    avg7: "7d avg",
    wow: "WoW",
    loading: "Loading…",
    noData: "No data for the period",
    error: "Error",
    accounts: "Accounts",
    replies_short: "replies",
    status_disabled: "Disabled",
    status_active: "Active",
    status_paused: "Paused (manual)",
    status_login: "Paused (login)",
    status_banned: "Paused (ban)",
    status_unknown: "Unknown",
    status_title_disabled: "Turned off manually",
    status_title_active: "Active",
    status_title_paused: "Paused manually",
    status_title_login: "Needs re-login/code",
    status_title_banned: "Banned/logged out",
    status_title_unknown: "State unknown",
    leads_title: "Leads",
    leads_sub: "Kanban (warm/hot/deal) + quick search.",
    filter_last_contact: "Last contact",
    filter_search: "Search",
    filter_search_ph: "Name, username, source…",
    col_warm: "Warm",
    col_warm_hint: "AI qualified / warmed",
    col_hot: "Hot",
    col_hot_hint: "Ready, waiting reply",
    col_deal: "Deal",
    col_deal_hint: "Hand-off to client",
    col_failed: "Failed",
    col_failed_hint: "Errors / needs review",
    status_hot: "Hot",
    status_warm: "Warm",
    status_deal: "Deal",
    status_failed: "Failed",
    logs_title: "Events",
    col_time: "Time",
    col_account: "Account",
    col_action: "Action",
    col_target: "Target",
    col_result: "Result",
    col_info: "Info",
    col_time_hint: "When the action happened",
    col_account_hint: "Account ID (masked tail)",
    col_action_hint: "What was executed",
    col_target_hint: "Target user/chat",
    col_result_hint: "Outcome",
    col_info_hint: "Extra context",
    statuses_title: "Statuses",
    dashboard_tab_hint: "Overview and charts",
    leads_tab_hint: "Pipeline and manual review",
    admin_tab_hint: "Admin tools",
    metric_cold_sent_hint: "Messages sent today",
    metric_replies_hint: "Replies received today",
    metric_hot_hint: "Hot leads in pipeline",
    metric_warm_hint: "Warm leads in pipeline",
  },
  ru: {
    dashboard: "Дашборд",
    leads: "Лиды",
    admin: "Админ",
    accountPrefix: "Аккаунт",
    today: "Сегодня",
    cold_sent: "Исходящие",
    replies: "Ответы",
    hot: "Hot-лиды",
    warm: "Тёплые лиды",
    chart_outreach: "Исходящие",
    chart_outreach_sub: "Отправки и ответы по дням",
    chart_leads: "Лиды",
    chart_leads_sub: "Hot / warm по времени",
    chart_warmup: "Прогрев и риск",
    chart_warmup_sub: "Прогрев и floodwait",
    latest: "Последнее",
    avg7: "Средн. 7д",
    wow: "WoW",
    loading: "Загрузка…",
    noData: "Нет данных за период",
    error: "Ошибка",
    accounts: "Аккаунты",
    replies_short: "ответы",
    status_disabled: "Отключён",
    status_active: "Активен",
    status_paused: "Пауза (ручная)",
    status_login: "Пауза (логин)",
    status_banned: "Бан/логаут",
    status_unknown: "Неизвестно",
    status_title_disabled: "Отключено вручную",
    status_title_active: "Аккаунт работает",
    status_title_paused: "Пауза по ручному решению",
    status_title_login: "Нужен повторный логин/код",
    status_title_banned: "Телеграм забанил/логаут",
    status_title_unknown: "Состояние не определено",
    leads_title: "Лиды",
    leads_sub: "Канбан (warm/hot/deal) + быстрый поиск.",
    filter_last_contact: "Последний контакт",
    filter_search: "Поиск",
    filter_search_ph: "Имя, ник, source…",
    col_warm: "Warm",
    col_warm_hint: "AI-квалификация / прогретые",
    col_hot: "Hot",
    col_hot_hint: "Горячие, ждут ответа",
    col_deal: "Deal",
    col_deal_hint: "Передано клиенту (вручную)",
    col_failed: "Failed",
    col_failed_hint: "Ошибки / нужна проверка",
    status_hot: "Hot",
    status_warm: "Warm",
    status_deal: "Deal",
    status_failed: "Failed",
    logs_title: "События",
    col_time: "Время",
    col_account: "Аккаунт",
    col_action: "Действие",
    col_target: "Цель",
    col_result: "Результат",
    col_info: "Инфо",
    col_time_hint: "Когда произошло действие",
    col_account_hint: "ID аккаунта (хвост номера)",
    col_action_hint: "Что выполнялось",
    col_target_hint: "Цель/контакт",
    col_result_hint: "Результат",
    col_info_hint: "Дополнительные детали",
    statuses_title: "Статусы",
    dashboard_tab_hint: "Обзор и графики",
    leads_tab_hint: "Воронка и ручная проверка",
    admin_tab_hint: "Инструменты админа",
    metric_cold_sent_hint: "Сообщения за сегодня",
    metric_replies_hint: "Ответы за сегодня",
    metric_hot_hint: "Горячих лидов в работе",
    metric_warm_hint: "Тёплых лидов в работе",
  },
};

export default function App() {
  const [auth, setAuth] = useState(() => {
    const raw = localStorage.getItem("auth");
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  });
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [loginModalAcc, setLoginModalAcc] = useState(null);
  const [logs, setLogs] = useState([]);
  const [landingSummary, setLandingSummary] = useState(null);
  const [clientAccounts, setClientAccounts] = useState([]);
  const [lang, setLang] = useState(() => localStorage.getItem("lang") || "en");
  const [activeTab, setActiveTab] = useState(() => {
    const saved = localStorage.getItem("activeTab");
    return saved || "main"; // main | leads | admin
  });

  const authToken = auth?.token || "";

  const logout = () => {
    setAuth(null);
    setAccounts([]);
    setLogs([]);
    setSelectedAccount(null);
    localStorage.removeItem("auth");
  };

  const fetchWithAuth = async (url, options = {}) => {
    const resp = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
    });
    if (resp.status === 401 || resp.status === 403) {
      logout();
      throw new Error("unauthorized");
    }
    return resp.json();
  };

  useEffect(() => {
    if (!auth) return;
    if (auth.role === "client") {
      Promise.all([
        fetchWithAuth(`${API_BASE}/landing/summary`),
        fetchWithAuth(`${API_BASE}/client/accounts`),
      ])
        .then(([summary, ca]) => {
          setLandingSummary(summary);
          setClientAccounts(ca);
        })
        .catch(console.error);
      return;
    }

    fetchWithAuth(`${API_BASE}/accounts`)
      .then(setAccounts)
      .catch(console.error);
  }, [auth]);

  useEffect(() => {
    if (!auth || auth.role !== "admin") return;
    fetchWithAuth(`${API_BASE}/logs/events?limit=200`)
      .then(setLogs)
      .catch(console.error);
  }, [auth]);

  const handleSelectAccount = (acc) => {
    setSelectedAccount(acc);
  };

  const handleLoginSuccess = (session) => {
    setAuth(session);
    localStorage.setItem("auth", JSON.stringify(session));
  };


  const toggleAccount = async (acc) => {
    if (!acc) return;
    const nextEnabled = acc.enabled === false ? true : false;
    setAccounts((prev) => prev.map((a) => (a.id === acc.id ? { ...a, enabled: nextEnabled } : a)));
    try {
      await fetchWithAuth(`${API_BASE}/accounts/${encodeURIComponent(acc.id)}/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      const data = await fetchWithAuth(`${API_BASE}/accounts`);
      setAccounts(data);
    } catch (err) {
      setAccounts((prev) => prev.map((a) => (a.id === acc.id ? { ...a, enabled: acc.enabled } : a)));
      console.error(err);
    }
  };
  const t = (key) => translations[lang]?.[key] || key;

  if (!auth) {
    return (
      <>
        <VideoBackground />
        <LoginView onSuccess={handleLoginSuccess} />
      </>
    );
  }

  if (auth.role === "client") {
    return (
      <>
        <VideoBackground />
        <ClientLanding
          summary={landingSummary}
          accounts={clientAccounts}
          onLogout={logout}
          email={auth.email}
        />
      </>
    );
  }

  return (
    <>
      <VideoBackground />
      <div className={`app-root ${activeTab !== "admin" ? "app-compact" : ""}`}>
        <main className="main">
          <header className="main-header">
            <div className="header-left">
              <img className="header-logo" src="/media/brand/wordmark-tight.webp" alt="Jack OutReacher" />
              <div className="tabs">
                <button
                  title={t("dashboard_tab_hint")}
                  className={activeTab === "main" ? "tab active" : "tab"}
                  onClick={() => {
                    setActiveTab("main");
                    localStorage.setItem("activeTab", "main");
                  }}
                >
                  {t("dashboard")}
                </button>
                {auth.role === "admin" && (
                  <button
                    title={t("leads_tab_hint")}
                    className={activeTab === "leads" ? "tab active" : "tab"}
                    onClick={() => {
                      setActiveTab("leads");
                      localStorage.setItem("activeTab", "leads");
                    }}
                  >
                    {t("leads")}
                  </button>
                )}
                {auth.role === "admin" && (
                  <button
                    title={t("admin_tab_hint")}
                    className={activeTab === "admin" ? "tab active" : "tab"}
                    onClick={() => {
                      setActiveTab("admin");
                      localStorage.setItem("activeTab", "admin");
                    }}
                  >
                    {t("admin")}
                  </button>
                )}
              </div>
            </div>
            <div className="header-title">
              {activeTab === "main"
                ? selectedAccount
                  ? `${t("accountPrefix")}: ${selectedAccount.id}`
                  : t("dashboard")
                : activeTab === "leads"
                ? t("leads")
              : t("admin")}
            </div>
            <div className="header-user">
              <span>{auth.email}</span>
              <button onClick={logout}>Log out</button>
              <button
                className="lang-switch"
                aria-label="Switch language"
                onClick={() => {
                  const next = lang === "en" ? "ru" : "en";
                  setLang(next);
                  localStorage.setItem("lang", next);
                }}
              >
                {lang === "en" ? "EN" : "RU"}
              </button>
            </div>
          </header>
          {activeTab === "main" && (
            <section className="main-content">
              <div className="main-left">
                <MetricsDashboard accounts={accounts} authToken={authToken} t={t} />
              </div>
              <div className="main-right">
                <LogsView logs={logs} authToken={authToken} accounts={accounts} t={t} />
              </div>
            </section>
          )}
          {activeTab === "leads" && auth.role === "admin" && (
            <section className="main-content leads-section">
              <LeadsView authToken={authToken} accounts={accounts} t={t} />
            </section>
          )}
          {activeTab === "admin" && auth.role === "admin" && (
            <section className="main-content">
              <div className="main-left">
                <AccountLoginPanel
                  account={selectedAccount}
                  authToken={authToken}
                  refreshAccounts={async () => {
                    try {
                      const data = await fetchWithAuth(`${API_BASE}/accounts`);
                      setAccounts(data);
                    } catch (err) {
                      console.error(err);
                    }
                  }}
                />
                <SettingsPanel authToken={authToken} accounts={accounts} />
                <AdminActions authToken={authToken} />
                <div className="account-cards">
                  <h3>{t("accounts")}</h3>
                  <div className="account-card-grid">
                    {accounts.map((acc) => {
                      const meta = accountStatusMeta(acc, t);
                      const enabled = acc.enabled !== false;
                      return (
                        <div
                          key={acc.id}
                          className="account-card"
                          onClick={() => setLoginModalAcc(acc)}
                        >
                          <div className="account-card-head">
                            <div className="account-id">{accountDisplay(acc)}</div>
                            <div className="account-head-actions">
                              <span className={`status-pill ${meta.cls}`} title={meta.title}>
                                {meta.label}
                              </span>
                              <label
                                className="switch"
                                title={enabled ? t("status_active") : t("status_disabled")}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  checked={enabled}
                                  onChange={() => toggleAccount(acc)}
                                />
                                <span className="slider" />
                              </label>
                            </div>
                          </div>
                          <div className="account-card-body">
                            <div className="account-metrics compact">
                              <span>{t("cold_sent")}: {acc.metrics?.cold_sent || 0}</span>
                              <span>{t("replies")}: {acc.metrics?.replies_received || 0}</span>
                              <span>Floodwaits: {acc.metrics?.floodwait_events || 0}</span>
                            </div>
                            {acc.ban_reason || acc.last_error ? (
                              <div className="account-alert">
                                {acc.ban_reason || acc.last_error}
                              </div>
                            ) : null}
                            <div className="account-hint muted">
                              {typeof acc.floodwait_seconds === "number"
                                ? `Floodwait: ${acc.floodwait_seconds}s`
                                : "Floodwait: —"}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </section>
          )}
              {loginModalAcc && (
        <div className="modal-backdrop" onClick={() => setLoginModalAcc(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <AccountLoginPanel
              account={loginModalAcc}
              authToken={authToken}
              refreshAccounts={async () => {
                try {
                  const data = await fetchWithAuth(`${API_BASE}/accounts`);
                  setAccounts(data);
                } catch (err) {
                  console.error(err);
                }
              }}
            />
            <div className="modal-actions" style={{ justifyContent: "flex-end" }}>
              <button className="toggle toggle-off" onClick={() => setLoginModalAcc(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

        </main>
      </div>
    </>
  );
}
