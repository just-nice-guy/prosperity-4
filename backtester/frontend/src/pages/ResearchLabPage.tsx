import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { apiFetch } from "../api/client";
import { MonteCarloRun, MonteCarloResults } from "../api/types";

const AXIS_LABEL = { color: "#7d8590", fontSize: 10 } as const;
const SPLIT_LINE = { lineStyle: { color: "rgba(48,54,61,0.5)" } } as const;

const PATH_COLORS = [
  "#58a6ff", "#3fb950", "#f0883e", "#bc8cff", "#f778ba",
  "#79c0ff", "#56d364", "#d29922", "#d2a8ff", "#ff7b72",
];

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(decimals);
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(2) + "%";
}

function PnlPathsChart({ results }: { results: MonteCarloResults }) {
  const paths = results.pnl_paths;
  const runIds = Object.keys(paths);

  const series = runIds.map((runId, i) => ({
    type: "line" as const,
    name: runId,
    data: paths[runId],
    showSymbol: false,
    lineStyle: { width: 1.2, color: PATH_COLORS[i % PATH_COLORS.length], opacity: 0.5 },
    emphasis: { lineStyle: { width: 2.5, opacity: 1 } },
  }));

  // Compute mean path
  if (runIds.length > 1) {
    const allTimestamps = new Set<number>();
    for (const p of Object.values(paths)) {
      for (const [ts] of p) allTimestamps.add(ts);
    }
    const sortedTs = [...allTimestamps].sort((a, b) => a - b);
    const meanPath: [number, number][] = sortedTs.map((ts) => {
      let sum = 0;
      let count = 0;
      for (const p of Object.values(paths)) {
        const point = p.find(([t]) => t === ts);
        if (point) { sum += point[1]; count++; }
      }
      return [ts, count > 0 ? Math.round((sum / count) * 100) / 100 : 0];
    });

    series.push({
      type: "line",
      name: "Mean",
      data: meanPath,
      showSymbol: false,
      lineStyle: { width: 3, color: "#e6edf3", opacity: 1 },
      emphasis: { lineStyle: { width: 4, opacity: 1 } },
    });
  }

  return (
    <ReactECharts
      style={{ height: 400 }}
      option={{
        animation: false,
        backgroundColor: "transparent",
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "cross" },
          confine: true,
        },
        legend: { show: false },
        grid: { left: 56, right: 24, top: 16, bottom: 40 },
        xAxis: {
          type: "value",
          name: "Timestamp",
          axisLabel: AXIS_LABEL,
          splitLine: SPLIT_LINE,
        },
        yAxis: {
          type: "value",
          name: "PnL",
          axisLabel: AXIS_LABEL,
          splitLine: SPLIT_LINE,
        },
        dataZoom: [
          { type: "inside", filterMode: "weakFilter" },
          { type: "slider", height: 18, bottom: 4, fillerColor: "rgba(88,166,255,0.15)", borderColor: "transparent" },
        ],
        series,
      }}
    />
  );
}

function DistributionChart({ distribution }: { distribution: number[] }) {
  if (distribution.length === 0) return null;

  // Build histogram buckets
  const sorted = [...distribution].sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const range = max - min || 1;
  const bucketCount = Math.min(30, Math.max(10, Math.ceil(Math.sqrt(distribution.length))));
  const bucketSize = range / bucketCount;
  const buckets: { label: string; count: number; center: number }[] = [];

  for (let i = 0; i < bucketCount; i++) {
    const lo = min + i * bucketSize;
    const hi = lo + bucketSize;
    const count = distribution.filter((v) => (i === bucketCount - 1 ? v >= lo && v <= hi : v >= lo && v < hi)).length;
    buckets.push({ label: lo.toFixed(0), count, center: (lo + hi) / 2 });
  }

  const colors = buckets.map((b) =>
    b.center >= 0 ? "rgba(63, 185, 80, 0.7)" : "rgba(248, 81, 73, 0.7)"
  );

  return (
    <ReactECharts
      style={{ height: 260 }}
      option={{
        animation: false,
        backgroundColor: "transparent",
        tooltip: {
          trigger: "axis",
          formatter: (params: Array<{ name: string; value: number }>) => {
            const p = params[0];
            return `PnL ~ ${p.name}<br/>Count: ${p.value}`;
          },
        },
        grid: { left: 44, right: 16, top: 12, bottom: 28 },
        xAxis: {
          type: "category",
          data: buckets.map((b) => b.label),
          axisLabel: { ...AXIS_LABEL, rotate: 45 },
        },
        yAxis: {
          type: "value",
          axisLabel: AXIS_LABEL,
          splitLine: SPLIT_LINE,
        },
        series: [
          {
            type: "bar",
            data: buckets.map((b, i) => ({
              value: b.count,
              itemStyle: { color: colors[i] },
            })),
            barWidth: "90%",
          },
        ],
      }}
    />
  );
}

