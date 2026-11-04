import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { ActivityRow, OrderbookSnapshot, RawPriceRow, RunLogs, RunRecord, TradeRow } from "../api/types";
import { OrderbookPanel } from "../features/orderbook/OrderbookPanel";
import { TimelineChart } from "../features/timeline/TimelineChart";
import { TickInspector } from "../features/timeline/TickInspector";
import { useTimelineStore } from "../features/timeline/useTimelineStore";
import { TradesPanel } from "../features/trades/TradesPanel";
import { LogsPanel } from "../features/logs/LogsPanel";
import { ImportOfficialLogForm } from "../features/comparisons/ImportOfficialLogForm";

function NoRunSelected({ onGoBacktest }: { onGoBacktest: () => void }) {
  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Results</p>
          <h1 className="page-title">No Run Selected</h1>
          <p className="page-desc">Launch a simulation first, then come back here.</p>
        </div>
      </div>
      <div className="panel">
        <div className="panel-body">
          <div className="empty-state">
            <span className="empty-state-icon">&#128202;</span>
            <span>No run selected. Launch a backtest to see results.</span>
            <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={onGoBacktest}>
              Go to Backtest
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ResultsPage() {
  const navigate = useNavigate();
  const params = useParams();
  const runId = params.runId ?? "";

  const { product, timestamp, roundNum, dayNum, setProduct, setTimestamp, setContext } =
    useTimelineStore();
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [viewAllDays, setViewAllDays] = useState(false);

  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiFetch<RunRecord>(`/api/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data?.manifest.status === "completed" ? false : 2500
  });

  const runStatus = runQuery.data?.manifest.status ?? "pending";
  const isRunning = runStatus !== "completed";
  const datasets = runQuery.data?.manifest.datasets ?? [];

  // Reset all context when navigating to a different run
  useEffect(() => {
    setTimestamp(null);
    setContext(null, null);
    setViewAllDays(false);
  }, [runId, setTimestamp, setContext]);

  // Set round/day context from the first dataset once manifest loads
  useEffect(() => {
    const firstDataset = runQuery.data?.manifest.datasets?.[0];
    if (firstDataset && !viewAllDays) {
      setContext(firstDataset.round_num, firstDataset.day_num);
    }
  }, [runQuery.data, setContext, viewAllDays]);

  // Build query params helper
  const timelineParams = useMemo(() => {
    if (viewAllDays) return "";
    const p = new URLSearchParams();
    if (roundNum !== null) p.set("round_num", String(roundNum));
    if (dayNum !== null) p.set("day_num", String(dayNum));
    return p.toString();
  }, [roundNum, dayNum, viewAllDays]);

  // Allow fetch when we have a specific day OR are viewing all days
  const canFetch = viewAllDays || (roundNum !== null && dayNum !== null);

  const timelineQuery = useQuery({
    queryKey: ["timeline", runId, viewAllDays ? "all" : `${roundNum}:${dayNum}`, runStatus],
    queryFn: () => {
      const qs = timelineParams ? `?${timelineParams}` : "";
      return apiFetch<ActivityRow[]>(`/api/runs/${runId}/timeline${qs}`);
    },
    enabled: Boolean(runId) && canFetch,
    refetchInterval: isRunning ? 3000 : false,
  });

  // Derive available products and the active product synchronously (no effect delay)
  const allTimelineRows = timelineQuery.data ?? [];
  const products = useMemo(
    () => Array.from(new Set(allTimelineRows.map((row) => row.product))),
    [allTimelineRows]
  );

  // If the store's product isn't available in this run, use the first available one
  const activeProduct = products.length > 0 && !products.includes(product)
    ? products[0]
    : product;

  const productRows = useMemo(
    () => allTimelineRows.filter((row) => row.product === activeProduct),
    [allTimelineRows, activeProduct]
  );

  const orderbookQuery = useQuery({
    queryKey: ["orderbook", runId, activeProduct, timestamp, roundNum, dayNum],
    queryFn: () =>
      apiFetch<OrderbookSnapshot>(
        `/api/runs/${runId}/orderbook?product=${activeProduct}&timestamp=${timestamp}${roundNum !== null ? `&round_num=${roundNum}` : ""}${dayNum !== null ? `&day_num=${dayNum}` : ""}`
      ),
    enabled: Boolean(runId && timestamp !== null && !viewAllDays && roundNum !== null && dayNum !== null)
  });

  const tradesQuery = useQuery({
    queryKey: ["trades", runId, activeProduct, viewAllDays ? "all" : `${roundNum}:${dayNum}`, runStatus],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("product", activeProduct);
      if (!viewAllDays) {
        if (roundNum !== null) p.set("round_num", String(roundNum));
        if (dayNum !== null) p.set("day_num", String(dayNum));
      }
      return apiFetch<{ own_trades: TradeRow[]; market_trades: TradeRow[] }>(
        `/api/runs/${runId}/trades?${p.toString()}`
      );
    },
    enabled: Boolean(runId) && canFetch,
    refetchInterval: isRunning ? 3000 : false,
  });

  const logsQuery = useQuery({
    queryKey: ["logs", runId, runStatus],
    queryFn: () => apiFetch<RunLogs>(`/api/runs/${runId}/logs`),
    enabled: Boolean(runId),
    refetchInterval: isRunning ? 3000 : false,
  });

  // Fetch raw CSV prices for overlay verification
  const rawPricesQuery = useQuery({
    queryKey: ["raw-prices", activeProduct],
    queryFn: () => apiFetch<RawPriceRow[]>(`/api/datasets/prices?product=${activeProduct}`),
    enabled: Boolean(activeProduct),
  });

  // Filter raw prices to the current day context (or pass all for "All" mode)
  const rawPricesFiltered = useMemo(() => {
    if (!rawPricesQuery.data) return undefined;
    if (viewAllDays) return rawPricesQuery.data;
    if (roundNum === null || dayNum === null) return undefined;
    return rawPricesQuery.data.filter(
      (rp) => rp.round_num === roundNum && rp.day_num === dayNum
    );
  }, [rawPricesQuery.data, roundNum, dayNum, viewAllDays]);

  // Sync the store when the active product differs (keeps tabs/other components in sync)
  useEffect(() => {
    if (activeProduct !== product) {
      setProduct(activeProduct);
    }
  }, [activeProduct, product, setProduct]);

  useEffect(() => {
    if (productRows.length > 0 && timestamp === null && !viewAllDays) {
      setTimestamp(Number(productRows[0].timestamp));
    }
  }, [productRows, timestamp, setTimestamp, viewAllDays]);

  // In all-days mode, clicking the chart returns an offset x-value.
  // Decode it back to raw timestamp + day context.
  const handleSelectTimestamp = useCallback(
    (xValue: number) => {
      if (viewAllDays) {
        const dayIdx = Math.floor(xValue / 1_000_000);
        const rawTs = xValue % 1_000_000;
        const clickedDayNum = dayIdx - 2;
        // Find matching dataset to get round_num
        const ds = datasets.find((d) => d.day_num === clickedDayNum);
        if (ds) {
          setViewAllDays(false);
          setContext(ds.round_num, ds.day_num);
          setTimestamp(rawTs);
        }
      } else {
        setTimestamp(xValue);
      }
    },
    [viewAllDays, datasets, setContext, setTimestamp],
  );

  if (!runId) {
    return <NoRunSelected onGoBacktest={() => navigate("/backtest")} />;
  }

  const summary = runQuery.data?.summary;
  const traderFile = runQuery.data?.manifest.trader_path?.split(/[\\/]/).pop() ?? "Unknown trader";
  const matchingMode = runQuery.data?.manifest.matching_mode ?? "prosperity";

  const finalPnl = summary?.final_pnl;

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Results</p>
          <h1 className="page-title" style={{ fontFamily: "monospace", fontSize: 16, letterSpacing: "0.02em" }}>
            {runId}
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
            <span className={`pill pill-${runStatus}`}>{runStatus}</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{traderFile}</span>
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>&middot;</span>
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{matchingMode}</span>
          </div>
        </div>
        <div className="stats-row">
          <div className={`stat-card ${finalPnl !== undefined ? (finalPnl >= 0 ? "stat-card-positive" : "stat-card-negative") : ""}`}>
            <span className="stat-label">Final PnL</span>
            <span className="stat-value">
              {finalPnl !== undefined ? `${finalPnl >= 0 ? "+" : ""}${finalPnl.toFixed(2)}` : "--"}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Ticks</span>
            <span className="stat-value">{summary?.total_ticks ?? "--"}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Fills</span>
            <span className="stat-value">{summary?.total_fills ?? "--"}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Orders</span>
            <span className="stat-value">{summary?.total_orders ?? "--"}</span>
          </div>
        </div>
      </div>

      {/* Timeline with product tabs */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Replay</p>
            <p className="panel-title">Timeline Explorer</p>
          </div>
          <div className="toolbar">
            {/* Day tabs (including "All") */}
            {datasets.length > 1 && (
              <div className="tabs">
                <button
                  className={`tab${viewAllDays ? " active" : ""}`}
                  onClick={() => {
                    setTimestamp(null);
                    setContext(null, null);
                    setViewAllDays(true);
                  }}
                >
                  All
                </button>
                {datasets.map((ds) => {
                  const active = !viewAllDays && ds.round_num === roundNum && ds.day_num === dayNum;
                  return (
                    <button
                      key={`${ds.round_num}:${ds.day_num}`}
                      className={`tab${active ? " active" : ""}`}
                      onClick={() => {
                        setTimestamp(null);
                        setViewAllDays(false);
                        setContext(ds.round_num, ds.day_num);
                      }}
                    >
                      R{ds.round_num}D{ds.day_num}
                    </button>
                  );
                })}
              </div>
            )}
            {/* Product tabs */}
            {products.length > 0 ? (
              <div className="tabs">
                {products.map((p) => (
                  <button
                    key={p}
                    className={`tab${activeProduct === p ? " active" : ""}`}
                    onClick={() => setProduct(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            ) : (
              <div className="tabs">
                <span className="tab active" style={{ color: "var(--text-dim)", fontSize: 11 }}>Loading…</span>
              </div>
            )}
            {timestamp !== null && !viewAllDays && (
              <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>
                t={timestamp}
              </span>
            )}
            <button
              className="btn btn-ghost"
              style={{ fontSize: 16, padding: "2px 8px", lineHeight: 1 }}
              onClick={() => setChartFullscreen(true)}
              title="Open fullscreen"
            >
              &#x26F6;
            </button>
          </div>
        </div>
        <div style={{ padding: "8px 0 4px" }}>
          {(timelineQuery.isLoading || productRows.length === 0) && !timelineQuery.data && (
            <div style={{ height: 320, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span className="muted-text">{isRunning ? "Waiting for results..." : "Loading timeline..."}</span>
            </div>
          )}
          {productRows.length > 0 && (
            <TimelineChart
              rows={productRows}
              ownTrades={tradesQuery.data?.own_trades ?? []}
              decisionTrace={(logsQuery.data?.decision_trace ?? []) as Parameters<typeof TimelineChart>[0]["decisionTrace"]}
              product={activeProduct}
              roundNum={roundNum}
              dayNum={dayNum}
              selectedTimestamp={timestamp}
              onSelectTimestamp={handleSelectTimestamp}
              rawPrices={rawPricesFiltered}
              viewAllDays={viewAllDays}
            />
          )}
          {timestamp !== null && !viewAllDays && (
            <div style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <TickInspector
                timestamp={timestamp}
                product={activeProduct}
                decisionTrace={(logsQuery.data?.decision_trace ?? []) as Parameters<typeof TickInspector>[0]["decisionTrace"]}
                events={(logsQuery.data?.events ?? []) as Parameters<typeof TickInspector>[0]["events"]}
              />
            </div>
          )}
        </div>
      </div>

      {/* Orderbook */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Snapshot</p>
            <p className="panel-title">Order Book</p>
          </div>
          {timestamp !== null && !viewAllDays && (
            <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>
              t={timestamp}
            </span>
          )}
        </div>
        <div className="panel-body">
          <OrderbookPanel snapshot={orderbookQuery.data ?? null} />
        </div>
      </div>

      {/* Trades */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Execution</p>
            <p className="panel-title">Trades</p>
          </div>
        </div>
        <div className="panel-body-sm">
          <TradesPanel
            ownTrades={tradesQuery.data?.own_trades ?? []}
            marketTrades={tradesQuery.data?.market_trades ?? []}
          />
        </div>
      </div>

      {/* Logs */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Debug</p>
            <p className="panel-title">Execution Logs</p>
          </div>
        </div>
        <div className="panel-body">
          <LogsPanel
            sandbox={logsQuery.data?.sandbox ?? ""}
            decisionTrace={logsQuery.data?.decision_trace ?? []}
            events={logsQuery.data?.events ?? []}
          />
        </div>
      </div>

      {/* Official comparison */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Calibration</p>
            <p className="panel-title">Official Log Comparison</p>
          </div>
        </div>
        <div className="panel-body">
          <ImportOfficialLogForm runId={runId} />
        </div>
      </div>

      {/* Fullscreen overlay */}
      {chartFullscreen && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 9999,
            background: "var(--bg, #0d1117)",
            display: "flex", flexDirection: "column",
          }}
        >
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "8px 16px", borderBottom: "1px solid var(--border-subtle)",
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 13, color: "var(--text-dim)", fontFamily: "monospace" }}>
              Timeline Explorer &mdash; {activeProduct}
              {viewAllDays ? " (all days)" : ""}
              {timestamp !== null && !viewAllDays ? ` &middot; t=${timestamp}` : ""}
            </span>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 16, padding: "2px 8px", lineHeight: 1 }}
              onClick={() => setChartFullscreen(false)}
              title="Close fullscreen"
            >
              &#x2715;
            </button>
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <TimelineChart
              rows={productRows}
              ownTrades={tradesQuery.data?.own_trades ?? []}
              decisionTrace={(logsQuery.data?.decision_trace ?? []) as Parameters<typeof TimelineChart>[0]["decisionTrace"]}
              product={activeProduct}
              roundNum={roundNum}
              dayNum={dayNum}
              selectedTimestamp={timestamp}
              onSelectTimestamp={handleSelectTimestamp}
              isFullscreen={true}
              rawPrices={rawPricesFiltered}
              viewAllDays={viewAllDays}
            />
          </div>
        </div>
      )}
    </div>
  );
}
