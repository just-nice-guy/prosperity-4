import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import {
  DiscoveredParam,
  OptimizationRun,
  OptimizationResults,
  OptCombinationResult,
  DatasetInfo,
} from "../api/types";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

type ParamPreset = {
  name: string;
  default_value: number;
  type: string;
  enabled: boolean;
  min: number;
  max: number;
  step: number;
};

function fmt(v: number | null | undefined, d = 2): string {
  if (v === null || v === undefined) return "\u2014";
  return v.toFixed(d);
}
function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "\u2014";
  return (v * 100).toFixed(1) + "%";
}

// ── PDF report generation ───────────────────────────────────────────────
function generatePdfReport(run: OptimizationRun, results: OptimizationResults) {
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const margin = 14;
  let y = 14;

  const teal: [number, number, number] = [20, 184, 166];
  const dark: [number, number, number] = [17, 24, 39];
  const muted: [number, number, number] = [107, 114, 128];
  const green: [number, number, number] = [16, 185, 129];
  const red: [number, number, number] = [239, 68, 68];

  // ── Header ──────────────────────────────────────────────────────────
  doc.setFillColor(...dark);
  doc.rect(0, 0, W, 28, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(255, 255, 255);
  doc.text("OPTIMIZATION REPORT", margin, 12);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(180, 190, 200);
  doc.text(`${run.opt_id}  |  ${run.search_method} search  |  objective: ${run.objective}  |  ${new Date().toLocaleDateString("en-GB")}`, margin, 19);

  const traderName = run.trader_path.split(/[/\\]/).pop() ?? run.trader_path;
  doc.text(`Strategy: ${traderName}  |  Matching: ${run.matching_mode}`, margin, 24);

  y = 36;

  // ── Config summary table ────────────────────────────────────────────
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...dark);
  doc.text("Configuration", margin, y);
  y += 3;

  const isFr = run.is_fraction ?? 0.7;
  const configData = [
    ["IS / OOS Split", `${(isFr * 100).toFixed(0)}% / ${(100 - isFr * 100).toFixed(0)}%`],
    ["IS Ticks", run.is_ticks?.toLocaleString() ?? "\u2014"],
    ["OOS Ticks", run.oos_ticks?.toLocaleString() ?? "\u2014"],
    ["CPCV", `N=${run.cpcv_n}  k=${run.cpcv_k}`],
    ["Matching Mode", run.matching_mode],
    ["Combinations", String(run.total_combinations)],
    ["CPCV Paths/Combo", String(run.cpcv_paths_per_combo)],
    ["Total Runs", String(run.total_runs)],
    ["Completed", String(run.completed_runs)],
  ];

  autoTable(doc, {
    startY: y,
    margin: { left: margin, right: W / 2 + 10 },
    head: [["Parameter", "Value"]],
    body: configData,
    theme: "grid",
    styles: { fontSize: 8, cellPadding: 2.5, textColor: dark, lineColor: [220, 220, 220], lineWidth: 0.2 },
    headStyles: { fillColor: teal, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 8 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
  });

  // ── Key metrics (right column, same Y) ──────────────────────────────
  const best = results.combination_results.find((c) => c.rank === 1);
  const metricsX = W / 2 + 10;

  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...dark);
  doc.text("Key Metrics", metricsX, 39);

  const metricsData: string[][] = [
    ["Deflated Sharpe", fmt(results.deflated_sharpe, 4)],
    ["Trials Tested", String(results.n_trials)],
  ];
  if (best) {
    metricsData.push(
      ["Best IS Mean PnL", fmt(best.is_mean_pnl)],
      ["Best IS Std PnL", fmt(best.is_std_pnl)],
      ["Best IS Sharpe", fmt(best.is_sharpe, 3)],
      ["Best IS PBO", fmtPct(best.is_pbo)],
      ["Best OOS PnL", fmt(best.oos_pnl)],
      ["IS/OOS Ratio", fmt(best.is_oos_ratio, 3)],
      ["Best IS Fills", String(best.is_total_fills)],
    );
  }

  autoTable(doc, {
    startY: 42,
    margin: { left: metricsX, right: margin },
    head: [["Metric", "Value"]],
    body: metricsData,
    theme: "grid",
    styles: { fontSize: 8, cellPadding: 2.5, textColor: dark, lineColor: [220, 220, 220], lineWidth: 0.2 },
    headStyles: { fillColor: teal, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 8 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didParseCell: (data) => {
      // Color PnL values
      if (data.section === "body" && data.column.index === 1) {
        const label = String(configData[data.row.index]?.[0] ?? metricsData[data.row.index]?.[0] ?? "");
        const val = parseFloat(String(data.cell.raw));
        if (!isNaN(val) && (label.includes("PnL") || label.includes("Sharpe"))) {
          data.cell.styles.textColor = val >= 0 ? green : red;
          data.cell.styles.fontStyle = "bold";
        }
      }
    },
  });

  // ── Best parameters highlight ───────────────────────────────────────
  if (best) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const tableEndY = Math.max((doc as any).lastAutoTable?.finalY ?? 90, 90);
    y = tableEndY + 8;

    doc.setFillColor(240, 253, 250);
    doc.setDrawColor(...teal);
    doc.roundedRect(margin, y, W - margin * 2, 18, 2, 2, "FD");

    doc.setFontSize(8);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...teal);
    doc.text("BEST PARAMETERS", margin + 5, y + 6);

    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...dark);
    const paramStr = Object.entries(best.overrides)
      .map(([k, v]) => `${k} = ${typeof v === "number" && !Number.isInteger(v) ? v.toFixed(4) : v}`)
      .join("    ");
    doc.text(paramStr, margin + 5, y + 13);

    y += 24;
  } else {
    y = 100;
  }

  // ── Full ranking table ──────────────────────────────────────────────
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...dark);
  doc.text("Full Ranking", margin, y);
  y += 3;

  const paramNames = results.combination_results.length > 0
    ? Object.keys(results.combination_results[0].overrides)
    : [];

  const rankHead = ["#", ...paramNames, "IS Mean", "IS Std", "IS Sharpe", "IS PBO", "OOS PnL", "IS/OOS", "Fills"];

  const rankBody = results.combination_results.map((cr) => [
    String(cr.rank),
    ...paramNames.map((k) => {
      const v = cr.overrides[k];
      return typeof v === "number" && !Number.isInteger(v) ? v.toFixed(3) : String(v ?? "");
    }),
    fmt(cr.is_mean_pnl),
    fmt(cr.is_std_pnl),
    fmt(cr.is_sharpe, 3),
    fmtPct(cr.is_pbo),
    fmt(cr.oos_pnl),
    fmt(cr.is_oos_ratio, 3),
    String(cr.is_total_fills),
  ]);

  autoTable(doc, {
    startY: y,
    margin: { left: margin, right: margin },
    head: [rankHead],
    body: rankBody,
    theme: "grid",
    styles: { fontSize: 7, cellPadding: 2, textColor: dark, lineColor: [220, 220, 220], lineWidth: 0.2, halign: "center" },
    headStyles: { fillColor: dark, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 7 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didParseCell: (data) => {
      if (data.section === "body") {
        // Highlight rank 1 row
        if (data.row.index === 0) {
          data.cell.styles.fillColor = [240, 253, 250];
        }
        // Color IS Mean PnL column
        const colIdx = paramNames.length + 1;
        if (data.column.index === colIdx) {
          const val = parseFloat(String(data.cell.raw).replace("\u2014", ""));
          if (!isNaN(val)) {
            data.cell.styles.textColor = val >= 0 ? green : red;
            data.cell.styles.fontStyle = "bold";
          }
        }
        // Color OOS PnL column
        const oosIdx = paramNames.length + 5;
        if (data.column.index === oosIdx) {
          const val = parseFloat(String(data.cell.raw).replace("\u2014", ""));
          if (!isNaN(val)) {
            data.cell.styles.textColor = val >= 0 ? green : red;
            data.cell.styles.fontStyle = "bold";
          }
        }
      }
    },
  });

  // ── Footer ──────────────────────────────────────────────────────────
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    const H = doc.internal.pageSize.getHeight();
    doc.setFillColor(248, 250, 252);
    doc.rect(0, H - 10, W, 10, "F");
    doc.setFontSize(7);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...muted);
    doc.text("Prosperity 4 Backtester Lab  \u2022  CPCV Parameter Optimization Report", margin, H - 4);
    doc.text(`Page ${i} / ${pageCount}`, W - margin, H - 4, { align: "right" });
  }

  doc.save(`opt-report-${run.opt_id}.pdf`);
}

