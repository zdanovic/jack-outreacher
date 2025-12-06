import React, { useEffect, useMemo, useState } from "react";

const API_BASE = "/api";

export default function MetricsDashboard({ accounts, authToken, t = (k) => k }) {
  const aggregate = accounts.reduce(
    (acc, a) => {
      const m = a.metrics || {};
      acc.cold_sent += m.cold_sent || 0;
      acc.replies += m.replies_received || 0;
      acc.hot += m.hot_leads || 0;
      acc.warm += m.warm_leads || 0;
      return acc;
    },
    { cold_sent: 0, replies: 0, hot: 0, warm: 0 }
  );

  const [range, setRange] = useState(30);
  const [series, setSeries] = useState({ by_date: [], per_account: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const fetchSeries = async () => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetch(`${API_BASE}/metrics/timeseries?days=${range}`, {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        });
        if (resp.status === 404) {
          // API not yet restarted or endpoint missing; show empty data but no crash.
          if (!cancelled) setSeries({ by_date: [], per_account: {} });
          return;
        }
        if (!resp.ok) throw new Error(`Failed to load metrics: ${resp.status}`);
        const data = await resp.json();
        if (!cancelled) setSeries(data);
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load metrics");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchSeries();
    return () => {
      cancelled = true;
    };
  }, [range, authToken]);

  const byDate = series?.by_date || [];

  const outreachSeries = useMemo(() => {
    return [
      { label: t("cold_sent"), color: "#38bdf8", points: byDate.map((d) => d.cold_sent || 0) },
      { label: t("replies"), color: "#22c55e", points: byDate.map((d) => d.replies_received || 0) },
    ];
  }, [byDate, t]);

  const leadsSeries = useMemo(() => {
    return [
      { label: t("hot"), color: "#f97316", points: byDate.map((d) => d.hot_leads || 0) },
      { label: t("warm"), color: "#fb7185", points: byDate.map((d) => d.warm_leads || 0) },
    ];
  }, [byDate, t]);

  const warmupSeries = useMemo(() => {
    return [
      { label: "Warmup actions", color: "#6366f1", points: byDate.map((d) => d.warmup_actions || 0) },
      { label: "Floodwait events", color: "#ef4444", points: byDate.map((d) => d.floodwait_events || 0) },
    ];
  }, [byDate]);

  const totals = useMemo(() => {
    const sum = (key) => byDate.reduce((acc, d) => acc + (d[key] || 0), 0);
    return {
      cold_sent: sum("cold_sent"),
      replies: sum("replies_received"),
      hot: sum("hot_leads"),
      warm: sum("warm_leads"),
      warmup: sum("warmup_actions"),
      flood: sum("floodwait_events"),
    };
  }, [byDate]);


  return (
    <section className="metrics-dashboard">
      <div className="dashboard-header">
        <h2>{t("dashboard")}</h2>
      </div>

      <h3>{t("today")}</h3>
      <div className="metric-grid">
        <div className="metric-card" title={t("metric_cold_sent_hint")}>
          <div className="metric-label">{t("cold_sent")}</div>
          <div className="metric-value">{aggregate.cold_sent}</div>
        </div>
        <div className="metric-card" title={t("metric_replies_hint")}>
          <div className="metric-label">{t("replies")}</div>
          <div className="metric-value">{aggregate.replies}</div>
        </div>
        <div className="metric-card" title={t("metric_hot_hint")}>
          <div className="metric-label">{t("hot")}</div>
          <div className="metric-value">{aggregate.hot}</div>
        </div>
        <div className="metric-card" title={t("metric_warm_hint")}>
          <div className="metric-label">{t("warm")}</div>
          <div className="metric-value">{aggregate.warm}</div>
        </div>
      </div>

      <div className="range-switcher range-switcher-inline" aria-label="Select range">
        {[1, 3, 7, 30, 90].map((r) => (
          <button
            key={r}
            className={range === r ? "chip chip-active" : "chip"}
            onClick={() => setRange(r)}
            title={`${r}d range`}
          >
            {r}d
          </button>
        ))}
      </div>

      <div className="charts-grid">
        <ChartCard
          title={t("chart_outreach")}
          subtitle={t("chart_outreach_sub")}
          labels={byDate.map((d) => d.date)}
          series={outreachSeries}
          loading={loading}
          error={error}
          t={t}
        />
        <ChartCard
          title={t("chart_leads")}
          subtitle={t("chart_leads_sub")}
          labels={byDate.map((d) => d.date)}
          series={leadsSeries}
          loading={loading}
          error={error}
          t={t}
        />
        <ChartCard
          title={t("chart_warmup")}
          subtitle={t("chart_warmup_sub")}
          labels={byDate.map((d) => d.date)}
          series={warmupSeries}
          loading={loading}
          error={error}
          t={t}
        />
      </div>

      <div className="summary-grid" aria-label="Totals for selected range">
        <div className="summary-card">
          <div className="metric-label">{t("cold_sent")} Σ</div>
          <div className="metric-value">{totals.cold_sent}</div>
        </div>
        <div className="summary-card">
          <div className="metric-label">{t("replies")} Σ</div>
          <div className="metric-value">{totals.replies}</div>
        </div>
        <div className="summary-card">
          <div className="metric-label">{t("hot")} Σ</div>
          <div className="metric-value">{totals.hot}</div>
        </div>
        <div className="summary-card">
          <div className="metric-label">{t("warm")} Σ</div>
          <div className="metric-value">{totals.warm}</div>
        </div>
        <div className="summary-card">
          <div className="metric-label">Warmup Σ</div>
          <div className="metric-value">{totals.warmup}</div>
        </div>
        <div className="summary-card">
          <div className="metric-label">Floodwait Σ</div>
          <div className="metric-value">{totals.flood}</div>
        </div>
      </div>
    </section>
  );
}

