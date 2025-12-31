import React from "react";
import { accountDisplayId, accountKey, accountPhoneTail } from "../utils/accounts.js";

function displayName(acc) {
  const label = accountDisplayId(acc);
  const tail = accountPhoneTail(acc);
  if (!tail) return label;
  return (
    <>
      {label}{" "}
      <span className="account-phone-hint">
        (...{tail || "????"})
      </span>
    </>
  );
}

function statusMeta(acc, t) {
  const status = (acc.status || "").toUpperCase();
  if (acc.enabled === false) {
    return { label: t("status_disabled"), cls: "status-disabled", title: t("status_title_disabled") };
  }
  if (status === "ACTIVE") {
    return { label: t("status_active"), cls: "status-active", title: t("status_title_active") };
  }
  if (status === "PAUSED") {
    return { label: t("status_paused"), cls: "status-paused", title: t("status_title_paused") };
  }
  if (status === "NEED_RELOGIN") {
    return { label: t("status_login"), cls: "status-login", title: t("status_title_login") };
  }
  if (status === "BANNED") {
    return { label: t("status_banned"), cls: "status-banned", title: t("status_title_banned") };
  }
  return { label: status || t("status_unknown"), cls: "status-paused", title: t("status_title_unknown") };
}

export default function AccountsPanel({ accounts, selected, onSelect, authToken, refreshAccounts, t }) {
  return (
    <div className="accounts-panel">
      <h2>{t("accounts")}</h2>
      <ul>
        {accounts.map((acc) => (
          <li
            key={accountKey(acc)}
            className={
              "account-item" +
              (selected && accountKey(selected) === accountKey(acc) ? " account-item-selected" : "")
            }
            onClick={() => onSelect(acc)}
          >
            <div className="account-id">{displayName(acc)}</div>
            <StatusPill acc={acc} t={t} />
            <div className="account-metrics">
              <span>
              {t("cold_sent")}: {acc.metrics?.cold_sent || 0}
              </span>
              <span>
                {t("replies_short")}: {acc.metrics?.replies_received || 0}
              </span>
            </div>
            {(acc.login_required || acc.ban_reason || acc.last_error) && (
              <div className="account-alerts">
                {acc.login_required && (
                  <span className="status-pill status-login" title={t("status_title_login")}>
                    {t("login_required")}
                  </span>
                )}
                {acc.ban_reason && (
                  <span className="status-pill status-banned" title={acc.ban_reason}>
                    {t("status_banned")}
                  </span>
                )}
                {!acc.ban_reason && acc.last_error && (
                  <span className="status-pill status-paused" title={acc.last_error}>
                    {t("last_error")}
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatusPill({ acc, t }) {
  const meta = statusMeta(acc, t);
  return (
    <div className="account-status" title={meta.title}>
      <span className={`status-pill ${meta.cls}`}>{meta.label}</span>
    </div>
  );
}