// ── Column definitions for sortable/filterable table ───────────────────
type ColDef = {
  key: string;
  label: string;
  get: (cr: OptCombinationResult) => number | null;
  fmt: (v: number | null) => string;
  colorize?: boolean;
  pctCol?: boolean;
};

const METRIC_COLS: ColDef[] = [
  { key: "is_mean_pnl", label: "IS Mean", get: (c) => c.is_mean_pnl, fmt: (v) => fmt(v), colorize: true },
  { key: "is_median_pnl", label: "IS Median", get: (c) => c.is_median_pnl, fmt: (v) => fmt(v), colorize: true },
  { key: "is_std_pnl", label: "IS Std", get: (c) => c.is_std_pnl, fmt: (v) => fmt(v) },
  { key: "is_min_pnl", label: "IS Min", get: (c) => c.is_min_pnl, fmt: (v) => fmt(v), colorize: true },
  { key: "is_max_pnl", label: "IS Max", get: (c) => c.is_max_pnl, fmt: (v) => fmt(v), colorize: true },
  { key: "is_sharpe", label: "IS Sharpe", get: (c) => c.is_sharpe, fmt: (v) => fmt(v, 3) },
  { key: "is_dsharpe", label: "IS DSharpe", get: (c) => c.is_dsharpe, fmt: (v) => fmt(v, 4) },
  { key: "is_pbo", label: "IS PBO", get: (c) => c.is_pbo, fmt: (v) => fmtPct(v), pctCol: true },
  { key: "is_win_rate", label: "IS Win%", get: (c) => c.is_win_rate, fmt: (v) => fmtPct(v), pctCol: true },
  { key: "oos_pnl", label: "OOS PnL", get: (c) => c.oos_pnl, fmt: (v) => fmt(v), colorize: true },
  { key: "is_oos_ratio", label: "IS/OOS", get: (c) => c.is_oos_ratio, fmt: (v) => fmt(v, 3) },
  { key: "is_total_fills", label: "Fills", get: (c) => c.is_total_fills, fmt: (v) => v !== null ? String(v) : "\u2014" },
];

