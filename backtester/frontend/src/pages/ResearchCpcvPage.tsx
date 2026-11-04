import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { apiFetch } from "../api/client";
import { CpcvRun, CpcvResults } from "../api/types";

const AXIS_LABEL = { color: "#7d8590", fontSize: 10 } as const;
const SPLIT_LINE = { lineStyle: { color: "rgba(48,54,61,0.5)" } } as const;

function fmt(v: number | null | undefined, d = 2): string {
  if (v === null || v === undefined) return "\u2014";
  return v.toFixed(d);
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "\u2014";
  return (v * 100).toFixed(2) + "%";
}

// ── PnL distribution across all C(N,k) paths ──────────────────────────
function PathPnlChart({ results }: { results: CpcvResults }) {
  const pnls = results.path_results.map((r) => r.final_pnl);
  if (pnls.length === 0) return null;

  const sorted = [...pnls].sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const range = max - min || 1;
  const bucketCount = Math.min(25, Math.max(8, Math.ceil(Math.sqrt(pnls.length))));
  const bucketSize = range / bucketCount;
  const buckets: { label: string; count: number; center: number }[] = [];

  for (let i = 0; i < bucketCount; i++) {
    const lo = min + i * bucketSize;
    const hi = lo + bucketSize;
    const count = pnls.filter((v) =>
      i === bucketCount - 1 ? v >= lo && v <= hi : v >= lo && v < hi
    ).length;
    buckets.push({ label: lo.toFixed(0), count, center: (lo + hi) / 2 });
  }

  return (
    <ReactECharts
      style={{ height: 240 }}
      option={{
        animation: false,
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        grid: { left: 44, right: 16, top: 12, bottom: 28 },
        xAxis: {
          type: "category",
          data: buckets.map((b) => b.label),
          axisLabel: { ...AXIS_LABEL, rotate: 45 },
        },
        yAxis: { type: "value", axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
        series: [
          {
            type: "bar",
            data: buckets.map((b) => ({
              value: b.count,
              itemStyle: {
                color: b.center >= 0 ? "rgba(63,185,80,0.7)" : "rgba(248,81,73,0.7)",
              },
            })),
            barWidth: "90%",
          },
        ],
      }}
    />
  );
}

// ── Per-fold heatmap: avg PnL contribution of each fold ────────────────
function FoldHeatmap({ results }: { results: CpcvResults }) {
  const { fold_avg_pnl, fold_std_pnl } = results.metrics;
  const foldKeys = Object.keys(fold_avg_pnl)
    .map(Number)
    .sort((a, b) => a - b);
  if (foldKeys.length === 0) return null;

  const vals = foldKeys.map((k) => fold_avg_pnl[String(k)] ?? 0);
  const maxAbs = Math.max(...vals.map(Math.abs), 1);

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {foldKeys.map((k) => {
        const avg = fold_avg_pnl[String(k)] ?? 0;
        const std = fold_std_pnl[String(k)] ?? 0;
        const intensity = Math.min(Math.abs(avg) / maxAbs, 1);
        const bg =
          avg >= 0
            ? `rgba(63,185,80,${0.15 + intensity * 0.55})`
            : `rgba(248,81,73,${0.15 + intensity * 0.55})`;
        return (
          <div
            key={k}
            style={{
              background: bg,
              borderRadius: 6,
              padding: "8px 12px",
              minWidth: 64,
              textAlign: "center",
              flex: "1 0 64px",
            }}
            title={`Fold ${k}: avg=${avg.toFixed(2)}, std=${std.toFixed(2)}`}
          >
            <div style={{ fontSize: 10, color: "var(--text-dim)" }}>Fold {k}</div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>
              {avg >= 0 ? "+" : ""}
              {avg.toFixed(1)}
            </div>
            <div style={{ fontSize: 9, color: "var(--text-dim)" }}>\u00b1{std.toFixed(1)}</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Combination scatter: PnL per combination index ─────────────────────
function CombinationScatter({ results }: { results: CpcvResults }) {
  const data = results.path_results.map((r, i) => [i, r.final_pnl]);
  if (data.length === 0) return null;

  return (
    <ReactECharts
      style={{ height: 200 }}
      option={{
        animation: false,
        backgroundColor: "transparent",
        tooltip: {
          trigger: "item",
          formatter: (p: { data: [number, number] }) =>
            `Path ${p.data[0]}: ${p.data[1].toFixed(2)}`,
        },
        grid: { left: 52, right: 16, top: 12, bottom: 28 },
        xAxis: {
          type: "value",
          name: "Path #",
          axisLabel: AXIS_LABEL,
          splitLine: SPLIT_LINE,
        },
        yAxis: {
          type: "value",
          name: "PnL",
          axisLabel: AXIS_LABEL,
          splitLine: SPLIT_LINE,
        },
        series: [
          {
            type: "scatter",
            data,
            symbolSize: 6,
            itemStyle: {
              color: (p: { data: [number, number] }) =>
                p.data[1] >= 0 ? "#3fb950" : "#f85149",
            },
          },
        ],
      }}
    />
  );
}

// ── Metrics table ──────────────────────────────────────────────────────
function MetricsTable({ metrics }: { metrics: CpcvResults["metrics"] }) {
  const rows: [string, string, string][] = [
    ["PBO (Prob. of Backtest Overfitting)", fmtPct(metrics.pbo), "Fraction of paths with negative PnL. >50% = strong overfitting signal."],
    ["PSR (Probabilistic Sharpe)", fmtPct(metrics.psr), "P(true Sharpe > 0) adjusted for skew/kurtosis."],
    ["DSR (Deflated Sharpe)", fmtPct(metrics.dsr), "PSR adjusted for multiple testing. Low = likely overfit."],
    ["Sharpe (raw)", fmt(metrics.sharpe_hat, 4), "Mean PnL / Std PnL across paths."],
    ["E[max SR] under null", fmt(metrics.e_max_sharpe, 4), "Expected best Sharpe from random trials."],
    ["Mean PnL", fmt(metrics.mean_pnl), ""],
    ["Median PnL", fmt(metrics.median_pnl), ""],
    ["Std PnL", fmt(metrics.std_pnl), ""],
    ["5th Percentile", fmt(metrics.percentile_5), ""],
    ["95th Percentile", fmt(metrics.percentile_95), ""],
    ["Skewness", fmt(metrics.skewness, 4), "Negative = left tail risk."],
    ["Excess Kurtosis", fmt(metrics.excess_kurtosis, 4), "Fat tails if > 0."],
  ];

  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <tbody>
        {rows.map(([label, value, hint]) => (
          <tr key={label} style={{ borderBottom: "1px solid rgba(48,54,61,0.3)" }}>
            <td style={{ padding: "6px 8px", color: "var(--text-dim)" }} title={hint}>
              {label}
            </td>
            <td
              style={{
                padding: "6px 8px",
                textAlign: "right",
                fontFamily: "var(--font-mono, monospace)",
                fontWeight: label.startsWith("PBO") || label.startsWith("DSR") ? 700 : 400,
              }}
            >
              {value}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Detail page for a single CPCV run ──────────────────────────────────
function CpcvRunDetail({ cpcvId }: { cpcvId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const runQuery = useQuery({
    queryKey: ["cpcv-run", cpcvId],
    queryFn: () => apiFetch<CpcvRun>(`/api/research/cpcv/${cpcvId}`),
    refetchInterval: (q) => (q.state.data?.status === "completed" ? false : 2000),
  });

  const resultsQuery = useQuery({
    queryKey: ["cpcv-results", cpcvId],
    queryFn: () => apiFetch<CpcvResults>(`/api/research/cpcv/${cpcvId}/results`),
    enabled: !!runQuery.data && runQuery.data.completed_combinations > 0,
    refetchInterval: (q) =>
      runQuery.data?.status === "completed" ? false : 3000,
  });

  const deleteCpcv = useMutation({
    mutationFn: () => apiFetch(`/api/research/cpcv/${cpcvId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cpcv-runs"] });
      navigate("/cpcv");
    },
  });

  const run = runQuery.data;
  const results = resultsQuery.data;

  if (runQuery.isLoading) return <p className="muted-text">Loading...</p>;
  if (!run) return <p className="muted-text">CPCV run not found.</p>;

  return (
    <div className="stack gap-16">
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <span className={`pill pill-${run.status}`} style={{ marginRight: 8 }}>
            {run.status}
          </span>
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
            N={run.n_groups} k={run.k_test_groups} | {run.completed_combinations}/
            {run.total_combinations} paths
            {run.purge_groups > 0 && ` | purge=${run.purge_groups}`}
            {run.embargo_pct > 0 && ` | embargo=${(run.embargo_pct * 100).toFixed(0)}%`}
          </span>
        </div>
        <button
          className="btn btn-ghost"
          style={{ fontSize: 11, color: "var(--red)", padding: "4px 8px" }}
          onClick={() => deleteCpcv.mutate()}
          disabled={deleteCpcv.isPending}
        >
          {deleteCpcv.isPending ? "Deleting..." : "Delete"}
        </button>
      </div>

      {results && results.metrics.n_paths > 0 && (
        <>
          {/* Row 1: Metrics + Fold heatmap */}
          <div className="split-layout" style={{ alignItems: "start" }}>
            <div className="panel">
              <div className="panel-header">
                <div className="panel-header-left">
                  <p className="panel-eyebrow">Overfitting Analysis</p>
                  <p className="panel-title">Statistical Metrics</p>
                </div>
              </div>
              <div className="panel-body">
                <MetricsTable metrics={results.metrics} />
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div className="panel-header-left">
                  <p className="panel-eyebrow">Fold Analysis</p>
                  <p className="panel-title">Average PnL per Fold</p>
                </div>
              </div>
              <div className="panel-body">
                <FoldHeatmap results={results} />
                <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-dim)" }}>
                  Each fold's average contribution across all paths that include it.
                  Green = profitable, red = losing. Intensity proportional to magnitude.
                </div>
              </div>
            </div>
          </div>

          {/* Row 2: Distribution + Scatter */}
          <div className="split-layout" style={{ alignItems: "start" }}>
            <div className="panel">
              <div className="panel-header">
                <div className="panel-header-left">
                  <p className="panel-eyebrow">Distribution</p>
                  <p className="panel-title">OOS PnL Histogram</p>
                </div>
              </div>
              <div className="panel-body">
                <PathPnlChart results={results} />
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div className="panel-header-left">
                  <p className="panel-eyebrow">Paths</p>
                  <p className="panel-title">Per-Combination PnL</p>
                </div>
              </div>
              <div className="panel-body">
                <CombinationScatter results={results} />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Combinations table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Combinations</p>
            <p className="panel-title">All C(N,k) Paths</p>
          </div>
        </div>
        <div className="panel-body" style={{ maxHeight: 300, overflowY: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(48,54,61,0.5)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>
                  Test Folds
                </th>
                <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>
                  Status
                </th>
                <th style={{ textAlign: "right", padding: "4px 8px", color: "var(--text-dim)", fontWeight: 500 }}>
                  PnL
                </th>
              </tr>
            </thead>
            <tbody>
              {run.children.map((child) => (
                <tr
                  key={child.run_id}
                  style={{ borderBottom: "1px solid rgba(48,54,61,0.2)", cursor: "pointer" }}
                  onClick={() => navigate(`/results/${child.run_id}`)}
                >
                  <td style={{ padding: "4px 8px", fontFamily: "var(--font-mono, monospace)" }}>
                    [{child.combination.join(", ")}]
                  </td>
                  <td style={{ padding: "4px 8px" }}>
                    <span className={`pill pill-${child.status}`} style={{ fontSize: 10 }}>
                      {child.status}
                    </span>
                  </td>
                  <td
                    style={{
                      padding: "4px 8px",
                      textAlign: "right",
                      fontFamily: "var(--font-mono, monospace)",
                    }}
                  >
                    {child.final_pnl !== null ? (
                      <span className={child.final_pnl >= 0 ? "pnl-positive" : "pnl-negative"}>
                        {child.final_pnl >= 0 ? "+" : ""}
                        {child.final_pnl.toFixed(2)}
                      </span>
                    ) : (
                      "\u2014"
                    )}
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

// ── List page ──────────────────────────────────────────────────────────
function CpcvRunList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const cpcvQuery = useQuery({
    queryKey: ["cpcv-runs"],
    queryFn: () => apiFetch<CpcvRun[]>("/api/research/cpcv"),
    refetchInterval: 3000,
  });

  const deleteAll = useMutation({
    mutationFn: async () => {
      for (const r of cpcvQuery.data ?? []) {
        await apiFetch(`/api/research/cpcv/${r.cpcv_id}`, { method: "DELETE" });
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cpcv-runs"] }),
  });

  const runs = cpcvQuery.data ?? [];

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-header-left">
          <p className="panel-eyebrow">CPCV</p>
          <p className="panel-title">All Runs</p>
        </div>
        {runs.length > 0 && (
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11, color: "var(--red)", padding: "4px 8px" }}
            onClick={() => deleteAll.mutate()}
            disabled={deleteAll.isPending}
          >
            {deleteAll.isPending ? "Clearing..." : "Clear all"}
          </button>
        )}
      </div>
      <div className="panel-body">
        {cpcvQuery.isLoading && <p className="muted-text">Loading...</p>}
        {runs.length === 0 && !cpcvQuery.isLoading && (
          <div className="empty-state">
            <span className="empty-state-icon">&#x1F4CA;</span>
            <span>No CPCV runs yet. Launch one from the Backtest page.</span>
          </div>
        )}
        {runs.length > 0 && (
          <div className="run-list">
            {runs.map((r) => (
              <div
                key={r.cpcv_id}
                className="run-row"
                onClick={() => navigate(`/cpcv/${r.cpcv_id}`)}
              >
                <div className="run-row-left">
                  <span className="run-row-id">{r.cpcv_id}</span>
                  <span className="run-row-path">
                    N={r.n_groups} k={r.k_test_groups} |{" "}
                    {r.completed_combinations}/{r.total_combinations} done
                  </span>
                </div>
                <span className={`pill pill-${r.status}`}>{r.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page shell ─────────────────────────────────────────────────────────
export function ResearchCpcvPage() {
  const { cpcvId } = useParams<{ cpcvId: string }>();

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Research Lab</p>
          <h1 className="page-title">
            {cpcvId ? `CPCV \u2014 ${cpcvId}` : "Combinatorial Purged Cross-Validation"}
          </h1>
          <p className="page-desc">
            {cpcvId
              ? "Out-of-sample robustness analysis, PBO, and deflated Sharpe ratio."
              : "Test strategy robustness across all combinatorial data splits."}
          </p>
        </div>
      </div>

      {cpcvId ? <CpcvRunDetail cpcvId={cpcvId} /> : <CpcvRunList />}
    </div>
  );
}