function ChartCard({ title, subtitle, labels, series, loading, error, t = (k) => k }) {
  const insights = useMemo(() => calcInsights(labels, series), [labels, series]);
  const hasData = series?.some((s) => (s.points || []).some((v) => v > 0));
  return (
    <div className="chart-card">
      <div className="chart-header">
        <div>
          <div className="chart-title">{title}</div>
          <div className="chart-subtitle">{subtitle}</div>
        </div>
        <Legend series={series} />
      </div>
      {insights && (
        <div className="chart-insights">
          <div className="chart-pill" title="Сумма всех серий за последний день">
            {t("latest")}: {insights.latest}
          </div>
          <div className="chart-pill" title="Среднее за последние 7 дней (или меньше, если данных мало)">
            {t("avg7")}: {insights.avg7}
          </div>
          <div
            className={
              "chart-pill " +
              (insights.wowDelta > 0 ? "pill-up" : insights.wowDelta < 0 ? "pill-down" : "pill-flat")
            }
            title="Сравнение последнего дня с предыдущим"
          >
            {t("wow")}: {insights.wowDelta > 0 ? "+" : ""}
            {insights.wowDelta}%
          </div>
        </div>
      )}
      <div className="chart-body">
      {loading && <div className="muted">Загрузка…</div>}
        {error && <div className="error">{error}</div>}
        {!loading && !error && labels?.length ? (
          <MiniChart labels={labels} series={series} />
        ) : null}
        {!loading && !error && !hasData && <div className="muted">Нет данных за период</div>}
      </div>
    </div>
  );
}

function calcInsights(labels = [], series = []) {
  if (!labels.length || !series.length) return null;
  const totals = labels.map((_, idx) =>
    series.reduce((sum, s) => sum + (s.points?.[idx] || 0), 0)
  );
  const latest = totals[totals.length - 1] || 0;
  const last7 = totals.slice(-7);
  const avg7 = last7.length ? Math.round(last7.reduce((a, b) => a + b, 0) / last7.length) : 0;
  let wowDelta = 0;
  if (totals.length >= 2) {
    const prev = totals[totals.length - 2] || 0;
    wowDelta = prev === 0 ? (latest > 0 ? 100 : 0) : Math.round(((latest - prev) / prev) * 100);
  }
  return { latest, avg7, wowDelta };
}

