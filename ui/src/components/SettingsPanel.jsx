import React, { useEffect, useState } from "react";

const API_BASE = "/api";

export default function SettingsPanel({ authToken, accounts }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

  useEffect(() => {
    if (!authToken) return;
    setLoading(true);
    fetch(`${API_BASE}/settings`, { headers })
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

  const toggleAccount = (accountId) => {
    setSettings((prev) => {
      const overrides = { ...(prev?.accounts?.overrides || {}) };
      const current = overrides[accountId] || { enabled: true };
      overrides[accountId] = { enabled: !current.enabled };
      return {
        ...prev,
        accounts: { overrides },
      };
    });
  };

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/settings`, {
        method: "PUT",
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
    minPlaceholder = "min",
    maxPlaceholder = "max",
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
          value={minValue ?? 0}
          placeholder={minPlaceholder}
          onChange={(e) => onMinChange(Number(e.target.value))}
        />
        <input
          type="number"
          value={maxValue ?? 0}
          placeholder={maxPlaceholder}
          onChange={(e) => onMaxChange(Number(e.target.value))}
        />
      </div>
    </div>
  );

  return (
    <section className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>Settings (admin)</h2>
          <p className="muted">Лимиты, warmup, outreach, ответы, аккаунты. Изменения сохраняются сразу.</p>
        </div>
        <button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="settings-grid">
        <div className="settings-card">
          <h3>Limits</h3>
          <div className="setting-hint">Дневные ограничения на холодные исходящие и тяжёлые действия.</div>
          <label title="Сколько холодных сообщений может отправить один аккаунт за день">
            <span>Max cold per account / day</span>
            <input
              type="number"
              value={settings.limits?.max_cold_per_account_per_day ?? 0}
              onChange={(e) => updateSection("limits", "max_cold_per_account_per_day", Number(e.target.value))}
            />
          </label>
          <label title="Общий лимит холодных сообщений на все аккаунты за день">
            <span>Max cold global / day</span>
            <input
              type="number"
              value={settings.limits?.max_cold_global_per_day ?? 0}
              onChange={(e) => updateSection("limits", "max_cold_global_per_day", Number(e.target.value))}
            />
          </label>
          <label title="Сколько тяжёлых действий (например, отправок) параллельно">
            <span>Max concurrent heavy</span>
            <input
              type="number"
              value={settings.limits?.max_concurrent_heavy_actions ?? 0}
              onChange={(e) => updateSection("limits", "max_concurrent_heavy_actions", Number(e.target.value))}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>Warmup</h3>
          <div className="setting-hint">Интервалы и джиттер прогрева (чтение каналов/диалогов).</div>
          <RangeField
            label="Batch interval (s)"
            title="Диапазон паузы между пакетами прогрева"
            hint="min / max секунд между планами"
            minValue={settings.warmup?.batch_interval_min}
            maxValue={settings.warmup?.batch_interval_max}
            onMinChange={(v) => updateSection("warmup", "batch_interval_min", v)}
            onMaxChange={(v) => updateSection("warmup", "batch_interval_max", v)}
          />
          <RangeField
            label="Action jitter (s)"
            title="Случайная задержка перед действиями прогрева"
            hint="min / max секунд перед чтением"
            minValue={settings.warmup?.action_jitter_min}
            maxValue={settings.warmup?.action_jitter_max}
            onMinChange={(v) => updateSection("warmup", "action_jitter_min", v)}
            onMaxChange={(v) => updateSection("warmup", "action_jitter_max", v)}
          />
          <label title="Вероятность читать ботов/юзеров, чтобы разбавить паттерн чтения каналов">
            <span>Bot read chance (0-1)</span>
            <input
              type="number"
              step="0.05"
              value={settings.warmup?.bot_read_chance ?? 0}
              onChange={(e) => updateSection("warmup", "bot_read_chance", Number(e.target.value))}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>Outreach</h3>
          <div className="setting-hint">Управление холодными DM: включить/выключить и настроить частоту.</div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={settings.outreach?.enabled ?? true}
              onChange={(e) => updateSection("outreach", "enabled", e.target.checked)}
            />
            Enable outreach
          </label>
          <RangeField
            label="Send interval (s)"
            title="Диапазон задержки между холодными отправками"
            hint="min / max секунд между отправками"
            minValue={settings.outreach?.send_interval_min}
            maxValue={settings.outreach?.send_interval_max}
            onMinChange={(v) => updateSection("outreach", "send_interval_min", v)}
            onMaxChange={(v) => updateSection("outreach", "send_interval_max", v)}
          />
          <label title="Сколько холодных отправок за один цикл планирования">
            <span>Max per batch</span>
            <input
              type="number"
              value={settings.outreach?.max_per_batch ?? 1}
              onChange={(e) => updateSection("outreach", "max_per_batch", Number(e.target.value))}
            />
          </label>
        </div>

        <div className="settings-card">
          <h3>Replies</h3>
          <div className="setting-hint">Автоответы и квалификация лидов.</div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={settings.replies?.enabled ?? true}
              onChange={(e) => updateSection("replies", "enabled", e.target.checked)}
            />
            Enable replies
          </label>
        </div>

        <div className="settings-card">
          <h3>Accounts</h3>
          <div className="setting-hint">
            Мгновенно выключить/включить аккаунт без правки .env. Статус обновится сразу.
          </div>
          <div className="account-toggle-list">
            {accounts.map((acc) => {
              const overrides = settings.accounts?.overrides || {};
              const enabled = overrides[acc.id]?.enabled ?? true;
              return (
                <div key={acc.id} className="account-toggle">
                  <span>{accountLabel(acc.id)}</span>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => toggleAccount(acc.id)}
                    />
                    <span className="slider"></span>
                  </label>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
