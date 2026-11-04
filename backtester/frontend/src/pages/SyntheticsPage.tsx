import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api/client";

type SyntheticSummary = {
  scenario: string;
  file: string;
  pnl: number;
  fills: number;
  orders: number;
  ticks: number;
  final_pos: number;
  n_own_trades: number;
  n_bot_trades: number;
};

type ListResponse = {
  trader_label: string;
  trader_path: string;
  datasets: SyntheticSummary[];
  results_dir: string;
};

type Trader = { name: string; filename: string; path: string };
type LabelInfo = {
  label: string;
  trader_path: string;
  n_datasets: number;
  mean_pnl: number;
};

export function SyntheticsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [selectedTrader, setSelectedTrader] = useState<string>("");

  const labelsQuery = useQuery({
    queryKey: ["synthetics-labels"],
    queryFn: () => apiFetch<{ labels: LabelInfo[] }>("/api/synthetics/labels"),
  });
  const tradersQuery = useQuery({
    queryKey: ["synthetics-traders"],
    queryFn: () => apiFetch<{ traders: Trader[] }>("/api/synthetics/traders"),
  });

  // Default selection once labels load
  const labels = labelsQuery.data?.labels ?? [];
  const activeLabel = selectedLabel ?? labels[0]?.label ?? null;

  const listQuery = useQuery({
    queryKey: ["synthetics-list", activeLabel],
    queryFn: () => apiFetch<ListResponse>(`/api/synthetics?label=${encodeURIComponent(activeLabel!)}`),
    enabled: !!activeLabel,
  });

  const runMutation = useMutation({
    mutationFn: async (params: { trader_path: string; label?: string }) => {
      return apiFetch<ListResponse>("/api/synthetics/run", {
        method: "POST",
        body: JSON.stringify(params),
      });
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["synthetics-labels"] });
      qc.invalidateQueries({ queryKey: ["synthetics-list"] });
      if (data?.trader_label) setSelectedLabel(data.trader_label);
    },
  });

  const datasets = listQuery.data?.datasets ?? [];
  const aggregatePnl = useMemo(
    () => datasets.reduce((acc, d) => acc + d.pnl, 0),
    [datasets]
  );
  const meanPnl = datasets.length > 0 ? aggregatePnl / datasets.length : 0;
  const minPnl = datasets.length > 0 ? Math.min(...datasets.map((d) => d.pnl)) : 0;
  const maxPnl = datasets.length > 0 ? Math.max(...datasets.map((d) => d.pnl)) : 0;
  const totalFills = useMemo(
    () => datasets.reduce((acc, d) => acc + d.fills, 0),
    [datasets]
  );

  const handleOpen = (scenario: string) => {
    if (!activeLabel) return;
    navigate(`/synthetics/${activeLabel}/${scenario}`);
  };

  const handleRun = () => {
    const traderPath = selectedTrader || tradersQuery.data?.traders?.[0]?.path;
    if (!traderPath) return;
    const trader = tradersQuery.data?.traders?.find((t) => t.path === traderPath);
    runMutation.mutate({ trader_path: traderPath, label: trader?.name });
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Synthetics</p>
          <h1 className="page-title">Synthetic Backtests</h1>
          <p className="page-desc">
            Pre-computed runs against synthetic 10k-tick scenarios derived from
            the 1k-tick base Prosperity provides. Select a trader version to
            view its performance, or trigger a fresh run on a different one.
          </p>
        </div>
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-label">Datasets</span>
            <span className="stat-value">{datasets.length}</span>
          </div>
          <div className={`stat-card ${meanPnl >= 0 ? "stat-card-positive" : "stat-card-negative"}`}>
            <span className="stat-label">Mean PnL</span>
            <span className="stat-value">{meanPnl >= 0 ? "+" : ""}{meanPnl.toFixed(0)}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Min / Max</span>
            <span className="stat-value" style={{ fontSize: 13 }}>
              {minPnl.toFixed(0)} / {maxPnl.toFixed(0)}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Total fills</span>
            <span className="stat-value">{totalFills}</span>
          </div>
        </div>
      </div>

      {/* Trader selector + run trigger */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Configure</p>
            <p className="panel-title">Trader Version</p>
          </div>
        </div>
        <div className="panel-body" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 11, color: "var(--text-dim)" }}>Cached results</label>
            <select
              value={activeLabel ?? ""}
              onChange={(e) => setSelectedLabel(e.target.value || null)}
              style={{
                background: "var(--bg-inset, #0d1117)", color: "var(--text)",
                border: "1px solid var(--border-subtle)", borderRadius: 4,
                padding: "6px 10px", fontSize: 12, fontFamily: "monospace",
                minWidth: 180,
              }}
            >
              {labels.length === 0 && <option value="">— no results yet —</option>}
              {labels.map((l) => (
                <option key={l.label} value={l.label}>
                  {l.label}  ({l.n_datasets} ds, mean PnL {l.mean_pnl.toFixed(0)})
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 11, color: "var(--text-dim)" }}>Trader to run</label>
            <select
              value={selectedTrader}
              onChange={(e) => setSelectedTrader(e.target.value)}
              style={{
                background: "var(--bg-inset, #0d1117)", color: "var(--text)",
                border: "1px solid var(--border-subtle)", borderRadius: 4,
                padding: "6px 10px", fontSize: 12, fontFamily: "monospace",
                minWidth: 200,
              }}
            >
              {(tradersQuery.data?.traders ?? []).map((t) => (
                <option key={t.path} value={t.path}>
                  {t.filename}
                </option>
              ))}
            </select>
          </div>

          <button
            className="btn btn-primary"
            onClick={handleRun}
            disabled={runMutation.isPending}
            style={{ marginTop: 18 }}
          >
            {runMutation.isPending ? "Running…" : "Run all 13 scenarios"}
          </button>

          {runMutation.isError && (
            <div style={{ color: "var(--red, #f85149)", fontSize: 11 }}>
              {String(runMutation.error)}
            </div>
          )}
          {runMutation.isPending && (
            <div style={{ color: "var(--text-dim)", fontSize: 11 }}>
              ~15-30s for all 13 datasets…
            </div>
          )}
        </div>
      </div>

      {/* Per-dataset results table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Per-Dataset Performance</p>
            <p className="panel-title">
              {activeLabel ? `Results for ${activeLabel}` : "Select a label above"}
            </p>
          </div>
          {listQuery.data?.trader_path && (
            <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "monospace" }}>
              {listQuery.data.trader_path}
            </span>
          )}
        </div>
        <div className="panel-body-sm">
          {listQuery.isLoading && <div className="empty-state">Loading…</div>}
          {listQuery.error && (
            <div style={{ color: "var(--red, #f85149)", fontSize: 12 }}>
              {String(listQuery.error)}
            </div>
          )}
          {datasets.length > 0 && (
            <div className="table-wrap">
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th style={{ textAlign: "right" }}>PnL</th>
                    <th style={{ textAlign: "right" }}>Fills</th>
                    <th style={{ textAlign: "right" }}>Orders</th>
                    <th style={{ textAlign: "right" }}>Ticks</th>
                    <th style={{ textAlign: "right" }}>Final pos</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((d) => (
                    <tr
                      key={d.scenario}
                      style={{ cursor: "pointer" }}
                      onClick={() => handleOpen(d.scenario)}
                    >
                      <td style={{ fontWeight: 500 }}>{d.scenario}</td>
                      <td style={{
                        textAlign: "right",
                        fontFamily: "monospace",
                        color: d.pnl >= 0 ? "var(--bid, #3fb950)" : "var(--ask, #f85149)",
                      }}>
                        {d.pnl >= 0 ? "+" : ""}{d.pnl.toFixed(0)}
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "monospace" }}>{d.fills}</td>
                      <td style={{ textAlign: "right", fontFamily: "monospace" }}>{d.orders}</td>
                      <td style={{ textAlign: "right", fontFamily: "monospace" }}>{d.ticks}</td>
                      <td style={{ textAlign: "right", fontFamily: "monospace" }}>{d.final_pos}</td>
                      <td>
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: 10, padding: "3px 8px" }}
                          onClick={(e) => { e.stopPropagation(); handleOpen(d.scenario); }}
                        >
                          Open visualizer →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