function RiskMetricsTable({ metrics }: { metrics: MonteCarloResults["risk_metrics"] }) {
  const rows: [string, string][] = [
    ["Mean PnL", fmt(metrics.mean_pnl)],
    ["Median PnL", fmt(metrics.median_pnl)],
    ["Std Dev", fmt(metrics.std_dev)],
    ["5th Percentile", fmt(metrics.percentile_5)],
    ["25th Percentile", fmt(metrics.percentile_25)],
    ["75th Percentile", fmt(metrics.percentile_75)],
    ["95th Percentile", fmt(metrics.percentile_95)],
    ["Probability of Loss", fmtPct(metrics.probability_of_loss)],
    ["VaR 95%", fmt(metrics.var_95)],
    ["CVaR 95%", fmt(metrics.cvar_95)],
    ["Sharpe Estimate", fmt(metrics.sharpe_estimate, 4)],
    ["Max Drawdown (mean)", fmt(metrics.max_drawdown_mean)],
    ["Max Drawdown (worst)", fmt(metrics.max_drawdown_worst)],
  ];

  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label} style={{ borderBottom: "1px solid rgba(48,54,61,0.3)" }}>
            <td style={{ padding: "6px 8px", color: "var(--text-dim)" }}>{label}</td>
            <td style={{ padding: "6px 8px", textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>
              {value}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function McRunDetail({ mcId }: { mcId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const runQuery = useQuery({
    queryKey: ["mc-run", mcId],
    queryFn: () => apiFetch<MonteCarloRun>(`/api/research/monte-carlo/${mcId}`),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && data.status === "completed" ? false : 2000;
    },
  });

  const resultsQuery = useQuery({
    queryKey: ["mc-results", mcId],
    queryFn: () => apiFetch<MonteCarloResults>(`/api/research/monte-carlo/${mcId}/results`),
    enabled: !!runQuery.data && runQuery.data.completed_paths > 0,
    refetchInterval: (query) => {
      const parent = runQuery.data;
      return parent && parent.status === "completed" ? false : 3000;
    },
  });

  const deleteMc = useMutation({
    mutationFn: () => apiFetch(`/api/research/monte-carlo/${mcId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mc-runs"] });
      navigate("/research");
    },
  });

  const mc = runQuery.data;
  const results = resultsQuery.data;

  if (runQuery.isLoading) return <p className="muted-text">Loading…</p>;
  if (!mc) return <p className="muted-text">MC run not found.</p>;

  return (
    <div className="stack gap-16">
      {/* Header info */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <span className={`pill pill-${mc.status}`} style={{ marginRight: 8 }}>{mc.status}</span>
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {mc.completed_paths}/{mc.num_paths} paths completed
            {mc.failed_paths > 0 && ` · ${mc.failed_paths} failed`}
          </span>
        </div>
        <button
          className="btn btn-ghost"
          style={{ fontSize: 11, color: "var(--red)", padding: "4px 8px" }}
          onClick={() => deleteMc.mutate()}
          disabled={deleteMc.isPending}
        >
          {deleteMc.isPending ? "Deleting…" : "Delete"}
        </button>
      </div>

      {/* PnL Paths */}
      {results && Object.keys(results.pnl_paths).length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Simulation</p>
              <p className="panel-title">PnL Paths</p>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {Object.keys(results.pnl_paths).length} paths · white = mean
            </span>
          </div>
          <div className="panel-body">
            <PnlPathsChart results={results} />
          </div>
        </div>
      )}

      {/* Distribution + Risk Metrics side by side */}
      {results && results.final_pnl_distribution.length > 0 && (
        <div className="split-layout" style={{ alignItems: "start" }}>
          <div className="panel">
            <div className="panel-header">
              <div className="panel-header-left">
                <p className="panel-eyebrow">Distribution</p>
                <p className="panel-title">Final PnL Histogram</p>
              </div>
            </div>
            <div className="panel-body">
              <DistributionChart distribution={results.final_pnl_distribution} />
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <div className="panel-header-left">
                <p className="panel-eyebrow">Analytics</p>
                <p className="panel-title">Risk Metrics</p>
              </div>
            </div>
            <div className="panel-body">
              <RiskMetricsTable metrics={results.risk_metrics} />
            </div>
          </div>
        </div>
      )}

      {/* Child runs table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Paths</p>
            <p className="panel-title">Child Runs</p>
          </div>
        </div>
        <div className="panel-body" style={{ maxHeight: 300, overflowY: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(48,54,61,0.5)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>Run ID</th>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>Status</th>
                <th style={{ textAlign: "right", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>Final PnL</th>
              </tr>
            </thead>
            <tbody>
              {mc.children.map((child) => (
                <tr
                  key={child.run_id}
                  style={{ borderBottom: "1px solid rgba(48,54,61,0.2)", cursor: "pointer" }}
                  onClick={() => navigate(`/results/${child.run_id}`)}
                >
                  <td style={{ padding: "4px 8px", fontFamily: "var(--font-mono, monospace)" }}>{child.run_id}</td>
                  <td style={{ padding: "4px 8px" }}>
                    <span className={`pill pill-${child.status}`} style={{ fontSize: 10 }}>{child.status}</span>
                  </td>
                  <td style={{ padding: "4px 8px", textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>
                    {child.final_pnl !== null ? (
                      <span className={child.final_pnl >= 0 ? "pnl-positive" : "pnl-negative"}>
                        {child.final_pnl >= 0 ? "+" : ""}{child.final_pnl.toFixed(2)}
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function McRunList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mcRunsQuery = useQuery({
    queryKey: ["mc-runs"],
    queryFn: () => apiFetch<MonteCarloRun[]>("/api/research/monte-carlo"),
    refetchInterval: 3000,
  });

  const deleteAll = useMutation({
    mutationFn: async () => {
      const runs = mcRunsQuery.data ?? [];
      for (const mc of runs) {
        await apiFetch(`/api/research/monte-carlo/${mc.mc_id}`, { method: "DELETE" });
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mc-runs"] }),
  });

  const mcRuns = mcRunsQuery.data ?? [];

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-header-left">
          <p className="panel-eyebrow">Monte Carlo</p>
          <p className="panel-title">All Simulations</p>
        </div>
        {mcRuns.length > 0 && (
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11, color: "var(--red)", padding: "4px 8px" }}
            onClick={() => deleteAll.mutate()}
            disabled={deleteAll.isPending}
          >
            {deleteAll.isPending ? "Clearing…" : "Clear all"}
          </button>
        )}
      </div>
      <div className="panel-body">
        {mcRunsQuery.isLoading && <p className="muted-text">Loading…</p>}
        {mcRuns.length === 0 && !mcRunsQuery.isLoading && (
          <div className="empty-state">
            <span className="empty-state-icon">🔬</span>
            <span>No simulations yet. Launch a Monte Carlo run from the Backtest page.</span>
          </div>
        )}
        {mcRuns.length > 0 && (
          <div className="run-list">
            {mcRuns.map((mc) => (
              <div
                key={mc.mc_id}
                className="run-row"
                onClick={() => navigate(`/research/${mc.mc_id}`)}
              >
                <div className="run-row-left">
                  <span className="run-row-id">{mc.mc_id}</span>
                  <span className="run-row-path">
                    {mc.num_paths} paths · {mc.completed_paths}/{mc.num_paths} done
                    {mc.failed_paths > 0 && ` · ${mc.failed_paths} failed`}
                    {mc.trader_path && ` · ${mc.trader_path.split(/[\\/]/).pop()}`}
                  </span>
                </div>
                <div className="run-row-right" style={{ alignItems: "center", flexDirection: "row", gap: 8 }}>
                  <span className={`pill pill-${mc.status}`}>{mc.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ResearchLabPage() {
  const { mcId } = useParams<{ mcId: string }>();

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Research Lab</p>
          <h1 className="page-title">
            {mcId ? `Monte Carlo — ${mcId}` : "Monte Carlo Simulations"}
          </h1>
          <p className="page-desc">
            {mcId
              ? "PnL path analysis, distribution and risk metrics."
              : "Browse and analyze Monte Carlo simulation results."}
          </p>
        </div>
      </div>

      {mcId ? <McRunDetail mcId={mcId} /> : <McRunList />}
    </div>
  );
}
