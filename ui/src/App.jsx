import React, { useEffect, useState, useRef } from "react";
import AccountsPanel from "./components/AccountsPanel.jsx";
import MetricsDashboard from "./components/MetricsDashboard.jsx";
import LogsView from "./components/LogsView.jsx";
import LoginView from "./components/LoginView.jsx";
import ClientLanding from "./components/ClientLanding.jsx";
import SettingsPanel from "./components/SettingsPanel.jsx";
import AccountLoginPanel from "./components/AccountLoginPanel.jsx";
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
  if (status === "ACTIVE") return { label: t("status_active"), cls: "status-active", title: t("status_title_active") };
  if (status === "PAUSED") return { label: t("status_paused"), cls: "status-paused", title: t("status_title_paused") };
  if (status === "NEED_RELOGIN") return { label: t("status_login"), cls: "status-login", title: t("status_title_login") };
  if (status === "BANNED") return { label: t("status_banned"), cls: "status-banned", title: t("status_title_banned") };
  return { label: status || t("status_unknown"), cls: "status-paused", title: t("status_title_unknown") };
}
const API_BASE = "/api";
const POLL_INTERVAL = Number(import.meta.env.VITE_POLL_INTERVAL_MS || 8000);
const LOGS_POLL_INTERVAL = Number(import.meta.env.VITE_LOGS_POLL_INTERVAL_MS || POLL_INTERVAL);
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
    settings_admin_title: "Settings (admin)",
    settings_admin_hint: "Limits, warmup, outreach, replies, accounts. Changes apply immediately.",
    btn_restart: "Restart",
    btn_restarting: "Restarting…",
    btn_save: "Save",
    btn_saving: "Saving…",
    settings_limits_title: "Limits",
    settings_limits_hint: "Daily caps for cold outreach and heavy actions.",
    settings_limits_acc_hint: "Cold messages per account per day",
    settings_limits_acc: "Max cold per account / day",
    settings_limits_global_hint: "Global cold messages per day across all accounts",
    settings_limits_global: "Max cold global / day",
    settings_limits_heavy_hint: "Parallel heavy actions allowed",
    settings_limits_heavy: "Max concurrent heavy",
    settings_warmup_title: "Warmup",
    settings_warmup_hint: "Intervals and jitter for warmup (reads/chats).",
    settings_warmup_batch: "Batch interval (s)",
    settings_warmup_batch_hint: "Pause range between warmup batches",
    settings_warmup_batch_sub: "min / max seconds between plans",
    settings_warmup_jitter: "Action jitter (s)",
    settings_warmup_jitter_hint: "Random delay before warmup actions",
    settings_warmup_jitter_sub: "min / max seconds before reads",
    settings_warmup_bot: "Bot read chance (0-1)",
    settings_warmup_bot_hint: "Probability to read bots/users to diversify channel reads",
    settings_outreach_title: "Outreach",
    settings_outreach_hint: "Cold DMs: enable/disable and tune pacing.",
    settings_outreach_enable: "Enable outreach",
    settings_outreach_interval: "Send interval (s)",
    settings_outreach_interval_hint: "Delay range between cold sends",
    settings_outreach_interval_sub: "min / max seconds between sends",
    settings_outreach_batch_hint: "Cold sends per planning batch",
    settings_outreach_batch: "Max per batch",
    settings_replies_title: "Replies",
    settings_replies_hint: "Auto-replies and lead qualification.",
    settings_replies_enable: "Enable replies",
    warmup_actions_label: "Warmup",
    floodwaits_label: "Floodwaits",
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
    settings_admin_title: "Настройки (админ)",
    settings_admin_hint: "Лимиты, прогрев, исходящие, ответы, аккаунты. Применяется сразу.",
    btn_restart: "Рестарт",
    btn_restarting: "Рестарт…",
    btn_save: "Сохранить",
    btn_saving: "Сохраняем…",
    settings_limits_title: "Лимиты",
    settings_limits_hint: "Дневные ограничения на холодные исходящие и тяжёлые действия.",
    settings_limits_acc_hint: "Сколько холодных сообщений на аккаунт в день",
    settings_limits_acc: "Макс. холодных на аккаунт / день",
    settings_limits_global_hint: "Общий лимит холодных сообщений на все аккаунты за день",
    settings_limits_global: "Макс. холодных глобально / день",
    settings_limits_heavy_hint: "Параллельные тяжёлые действия",
    settings_limits_heavy: "Макс. тяжёлых одновременно",
    settings_warmup_title: "Прогрев",
    settings_warmup_hint: "Интервалы и джиттер прогрева (чтение каналов/диалогов).",
    settings_warmup_batch: "Интервал пачек (с)",
    settings_warmup_batch_hint: "Диапазон паузы между пакетами прогрева",
    settings_warmup_batch_sub: "мин / макс секунд между планами",
    settings_warmup_jitter: "Джиттер действий (с)",
    settings_warmup_jitter_hint: "Случайная задержка перед действиями прогрева",
    settings_warmup_jitter_sub: "мин / макс секунд перед чтением",
    settings_warmup_bot: "Вероятность чтения ботов (0-1)",
    settings_warmup_bot_hint: "Шанс разбавить чтение каналов чтением ботов/юзеров",
    settings_outreach_title: "Исходящие",
    settings_outreach_hint: "Холодные DM: включить/выключить и настроить частоту.",
    settings_outreach_enable: "Включить исходящие",
    settings_outreach_interval: "Интервал отправок (с)",
    settings_outreach_interval_hint: "Диапазон задержки между холодными отправками",
    settings_outreach_interval_sub: "мин / макс секунд между отправками",
    settings_outreach_batch_hint: "Сколько холодных отправок за один цикл планирования",
    settings_outreach_batch: "Макс. за цикл",
    settings_replies_title: "Ответы",
    settings_replies_hint: "Автоответы и квалификация лидов.",
    settings_replies_enable: "Включить ответы",
    warmup_actions_label: "Прогрев",
    floodwaits_label: "Floodwait",
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
  const [accountsRange, setAccountsRange] = useState(() => localStorage.getItem("accountsRange") || "30d");

  const authToken = auth?.token || "";

  const envPoll = import.meta.env.VITE_POLL_INTERVAL_MS || "8000";
  const envLogsPoll = import.meta.env.VITE_LOGS_POLL_INTERVAL_MS || envPoll;
  const pollRef = React.useRef({ accounts: null, logs: null });

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

    const rangeParam = accountsRange ? `?range=${encodeURIComponent(accountsRange)}` : "";
    fetchWithAuth(`${API_BASE}/accounts${rangeParam}`)
      .then(setAccounts)
      .catch(console.error);
  }, [auth, accountsRange]);

  useEffect(() => {
    if (!auth || auth.role !== "admin") return;
    fetchWithAuth(`${API_BASE}/logs/events?limit=200`)
      .then(setLogs)
      .catch(console.error);
  }, [auth]);

  useEffect(() => {
    if (!auth || auth.role !== "admin") return;
    const clear = () => {
      if (pollRef.current.logs) {
        clearInterval(pollRef.current.logs);
        pollRef.current.logs = null;
      }
      if (pollRef.current.accounts) {
        clearInterval(pollRef.current.accounts);
        pollRef.current.accounts = null;
      }
    };
    // start polling when admin tab is active
    if (activeTab === "admin") {
      pollRef.current.accounts = setInterval(() => {
        const rangeParam = accountsRange ? `?range=${encodeURIComponent(accountsRange)}` : "";
        fetchWithAuth(`${API_BASE}/accounts${rangeParam}`).then(setAccounts).catch(console.error);
      }, POLL_INTERVAL);
      pollRef.current.logs = setInterval(() => {
        fetchWithAuth(`${API_BASE}/logs/events?limit=200`).then(setLogs).catch(console.error);
      }, LOGS_POLL_INTERVAL);
    }
    return () => clear();
  }, [auth, activeTab, accountsRange]);

  const handleSelectAccount = (acc) => {
    setSelectedAccount(acc);
  };

  const handleLoginSuccess = (session) => {
    setAuth(session);
    localStorage.setItem("auth", JSON.stringify(session));
  };


  const toggleAccount = async (acc) => {
    if (!acc || acc.id == null) return;
    const accId = String(acc.id);
    const status = (acc.status || "").toUpperCase();
    const willPause = status !== "PAUSED";

    // optimistic: flip status locally
    setAccounts((prev) =>
      prev.map((a) =>
        a.id === acc.id
          ? { ...a, status: willPause ? "PAUSED" : "ACTIVE" }
          : a
      )
    );

    try {
      const endpoint = willPause ? "pause" : "resume";
      const resp = await fetch(`${API_BASE}/accounts/${encodeURIComponent(accId)}/${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
      });
      if (!resp.ok) {
        console.error("Toggle failed", resp.status);
      } else {
        const data = await fetchWithAuth(`${API_BASE}/accounts`);
        setAccounts(data);
      }
    } catch (err) {
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
                <SettingsPanel authToken={authToken} accounts={accounts} t={t} />
                <div className="poll-hint muted">Poll: {envPoll} ms · Logs: {envLogsPoll} ms</div>
                <div className="account-cards">
                  <div className="account-cards-header">
                    <h3>{t("accounts")}</h3>
                    <div className="range-switcher account-range-switcher">
                      {["1d", "3d", "7d", "30d", "90d"].map((range) => (
                        <button
                          key={range}
                          className={accountsRange === range ? "chip chip-active" : "chip"}
                          title={`${range} range for metrics`}
                          onClick={() => {
                            setAccountsRange(range);
                            localStorage.setItem("accountsRange", range);
                          }}
                        >
                          {range}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="account-card-grid">
                    {accounts.map((acc) => {
                      if (!acc || acc.id == null) return null;
                      const meta = accountStatusMeta(acc, t);
                      const switchOn = (acc.status || "").toUpperCase() !== "PAUSED";
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
                                title={switchOn ? t("status_active") : t("status_disabled")}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  checked={switchOn}
                                  onChange={() => toggleAccount(acc)}
                                />
                                <span className="slider" />
                              </label>
                            </div>
                          </div>
                          <div className="account-card-body">
                            <div className="account-metrics compact account-metrics-grid">
                              <span>{t("cold_sent")}: {acc.metrics?.cold_sent || 0}</span>
                              <span>{t("replies")}: {acc.metrics?.replies_received || 0}</span>
                              <span>{t("hot")}: {acc.metrics?.hot_leads || 0}</span>
                              <span>{t("warm")}: {acc.metrics?.warm_leads || 0}</span>
                              <span>{t("warmup_actions_label", "Warmup")}: {acc.metrics?.warmup_actions || 0}</span>
                              <span>{t("floodwaits_label", "Floodwaits")}: {acc.metrics?.floodwait_events || 0}</span>
                            </div>
                            {acc.ban_reason || acc.last_error ? (
                              <div className="account-alert">
                                {acc.ban_reason || acc.last_error}
                              </div>
                            ) : null}
                            {typeof acc.floodwait_seconds === "number" ? (
                              <div className="account-subinfo muted">{`Floodwait: ${acc.floodwait_seconds}s`}</div>
                            ) : null}
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
                  const rangeParam = accountsRange ? `?range=${encodeURIComponent(accountsRange)}` : "";
                  const data = await fetchWithAuth(`${API_BASE}/accounts${rangeParam}`);
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
