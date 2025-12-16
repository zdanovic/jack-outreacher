import React, { useEffect, useState } from "react";

const API_BASE = "/api";

export default function SettingsPanel({ authToken, csrfToken, accounts, t }) {
  const tr = (key, fallback) => (typeof t === "function" ? t(key) : null) || fallback || key;
  const SAFE_DEFAULTS = {
    limits: {
      max_cold_per_account_per_day: 15,
      max_cold_global_per_day: 80,
      max_concurrent_heavy_actions: 2,
      min_cold_interval_seconds: 900, // 15 minutes between cold sends
      max_cold_per_hour_per_account: 2,
    },
    warmup: {
      batch_interval_min: 300,
      batch_interval_max: 900,
      night_batch_interval_min: 900,
      night_batch_interval_max: 1800,
      action_jitter_min: 10,
      action_jitter_max: 120,
      bot_read_chance: 0.2,
      quiet_hours_start: 0,
      quiet_hours_end: 6,
      max_read_dialogs_per_hour: 2,
    },
    outreach: {
      enabled: true,
      send_interval_min: 900,
      send_interval_max: 3600,
      max_per_batch: 1,
    },
    replies: { enabled: true },
  };
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [restartLoading, setRestartLoading] = useState(false);
  const [restartMessage, setRestartMessage] = useState(null);

  const headers = {
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/settings`, { headers, credentials: "include" })
      .then((res) => res.json())
      .then((data) => setSettings(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [authToken]);

  const updateSection = (section, key, value) => {
    setSettings((prev) => ({
      ...prev,
      [section]: {
        ...(prev?.[section] || {}),
        [key]: value,
      },
    }));
  };

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/settings`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          limits: settings.limits,
          warmup: settings.warmup,
          outreach: settings.outreach,
          replies: settings.replies,
          accounts: settings.accounts,
        }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(t || "Failed to save settings");
      }
      const data = await resp.json();
      setSettings(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const restart = async () => {
    setRestartLoading(true);
    setRestartMessage(null);
    try {
      const resp = await fetch(`${API_BASE}/admin/restart`, {
        method: "POST",
        credentials: "include",
        headers,
      });
      const data = await resp.json();
      setRestartMessage(
        data.message || tr("restart_status_sent", "Restart request sent. Restart via process manager if needed.")
      );
    } catch (err) {
      setRestartMessage(err.message || tr("restart_status_fail", "Failed to send restart command"));
    } finally {
      setRestartLoading(false);
    }
  };

  if (loading) return <div className="settings-panel">Loading settings…</div>;
  if (!settings) return null;

  const accountLabel = (accId) => {
    const acc = accounts.find((a) => a.id === accId);
    if (!acc || !acc.phone) return accId;
    const digits = acc.phone.replace(/\D/g, "");
    const tail = digits.slice(-4);
    return (
      <>
        {accId} <span className="account-phone-hint">(...{tail || "????"})</span>
      </>
    );
  };

  const RangeField = ({
    label,
    title,
    minValue,
    maxValue,
    onMinChange,
    onMaxChange,
    minPlaceholder = "",
    maxPlaceholder = "",
    hint,
  }) => (
    <div className="range-field" title={title}>
      <div className="range-field-label">
        <span>{label}</span>
        {hint && <span className="subhint">{hint}</span>}
      </div>
      <div className="range-field-inputs">
        <input
          type="number"
          value={minValue ?? ""}
          placeholder={minPlaceholder}
          onChange={(e) => {
            const val = e.target.value;
            onMinChange(val === "" ? undefined : Number(val));
          }}
        />
        <input
          type="number"
          value={maxValue ?? ""}
          placeholder={maxPlaceholder}
          onChange={(e) => {
            const val = e.target.value;
            onMaxChange(val === "" ? undefined : Number(val));
          }}
        />
      </div>
    </div>
  );

  return (
    <section className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>{tr("settings_admin_title", "Settings (admin)")}</h2>
          <p className="muted">{tr("settings_admin_hint", "Limits, warmup, outreach, replies, accounts. Changes apply immediately.")}</p>
        </div>
        <div className="settings-actions-buttons">
          <button onClick={restart} disabled={restartLoading}>
            {restartLoading ? tr("btn_restarting", "Restarting…") : tr("btn_restart", "Restart")}
          </button>
          <button onClick={save} disabled={saving}>
            {saving ? tr("btn_saving", "Saving…") : tr("btn_save", "Save")}
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {restartMessage && <div className="muted restart-hint">{restartMessage}</div>}

      <div className="settings-grid">
        <div className="settings-card">
          <h3>{tr("settings_limits_title", "Limits")}</h3>
          <div className="setting-hint">{tr("settings_limits_hint", "Daily caps for cold outreach and heavy actions.")}</div>
          <label title={tr("settings_limits_acc_hint", "Cold messages per account per day")}>
            <span>{tr("settings_limits_acc", "Max cold per account / day")}</span>
            <input
              type="number"
              value={settings.limits?.max_cold_per_account_per_day ?? ""}
              placeholder={SAFE_DEFAULTS.limits.max_cold_per_account_per_day}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("limits", "max_cold_per_account_per_day", val === "" ? undefined : Number(val));
              }}
            />
          </label>
          <label title={tr("settings_limits_global_hint", "Global cold messages per day across all accounts")}>
            <span>{tr("settings_limits_global", "Max cold global / day")}</span>
            <input
              type="number"
              value={settings.limits?.max_cold_global_per_day ?? ""}
              placeholder={SAFE_DEFAULTS.limits.max_cold_global_per_day}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("limits", "max_cold_global_per_day", val === "" ? undefined : Number(val));
              }}
            />
          </label>
          <label title={tr("settings_limits_heavy_hint", "Parallel heavy actions allowed")}>
            <span>{tr("settings_limits_heavy", "Max concurrent heavy")}</span>
            <input
              type="number"
              value={settings.limits?.max_concurrent_heavy_actions ?? ""}
              placeholder={SAFE_DEFAULTS.limits.max_concurrent_heavy_actions}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("limits", "max_concurrent_heavy_actions", val === "" ? undefined : Number(val));
              }}
            />
          </label>
          <label title={tr("settings_limits_interval_hint", "Minimum seconds between cold sends per account (soft throttle)")}>
            <span>{tr("settings_limits_interval", "Min interval between cold sends (s)")}</span>
            <input
              type="number"
              value={settings.limits?.min_cold_interval_seconds ?? ""}
              placeholder={SAFE_DEFAULTS.limits.min_cold_interval_seconds}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("limits", "min_cold_interval_seconds", val === "" ? undefined : Number(val));
              }}
            />
          </label>
          <label title={tr("settings_limits_hour_hint", "Soft cap per account per hour (0 disables)")}>
            <span>{tr("settings_limits_hour", "Max cold per hour / account")}</span>
            <input
              type="number"
              value={settings.limits?.max_cold_per_hour_per_account ?? ""}
              placeholder={SAFE_DEFAULTS.limits.max_cold_per_hour_per_account}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("limits", "max_cold_per_hour_per_account", val === "" ? undefined : Number(val));
              }}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>{tr("settings_warmup_title", "Warmup")}</h3>
          <div className="setting-hint">{tr("settings_warmup_hint", "Intervals and jitter for warmup (reads/chats).")}</div>
          <RangeField
            label={tr("settings_warmup_batch", "Batch interval (s)")}
            title={tr("settings_warmup_batch_hint", "Pause range between warmup batches")}
            hint={tr("settings_warmup_batch_sub", "min / max seconds between plans")}
            minValue={settings.warmup?.batch_interval_min}
            maxValue={settings.warmup?.batch_interval_max}
            minPlaceholder={SAFE_DEFAULTS.warmup.batch_interval_min}
            maxPlaceholder={SAFE_DEFAULTS.warmup.batch_interval_max}
            onMinChange={(v) => updateSection("warmup", "batch_interval_min", v)}
            onMaxChange={(v) => updateSection("warmup", "batch_interval_max", v)}
          />
          <RangeField
            label={tr("settings_warmup_batch_night", "Batch interval at night (s)")}
            title={tr("settings_warmup_batch_night_hint", "Longer pauses during quiet hours")}
            hint={tr("settings_warmup_batch_sub", "min / max seconds between plans")}
            minValue={settings.warmup?.night_batch_interval_min}
            maxValue={settings.warmup?.night_batch_interval_max}
            minPlaceholder={SAFE_DEFAULTS.warmup.night_batch_interval_min}
            maxPlaceholder={SAFE_DEFAULTS.warmup.night_batch_interval_max}
            onMinChange={(v) => updateSection("warmup", "night_batch_interval_min", v)}
            onMaxChange={(v) => updateSection("warmup", "night_batch_interval_max", v)}
          />
          <RangeField
            label={tr("settings_warmup_jitter", "Action jitter (s)")}
            title={tr("settings_warmup_jitter_hint", "Random delay before warmup actions")}
            hint={tr("settings_warmup_jitter_sub", "min / max seconds before reads")}
            minValue={settings.warmup?.action_jitter_min}
            maxValue={settings.warmup?.action_jitter_max}
            minPlaceholder={SAFE_DEFAULTS.warmup.action_jitter_min}
            maxPlaceholder={SAFE_DEFAULTS.warmup.action_jitter_max}
            onMinChange={(v) => updateSection("warmup", "action_jitter_min", v)}
            onMaxChange={(v) => updateSection("warmup", "action_jitter_max", v)}
          />
          <label title={tr("settings_warmup_bot_hint", "Probability to read bots/users to diversify channel reads")}>
            <span>{tr("settings_warmup_bot", "Bot read chance (0-1)")}</span>
            <input
              type="number"
              step="0.05"
              value={settings.warmup?.bot_read_chance ?? ""}
              placeholder={SAFE_DEFAULTS.warmup.bot_read_chance}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("warmup", "bot_read_chance", val === "" ? undefined : Number(val));
              }}
            />
          </label>
          <label title={tr("settings_warmup_quiet_hint", "Local hours when warmup is slowed down")}>
            <span>{tr("settings_warmup_quiet", "Quiet hours (start-end, local)")}</span>
            <div className="range-field-inputs">
              <input
                type="number"
                min="0"
                max="23"
                value={settings.warmup?.quiet_hours_start ?? ""}
                placeholder={SAFE_DEFAULTS.warmup.quiet_hours_start}
                onChange={(e) => {
                  const val = e.target.value;
                  updateSection("warmup", "quiet_hours_start", val === "" ? undefined : Number(val));
                }}
              />
              <input
                type="number"
                min="0"
                max="23"
                value={settings.warmup?.quiet_hours_end ?? ""}
                placeholder={SAFE_DEFAULTS.warmup.quiet_hours_end}
                onChange={(e) => {
                  const val = e.target.value;
                  updateSection("warmup", "quiet_hours_end", val === "" ? undefined : Number(val));
                }}
              />
            </div>
          </label>
          <label title={tr("settings_warmup_dialogs_hint", "Soft cap on dialog reads per hour")}>
            <span>{tr("settings_warmup_dialogs", "Max dialog reads per hour")}</span>
            <input
              type="number"
              value={settings.warmup?.max_read_dialogs_per_hour ?? ""}
              placeholder={SAFE_DEFAULTS.warmup.max_read_dialogs_per_hour}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("warmup", "max_read_dialogs_per_hour", val === "" ? undefined : Number(val));
              }}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>{tr("settings_outreach_title", "Outreach")}</h3>
          <div className="setting-hint">{tr("settings_outreach_hint", "Cold DMs: enable/disable and tune pacing.")}</div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={settings.outreach?.enabled ?? true}
              onChange={(e) => updateSection("outreach", "enabled", e.target.checked)}
            />
            {tr("settings_outreach_enable", "Enable outreach")}
          </label>
          <RangeField
            label={tr("settings_outreach_interval", "Send interval (s)")}
            title={tr("settings_outreach_interval_hint", "Delay range between cold sends")}
            hint={tr("settings_outreach_interval_sub", "min / max seconds between sends")}
            minValue={settings.outreach?.send_interval_min}
            maxValue={settings.outreach?.send_interval_max}
            minPlaceholder={SAFE_DEFAULTS.outreach.send_interval_min}
            maxPlaceholder={SAFE_DEFAULTS.outreach.send_interval_max}
            onMinChange={(v) => updateSection("outreach", "send_interval_min", v)}
            onMaxChange={(v) => updateSection("outreach", "send_interval_max", v)}
          />
          <label title={tr("settings_outreach_batch_hint", "Cold sends per planning batch")}>
            <span>{tr("settings_outreach_batch", "Max per batch")}</span>
            <input
              type="number"
              value={settings.outreach?.max_per_batch ?? ""}
              placeholder={SAFE_DEFAULTS.outreach.max_per_batch}
              onChange={(e) => {
                const val = e.target.value;
                updateSection("outreach", "max_per_batch", val === "" ? undefined : Number(val));
              }}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>{tr("settings_replies_title", "Replies")}</h3>
          <div className="setting-hint">{tr("settings_replies_hint", "Auto-replies and lead qualification.")}</div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={settings.replies?.enabled ?? true}
              onChange={(e) => updateSection("replies", "enabled", e.target.checked)}
            />
            {tr("settings_replies_enable", "Enable replies")}
          </label>
        </div>

      </div>
    </section>
  );
}