type SortDir = "asc" | "desc" | null;
type SortState = { key: string; dir: SortDir };
type FilterRange = { min: string; max: string };

// ── Results detail view ─────────────────────────────────────────────────
function OptResultsView({ optId }: { optId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const runQ = useQuery({
    queryKey: ["opt-run", optId],
    queryFn: () => apiFetch<OptimizationRun>(`/api/research/optimization/${optId}`),
    refetchInterval: 3000,
  });
  const resultsQ = useQuery({
    queryKey: ["opt-results", optId],
    queryFn: () => apiFetch<OptimizationResults>(`/api/research/optimization/${optId}/results`),
    refetchInterval: (runQ.data?.status === "completed") ? false : 4000,
  });
  const deleteMut = useMutation({
    mutationFn: () => apiFetch(`/api/research/optimization/${optId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opt-runs"] });
      navigate("/optimization");
    },
  });

  // Sort & filter state
  const [sort, setSort] = useState<SortState>({ key: "rank", dir: "asc" });
  const [filters, setFilters] = useState<Record<string, FilterRange>>({});
  const [showFilters, setShowFilters] = useState(false);
  const [savingIdx, setSavingIdx] = useState<number | null>(null);

  const cycleSort = (key: string) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: "desc" };
      if (prev.dir === "desc") return { key, dir: "asc" };
      if (prev.dir === "asc") return { key: "rank", dir: "asc" };
      return { key, dir: "desc" };
    });
  };

  const sortIcon = (key: string) => {
    if (sort.key !== key) return " \u2195";
    return sort.dir === "desc" ? " \u2193" : " \u2191";
  };

  const setFilter = (key: string, field: "min" | "max", value: string) => {
    setFilters((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value, ...(prev[key] ? {} : { min: "", max: "" }) },
    }));
  };

  const saveTrader = async (cr: OptCombinationResult) => {
    setSavingIdx(cr.combo_idx);
    try {
      const resp = await apiFetch<string>(`/api/research/optimization/${optId}/export-trader`, {
        method: "POST",
        body: JSON.stringify({ overrides: cr.overrides }),
        rawText: true,
      });
      const blob = new Blob([resp], { type: "text/x-python" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const paramStr = Object.entries(cr.overrides).map(([k, v]) =>
        `${k}${typeof v === "number" && !Number.isInteger(v) ? v.toFixed(2) : v}`
      ).join("_").slice(0, 40);
      a.download = `trader_${paramStr}.py`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Failed to export trader:", e);
    } finally {
      setSavingIdx(null);
    }
  };

  const run = runQ.data;
  const results = resultsQ.data;

  if (!run) return <p className="muted-text">Loading...</p>;

  const pct = run.total_runs > 0 ? Math.round((run.completed_runs / run.total_runs) * 100) : 0;

  // Apply sort + filter
  let rows = results?.combination_results ?? [];
  if (rows.length > 0) {
    // Filter
    rows = rows.filter((cr) => {
      for (const col of METRIC_COLS) {
        const f = filters[col.key];
        if (!f) continue;
        const v = col.get(cr);
        if (v === null) continue;
        const realV = col.pctCol ? v * 100 : v;
        if (f.min !== "" && f.min !== undefined && realV < parseFloat(f.min)) return false;
        if (f.max !== "" && f.max !== undefined && realV > parseFloat(f.max)) return false;
      }
      return true;
    });
    // Sort
    if (sort.key === "rank") {
      rows = [...rows].sort((a, b) => sort.dir === "asc" ? a.rank - b.rank : b.rank - a.rank);
    } else {
      const col = METRIC_COLS.find((c) => c.key === sort.key);
      if (col) {
        rows = [...rows].sort((a, b) => {
          const va = col.get(a) ?? -Infinity;
          const vb = col.get(b) ?? -Infinity;
          return sort.dir === "desc" ? vb - va : va - vb;
        });
      }
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Optimization</p>
          <h1 className="page-title">{optId}</h1>
          <p className="page-desc">
            {run.search_method} search &middot; {run.total_combinations} combos &times;{" "}
            {run.cpcv_paths_per_combo} CPCV paths + OOS &middot; objective: {run.objective}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`pill pill-${run.status}`}>{run.status}</span>
          {results && results.combination_results.length > 0 && (
            <button
              className="btn btn-secondary"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 12 }}
              onClick={() => generatePdfReport(run, results)}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 14h8" /><path d="M8 10V2" /><path d="M5 7l3 3 3-3" />
              </svg>
              Export PDF
            </button>
          )}
          <button className="btn btn-ghost" style={{ color: "var(--red)" }} onClick={() => deleteMut.mutate()}>
            Delete
          </button>
        </div>
      </div>

      {/* Progress */}
      {run.status === "running" && (
        <div className="panel">
          <div className="panel-body">
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
              <span>{run.completed_runs} / {run.total_runs} runs</span>
              <span>{pct}%</span>
            </div>
            <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${pct}%`, height: "100%", background: "var(--teal)", borderRadius: 3, transition: "width 0.3s" }} />
            </div>
          </div>
        </div>
      )}

      {/* Config summary */}
      <div className="panel">
        <div className="panel-header"><p className="panel-title">Configuration</p></div>
        <div className="panel-body">
          <div className="stats-grid">
            <div className="stat-card"><span className="stat-label">IS / OOS</span><span className="stat-value">{((run.is_fraction ?? 0.7) * 100).toFixed(0)}% / {(100 - (run.is_fraction ?? 0.7) * 100).toFixed(0)}%</span></div>
            <div className="stat-card"><span className="stat-label">IS ticks</span><span className="stat-value">{run.is_ticks?.toLocaleString()}</span></div>
            <div className="stat-card"><span className="stat-label">OOS ticks</span><span className="stat-value">{run.oos_ticks?.toLocaleString()}</span></div>
            <div className="stat-card"><span className="stat-label">CPCV</span><span className="stat-value">N={run.cpcv_n} k={run.cpcv_k}</span></div>
            <div className="stat-card"><span className="stat-label">Matching</span><span className="stat-value">{run.matching_mode}</span></div>
            <div className="stat-card"><span className="stat-label">Combinations</span><span className="stat-value">{run.total_combinations}</span></div>
            <div className="stat-card"><span className="stat-label">Total runs</span><span className="stat-value">{run.total_runs}</span></div>
          </div>
        </div>
      </div>

      {/* Deflated Sharpe & best result */}
      {results && results.combination_results.length > 0 && (
        <div className="panel">
          <div className="panel-header"><p className="panel-title">Summary</p></div>
          <div className="panel-body">
            <div className="stats-grid">
              <div className="stat-card"><span className="stat-label">Deflated Sharpe</span><span className="stat-value">{fmt(results.deflated_sharpe, 4)}</span></div>
              <div className="stat-card"><span className="stat-label">Trials tested</span><span className="stat-value">{results.n_trials}</span></div>
              {(() => {
                const best = results.combination_results.find((c) => c.rank === 1);
                if (!best) return null;
                return (
                  <>
                    <div className="stat-card stat-card-positive"><span className="stat-label">Best IS Mean PnL</span><span className="stat-value">{fmt(best.is_mean_pnl)}</span></div>
                    <div className="stat-card"><span className="stat-label">Best IS Sharpe</span><span className="stat-value">{fmt(best.is_sharpe, 3)}</span></div>
                    <div className="stat-card"><span className="stat-label">Best IS PBO</span><span className="stat-value">{fmtPct(best.is_pbo)}</span></div>
                    <div className={`stat-card ${best.oos_pnl !== null && best.oos_pnl >= 0 ? "stat-card-positive" : best.oos_pnl !== null && best.oos_pnl < 0 ? "stat-card-negative" : ""}`}>
                      <span className="stat-label">Best OOS PnL</span><span className="stat-value">{fmt(best.oos_pnl)}</span>
                    </div>
                    <div className="stat-card"><span className="stat-label">IS/OOS Ratio</span><span className="stat-value">{fmt(best.is_oos_ratio, 3)}</span></div>
                  </>
                );
              })()}
            </div>
            {(() => {
              const best = results.combination_results.find((c) => c.rank === 1);
              if (!best) return null;
              return (
                <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--teal-border)", background: "var(--teal-dim)" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "var(--teal)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Best parameters</span>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>
                    {Object.entries(best.overrides).map(([k, v]) => (
                      <span key={k} style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{k}={typeof v === "number" && !Number.isInteger(v) ? v.toFixed(4) : v}</span>
                    ))}
                  </div>
                  <button
                    className="btn btn-secondary"
                    style={{ marginTop: 8, fontSize: 11, padding: "4px 10px", display: "inline-flex", alignItems: "center", gap: 4 }}
                    onClick={() => saveTrader(best)}
                    disabled={savingIdx === best.combo_idx}
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 2h9l3 3v9H2z" /><rect x="5" y="9" width="6" height="5" /><rect x="5" y="2" width="4" height="3" />
                    </svg>
                    {savingIdx === best.combo_idx ? "Saving..." : "Save as trader.py"}
                  </button>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Ranking table */}
      {results && results.combination_results.length > 0 && (
        <div className="panel">
          <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="panel-title">
              Ranking ({rows.length}{rows.length !== results.combination_results.length ? ` / ${results.combination_results.length}` : ""} combinations)
            </p>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => setShowFilters((v) => !v)}
            >
              {showFilters ? "Hide Filters" : "Show Filters"}
            </button>
          </div>

          {/* Filter row */}
          {showFilters && (
            <div style={{ padding: "8px 14px", background: "var(--bg-offset)", borderBottom: "1px solid var(--border)", display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              {METRIC_COLS.map((col) => (
                <div key={col.key} style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10 }}>
                  <span style={{ fontWeight: 600, color: "var(--text-dim)", minWidth: 55 }}>{col.label}</span>
                  <input
                    type="number"
                    placeholder="min"
                    value={filters[col.key]?.min ?? ""}
                    onChange={(e) => setFilter(col.key, "min", e.target.value)}
                    style={{ width: 52, padding: "2px 4px", fontSize: 10 }}
                  />
                  <span style={{ color: "var(--text-dim)" }}>-</span>
                  <input
                    type="number"
                    placeholder="max"
                    value={filters[col.key]?.max ?? ""}
                    onChange={(e) => setFilter(col.key, "max", e.target.value)}
                    style={{ width: 52, padding: "2px 4px", fontSize: 10 }}
                  />
                </div>
              ))}
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: "2px 6px", color: "var(--red)" }}
                onClick={() => setFilters({})}
              >
                Clear
              </button>
            </div>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }} onClick={() => cycleSort("rank")}>
                    #{sortIcon("rank")}
                  </th>
                  <th>Parameters</th>
                  {METRIC_COLS.map((col) => (
                    <th
                      key={col.key}
                      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", fontSize: 11 }}
                      onClick={() => cycleSort(col.key)}
                    >
                      {col.label}{sortIcon(col.key)}
                    </th>
                  ))}
                  <th style={{ width: 32 }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((cr: OptCombinationResult) => (
                  <tr key={cr.combo_idx} style={cr.rank === 1 ? { background: "rgba(20,184,166,0.06)" } : undefined}>
                    <td style={{ fontWeight: 700 }}>{cr.rank}</td>
                    <td style={{ fontSize: 10, fontFamily: "monospace", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {Object.entries(cr.overrides).map(([k, v]) => `${k}=${typeof v === "number" && !Number.isInteger(v) ? v.toFixed(3) : v}`).join(", ")}
                    </td>
                    {METRIC_COLS.map((col) => {
                      const v = col.get(cr);
                      const cls = col.colorize && v !== null ? (v >= 0 ? "pnl-positive" : "pnl-negative") : undefined;
                      return (
                        <td key={col.key} className={cls} style={{ fontSize: 11 }}>
                          {col.fmt(v)}
                        </td>
                      );
                    })}
                    <td>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "2px 4px", fontSize: 10, lineHeight: 1 }}
                        title="Save as trader.py"
                        onClick={() => saveTrader(cr)}
                        disabled={savingIdx === cr.combo_idx}
                      >
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M2 2h9l3 3v9H2z" /><rect x="5" y="9" width="6" height="5" /><rect x="5" y="2" width="4" height="3" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Config / launcher view ──────────────────────────────────────────────
function OptLauncherView() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [traderPath, setTraderPath] = useState("");
  const datasetsQ = useQuery({ queryKey: ["datasets"], queryFn: () => apiFetch<DatasetInfo[]>("/api/datasets") });
  const datasets = datasetsQ.data ?? [];
  const [selectedDays, setSelectedDays] = useState<string[]>([]);

  // Products
  const productsQ = useQuery({ queryKey: ["products"], queryFn: () => apiFetch<string[]>("/api/datasets/products") });
  const allProducts = productsQ.data ?? [];
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);

  // Auto-select days on first load
  if (datasets.length > 0 && selectedDays.length === 0) {
    const all = datasets.map((d) => `${d.round_num}:${d.day_num}`);
    setSelectedDays(all);
  }

  // Auto-select all products on first load
  if (allProducts.length > 0 && selectedProducts.length === 0) {
    setSelectedProducts(allProducts);
  }

  // Parameter discovery
  const [discoveredParams, setDiscoveredParams] = useState<DiscoveredParam[]>([]);
  const [enabledParams, setEnabledParams] = useState<Record<string, boolean>>({});
  const [paramConfig, setParamConfig] = useState<Record<string, { min: number; max: number; step: number }>>({});

  const discoverMut = useMutation({
    mutationFn: () => apiFetch<DiscoveredParam[]>(`/api/research/optimization/discover?trader_path=${encodeURIComponent(traderPath)}`),
    onSuccess: (data) => {
      setDiscoveredParams(data);
      const enabled: Record<string, boolean> = {};
      const config: Record<string, { min: number; max: number; step: number }> = {};
      for (const p of data) {
        enabled[p.name] = false;
        const dv = p.default_value;
        const step = p.type === "int" ? 1 : Math.max(0.01, Math.abs(dv) * 0.2);
        config[p.name] = {
          min: p.type === "int" ? Math.max(1, dv - 3) : Math.max(0, dv - step * 3),
          max: p.type === "int" ? dv + 3 : dv + step * 3,
          step: p.type === "int" ? 1 : parseFloat(step.toFixed(4)),
        };
      }
      setEnabledParams(enabled);
      setParamConfig(config);
    },
  });

  // Matching mode + invisible taker params
  const [matchingMode, setMatchingMode] = useState("invisible");
  const [fillProbability, setFillProbability] = useState(0.005);
  const [activityBoost, setActivityBoost] = useState(0.003);
  const [sigma, setSigma] = useState(0.0);
  const [edgeFillBoost, setEdgeFillBoost] = useState(0.0);

  // Import file ref
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Export parameter config as JSON
  const exportParamConfig = () => {
    const preset: ParamPreset[] = discoveredParams.map((p) => ({
      name: p.name,
      default_value: p.default_value,
      type: p.type,
      enabled: !!enabledParams[p.name],
      min: paramConfig[p.name]?.min ?? 0,
      max: paramConfig[p.name]?.max ?? 1,
      step: paramConfig[p.name]?.step ?? 0.01,
    }));
    const blob = new Blob([JSON.stringify(preset, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `opt-params-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Import parameter config from JSON
  const importParamConfig = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const preset: ParamPreset[] = JSON.parse(ev.target?.result as string);
        if (!Array.isArray(preset)) return;
        const newEnabled: Record<string, boolean> = { ...enabledParams };
        const newConfig: Record<string, { min: number; max: number; step: number }> = { ...paramConfig };
        for (const p of preset) {
          if (!p.name) continue;
          newEnabled[p.name] = !!p.enabled;
          newConfig[p.name] = { min: p.min, max: p.max, step: p.step };
        }
        setEnabledParams(newEnabled);
        setParamConfig(newConfig);
      } catch { /* ignore bad files */ }
    };
    reader.readAsText(file);
    // Reset so the same file can be re-imported
    e.target.value = "";
  };

  // Search settings
  const [searchMethod, setSearchMethod] = useState("grid");
  const [searchBudget, setSearchBudget] = useState(30);
  const [objective, setObjective] = useState("mean_pnl");
  const [isFraction, setIsFraction] = useState(0.7);
  const [cpcvN, setCpcvN] = useState(5);
  const [cpcvK, setCpcvK] = useState(1);
  const [purge, setPurge] = useState(1);
  const [embargo, setEmbargo] = useState(0.0);
  const [minTrades, setMinTrades] = useState(5);

  // Existing runs
  const optRunsQ = useQuery({
    queryKey: ["opt-runs"],
    queryFn: () => apiFetch<OptimizationRun[]>("/api/research/optimization"),
    refetchInterval: 5000,
  });

  const enabledList = Object.entries(enabledParams).filter(([, v]) => v).map(([k]) => k);
  const totalGrid = enabledList.reduce((acc, name) => {
    const c = paramConfig[name];
    if (!c) return acc;
    return acc * Math.max(1, Math.floor((c.max - c.min) / c.step) + 1);
  }, 1);
  const effectiveCombos = searchMethod === "grid" ? Math.min(totalGrid, searchBudget) : searchBudget;

  // Compute CPCV paths
  let cpcvPaths = 0;
  {
    let num = 1, den = 1;
    for (let i = 0; i < cpcvK; i++) { num *= cpcvN - i; den *= i + 1; }
    cpcvPaths = Math.round(num / den);
    // Subtract purge-invalid (rough estimate)
    if (purge > 0 && cpcvK >= 2) {
      cpcvPaths = Math.max(1, Math.floor(cpcvPaths * 0.8));
    }
  }
  const totalRuns = effectiveCombos * (cpcvPaths + 1);

  const buildLimitOverrides = () => {
    const overrides: Record<string, number> = {};
    for (const p of allProducts) {
      if (!selectedProducts.includes(p)) overrides[p] = 0;
    }
    return overrides;
  };

  const launchMut = useMutation({
    mutationFn: async () => {
      const parameters = enabledList.map((name) => ({
        name,
        min_value: paramConfig[name].min,
        max_value: paramConfig[name].max,
        step: paramConfig[name].step,
        type: discoveredParams.find((p) => p.name === name)?.type ?? "float",
      }));
      return apiFetch<OptimizationRun>("/api/research/optimization", {
        method: "POST",
        body: JSON.stringify({
          trader_path: traderPath,
          round_days: selectedDays.map((v) => {
            const [round_num, day_num] = v.split(":").map(Number);
            return { round_num, day_num };
          }),
          parameters,
          search_method: searchMethod,
          search_budget: searchBudget,
          objective,
          is_fraction: isFraction,
          cpcv_n: cpcvN,
          cpcv_k: cpcvK,
          purge_groups: purge,
          embargo_pct: embargo,
          matching_mode: matchingMode,
          fill_probability: fillProbability,
          activity_boost: activityBoost,
          sigma,
          edge_fill_boost: edgeFillBoost,
          min_trades: minTrades,
          limit_overrides: buildLimitOverrides(),
        }),
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["opt-runs"] });
      navigate(`/optimization/${data.opt_id}`);
    },
  });

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Research</p>
          <h1 className="page-title">Parameter Optimization</h1>
          <p className="page-desc">
            CPCV-based parameter optimization with IS/OOS validation and deflated Sharpe correction.
          </p>
        </div>
      </div>

      <div className="split-layout">
        {/* Left: Config */}
        <div className="stack gap-16">
          {/* Trader + Data */}
          <div className="panel">
            <div className="panel-header"><p className="panel-title">Strategy</p></div>
            <div className="panel-body stack gap-12">
              <div className="field">
                <span className="field-label">Trader file</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input value={traderPath} onChange={(e) => setTraderPath(e.target.value)} placeholder="/path/to/trader.py" style={{ flex: 1 }} />
                  <button className="btn btn-secondary" disabled={!traderPath.trim() || discoverMut.isPending} onClick={() => discoverMut.mutate()}>
                    {discoverMut.isPending ? "Scanning..." : "Discover"}
                  </button>
                </div>
              </div>
              <div className="field">
                <span className="field-label">Datasets</span>
                <div className="dataset-checkbox-grid">
                  {datasets.map((ds) => {
                    const val = `${ds.round_num}:${ds.day_num}`;
                    return (
                      <label key={val} className="dataset-checkbox-card">
                        <input type="checkbox" checked={selectedDays.includes(val)} onChange={(e) => setSelectedDays(e.target.checked ? [...selectedDays, val] : selectedDays.filter((v) => v !== val))} />
                        <div className="dataset-checkbox-label"><strong>R{ds.round_num} D{ds.day_num}</strong></div>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="field">
                <span className="field-label">Products</span>
                {allProducts.length > 0 ? (
                  <div className="dataset-checkbox-grid">
                    {allProducts.map((product) => (
                      <label key={product} className="dataset-checkbox-card">
                        <input type="checkbox" checked={selectedProducts.includes(product)} onChange={(e) => setSelectedProducts(e.target.checked ? [...selectedProducts, product] : selectedProducts.filter((p) => p !== product))} />
                        <div className="dataset-checkbox-label"><strong>{product}</strong></div>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="muted-text" style={{ fontSize: 12 }}>Loading products...</p>
                )}
              </div>
              <div className="field">
                <span className="field-label">Matching mode</span>
                <select value={matchingMode} onChange={(e) => setMatchingMode(e.target.value)}>
                  <option value="prosperity">Prosperity — matches against CSV market trades</option>
                  <option value="invisible">Invisible Taker — probabilistic fills (realistic)</option>
                </select>
                <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                  {matchingMode === "invisible"
                    ? "Simulates invisible taker bots like the real exchange. Fill probability is random per tick."
                    : "Matches passive orders against market trades from CSV data. Overfills compared to real exchange."}
                </span>
              </div>
              {matchingMode === "invisible" && (
                <>
                  <div className="field">
                    <span className="field-label">Base fill probability: {(fillProbability * 100).toFixed(2)}%</span>
                    <input type="range" min={0.0001} max={0.05} step={0.0001} value={fillProbability} onChange={(e) => setFillProbability(parseFloat(e.target.value))} style={{ width: "100%" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>0.01%</span><span>5%</span></div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>Per-tick fill chance. Keep low — with ~10k ticks/day even 0.5% yields ~50 fills.</span>
                  </div>
                  <div className="field">
                    <span className="field-label">Activity boost: +{(activityBoost * 100).toFixed(2)}%</span>
                    <input type="range" min={0} max={0.02} step={0.0001} value={activityBoost} onChange={(e) => setActivityBoost(parseFloat(e.target.value))} style={{ width: "100%" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>0%</span><span>2%</span></div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Extra fill probability when bot-to-bot trades exist at the same tick.
                      Effective: {(fillProbability * 100).toFixed(2)}% + {(activityBoost * 100).toFixed(2)}% = {((fillProbability + activityBoost) * 100).toFixed(2)}% when active.
                    </span>
                  </div>
                  <div className="field">
                    <span className="field-label">Sigma (randomize): {sigma.toFixed(3)}</span>
                    <input type="range" min={0} max={0.02} step={0.001} value={sigma} onChange={(e) => setSigma(parseFloat(e.target.value))} style={{ width: "100%" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>0 (deterministic)</span><span>0.02</span></div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>When &gt; 0, fill probability is drawn from N(centre, sigma) each tick, making fills more stochastic.</span>
                  </div>
                  <div className="field">
                    <span className="field-label">Edge fill boost: {edgeFillBoost.toFixed(2)}</span>
                    <input type="range" min={0} max={2} step={0.05} value={edgeFillBoost} onChange={(e) => setEdgeFillBoost(parseFloat(e.target.value))} style={{ width: "100%" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>0 (off)</span><span>2.0</span></div>
                    <span style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      Tighter quotes get more fills. Multiplier per tick of price improvement over best market quote. E.g. 0.5 with 3-tick edge = +150% fill probability.
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Discovered parameters */}
          {discoveredParams.length > 0 && (
            <div className="panel">
              <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <p className="panel-title">Parameters ({enabledList.length} selected)</p>
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={exportParamConfig} title="Export parameter ranges as JSON">
                    Export
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => fileInputRef.current?.click()} title="Import parameter ranges from JSON">
                    Import
                  </button>
                  <input ref={fileInputRef} type="file" accept=".json" style={{ display: "none" }} onChange={importParamConfig} />
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th></th><th>Name</th><th>Default</th><th>Min</th><th>Max</th><th>Step</th></tr></thead>
                  <tbody>
                    {discoveredParams.map((p) => (
                      <tr key={p.name}>
                        <td><input type="checkbox" checked={!!enabledParams[p.name]} onChange={(e) => setEnabledParams({ ...enabledParams, [p.name]: e.target.checked })} /></td>
                        <td style={{ fontFamily: "monospace", fontWeight: 600 }}>{p.name}</td>
                        <td>{p.default_value}</td>
                        <td>
                          <input type="number" value={paramConfig[p.name]?.min ?? 0} step={paramConfig[p.name]?.step ?? 0.01} style={{ width: 70, padding: "4px 6px", fontSize: 12 }}
                            onChange={(e) => setParamConfig({ ...paramConfig, [p.name]: { ...paramConfig[p.name], min: parseFloat(e.target.value) || 0 } })} />
                        </td>
                        <td>
                          <input type="number" value={paramConfig[p.name]?.max ?? 1} step={paramConfig[p.name]?.step ?? 0.01} style={{ width: 70, padding: "4px 6px", fontSize: 12 }}
                            onChange={(e) => setParamConfig({ ...paramConfig, [p.name]: { ...paramConfig[p.name], max: parseFloat(e.target.value) || 1 } })} />
                        </td>
                        <td>
                          <input type="number" value={paramConfig[p.name]?.step ?? 0.01} min={0.001} step={0.001} style={{ width: 70, padding: "4px 6px", fontSize: 12 }}
                            onChange={(e) => setParamConfig({ ...paramConfig, [p.name]: { ...paramConfig[p.name], step: parseFloat(e.target.value) || 0.01 } })} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Search settings */}
          <div className="panel">
            <div className="panel-header"><p className="panel-title">Search</p></div>
            <div className="panel-body stack gap-12">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="field">
                  <span className="field-label">Method</span>
                  <select value={searchMethod} onChange={(e) => setSearchMethod(e.target.value)}>
                    <option value="grid">Grid search</option>
                    <option value="random">Random search</option>
                  </select>
                </div>
                <div className="field">
                  <span className="field-label">Budget (max combos)</span>
                  <input type="number" min={1} max={500} value={searchBudget} onChange={(e) => setSearchBudget(parseInt(e.target.value, 10) || 30)} />
                </div>
              </div>
              <div className="field">
                <span className="field-label">Objective</span>
                <select value={objective} onChange={(e) => setObjective(e.target.value)}>
                  <option value="mean_pnl">Maximize IS Mean PnL</option>
                  <option value="sharpe">Maximize IS Sharpe Ratio</option>
                  <option value="pbo">Minimize IS PBO (overfitting probability)</option>
                </select>
              </div>
              <div className="field">
                <span className="field-label">Minimum fills per combo</span>
                <input type="number" min={0} max={100} value={minTrades} onChange={(e) => setMinTrades(parseInt(e.target.value, 10) || 0)} />
                <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Discard parameter sets that produce fewer fills (degenerate strategies).</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: IS/OOS + CPCV + Launch */}
        <div className="stack gap-16">
          <div className="panel">
            <div className="panel-header"><p className="panel-title">In-Sample / Out-of-Sample</p></div>
            <div className="panel-body stack gap-12">
              <div className="field">
                <span className="field-label">IS fraction: {(isFraction * 100).toFixed(0)}% / {(100 - isFraction * 100).toFixed(0)}% OOS</span>
                <input type="range" min={0.3} max={0.95} step={0.05} value={isFraction} onChange={(e) => setIsFraction(parseFloat(e.target.value))} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>30%</span><span>95%</span></div>
                <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
                  Optimization runs CPCV on the IS portion only. OOS is held out for final validation.
                  Larger IS = more data to learn from but less to validate on.
                </span>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header"><p className="panel-title">CPCV Evaluation</p></div>
            <div className="panel-body stack gap-12">
              <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                Each parameter combination is evaluated by running a mini-CPCV on the IS data.
                Smaller N/k = faster but less robust evaluation.
              </span>
              <div className="field">
                <span className="field-label">N (folds): {cpcvN}</span>
                <input type="range" min={2} max={10} step={1} value={cpcvN} onChange={(e) => { const v = parseInt(e.target.value, 10); setCpcvN(v); if (cpcvK >= v) setCpcvK(v - 1); }} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>2</span><span>10</span></div>
              </div>
              <div className="field">
                <span className="field-label">k (test folds): {cpcvK}</span>
                <input type="range" min={1} max={Math.max(1, cpcvN - 1)} step={1} value={cpcvK} onChange={(e) => setCpcvK(parseInt(e.target.value, 10))} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}><span>1</span><span>{cpcvN - 1}</span></div>
              </div>
              <div className="field">
                <span className="field-label">Purge gap: {purge}</span>
                <input type="range" min={0} max={3} step={1} value={purge} onChange={(e) => setPurge(parseInt(e.target.value, 10))} />
              </div>
              <div className="field">
                <span className="field-label">Embargo: {(embargo * 100).toFixed(0)}%</span>
                <input type="range" min={0} max={0.2} step={0.01} value={embargo} onChange={(e) => setEmbargo(parseFloat(e.target.value))} />
              </div>
            </div>
          </div>

          {/* Run estimate & launch */}
          <div className="panel">
            <div className="panel-header"><p className="panel-title">Launch</p></div>
            <div className="panel-body stack gap-12">
              <div className="stats-grid">
                <div className="stat-card"><span className="stat-label">Combinations</span><span className="stat-value">{effectiveCombos}</span></div>
                <div className="stat-card"><span className="stat-label">CPCV paths</span><span className="stat-value">~{cpcvPaths}</span></div>
                <div className="stat-card"><span className="stat-label">Total runs</span><span className="stat-value">~{totalRuns}</span></div>
              </div>
              <button
                className="btn btn-primary btn-full"
                disabled={launchMut.isPending || enabledList.length === 0 || selectedDays.length === 0 || !traderPath.trim() || selectedProducts.length === 0}
                onClick={() => launchMut.mutate()}
              >
                {launchMut.isPending ? "Launching..." : `Start Optimization (~${totalRuns} runs)`}
              </button>
              {launchMut.isError && <p className="error-text">{String((launchMut.error as Error)?.message ?? launchMut.error)}</p>}
            </div>
          </div>

          {/* Previous runs */}
          <div className="panel">
            <div className="panel-header"><p className="panel-title">Previous Optimizations</p></div>
            <div className="panel-body">
              {(optRunsQ.data ?? []).length === 0 && <p className="muted-text" style={{ fontSize: 12 }}>No optimization runs yet.</p>}
              <div className="run-list">
                {(optRunsQ.data ?? []).map((r: OptimizationRun) => (
                  <div key={r.opt_id} className="run-row" onClick={() => navigate(`/optimization/${r.opt_id}`)}>
                    <div className="run-row-left">
                      <span className="run-row-id">{r.opt_id}</span>
                      <span className="run-row-path">{r.total_combinations} combos &middot; {r.objective}</span>
                    </div>
                    <div className="run-row-right">
                      <span className={`pill pill-${r.status}`} style={{ fontSize: 10 }}>{r.status}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{r.completed_runs}/{r.total_runs}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page root ───────────────────────────────────────────────────────────
export function ResearchOptimizationPage() {
  const { optId } = useParams<{ optId: string }>();
  if (optId) return <OptResultsView optId={optId} />;
  return <OptLauncherView />;
}