function Legend({ series }) {
  if (!series?.length) return null;
  return (
    <div className="chart-legend">
      {series.map((s) => (
        <div key={s.label} className="legend-item">
          <span className="legend-dot" style={{ background: s.color }} />
          {s.label}
        </div>
      ))}
    </div>
  );
}

function MiniChart({ labels = [], series = [] }) {
  const width = 320;
  const height = 120;
  const padding = 12;
  const maxVal = Math.max(
    1,
    ...series.flatMap((s) => (s.points || []).map((v) => (typeof v === "number" ? v : 0)))
  );
  const steps = Math.max(1, labels.length - 1);
  const gridLines = [0.25, 0.5, 0.75];

  const coordsFor = (points) =>
    (points || []).map((v, idx) => {
      const x = (idx / steps) * (width - padding * 2) + padding;
      const y = height - padding - (v / maxVal) * (height - padding * 2);
      return { x, y };
    });

  const smoothPath = (coords = [], smoothing = 0.18) => {
    if (!coords.length) return "";
    if (coords.length < 3) {
      return coords.reduce(
        (acc, p, i) => acc + (i === 0 ? `M ${p.x},${p.y}` : ` L ${p.x},${p.y}`),
        ""
      );
    }
    const lines = coords.map((point, i, arr) => {
      if (i === 0) return `M ${point.x},${point.y}`;
      const prev = arr[i - 1];
      const next = arr[i + 1] || point;
      const prev2 = arr[i - 2] || prev;
      const cp1x = prev.x + (point.x - prev2.x) * smoothing;
      const cp1y = prev.y + (point.y - prev2.y) * smoothing;
      const cp2x = point.x - (next.x - prev.x) * smoothing;
      const cp2y = point.y - (next.y - prev.y) * smoothing;
      return `C ${cp1x},${cp1y} ${cp2x},${cp2y} ${point.x},${point.y}`;
    });
    return lines.join(" ");
  };

  const startLabel = labels[0]
    ? new Date(labels[0]).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "";
  const endLabel =
    labels.length > 1 && labels[labels.length - 1]
      ? new Date(labels[labels.length - 1]).toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : startLabel;

  return (
    <div className="mini-chart">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <line
          x1={padding}
          y1={height - padding}
          x2={width - padding}
          y2={height - padding}
          stroke="#1f2937"
          strokeWidth="0.6"
        />
        {gridLines.map((g) => {
          const y = height - padding - g * (height - padding * 2);
          return (
            <line
              key={g}
              x1={padding}
              x2={width - padding}
              y1={y}
              y2={y}
              stroke="#0f172a"
              strokeWidth="0.6"
              strokeDasharray="2 2"
            />
          );
        })}
        {series.map((s) => {
          const coords = coordsFor(s.points);
          return (
            <path
              key={s.label}
              d={smoothPath(coords)}
              fill="none"
              stroke={s.color}
              strokeWidth="2.2"
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 6px ${s.color}55)` }}
            />
          );
        })}
        {series.map((s) =>
          (s.points || []).map((v, idx) => {
            const x = (idx / steps) * (width - padding * 2) + padding;
            const y = height - padding - (v / maxVal) * (height - padding * 2);
            return <circle key={`${s.label}-${idx}`} cx={x} cy={y} r="2.8" fill={s.color} />;
          })
        )}
        <rect
          x={padding}
          y={padding}
          width={width - padding * 2}
          height={height - padding * 2}
          rx="10"
          ry="10"
          fill="rgba(255,255,255,0.02)"
          stroke="rgba(255,255,255,0.06)"
        />
      </svg>
      <div className="chart-axis">
        <span>{startLabel}</span>
        <span>{endLabel}</span>
      </div>
    </div>
  );
}
