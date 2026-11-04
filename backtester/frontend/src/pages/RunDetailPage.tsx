import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { ActivityRow, OrderbookSnapshot, RunLogs, RunRecord, TradeRow } from "../api/types";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { ImportOfficialLogForm } from "../features/comparisons/ImportOfficialLogForm";
import { LogsPanel } from "../features/logs/LogsPanel";
import { OrderbookPanel } from "../features/orderbook/OrderbookPanel";
import { PnlChart } from "../features/pnl/PnlChart";
import { PositionsPanel } from "../features/positions/PositionsPanel";
import { TimelineChart } from "../features/timeline/TimelineChart";
import { useTimelineStore } from "../features/timeline/useTimelineStore";
import { TradesPanel } from "../features/trades/TradesPanel";

export function RunDetailPage() {
  const params = useParams();
  const runId = params.runId ?? "";
  const { product, timestamp, roundNum, dayNum, setProduct, setTimestamp, setContext } = useTimelineStore();

  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiFetch<RunRecord>(`/api/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: 2500
  });
  const timelineQuery = useQuery({
    queryKey: ["timeline", runId, product, roundNum, dayNum],
    queryFn: () =>
      apiFetch<ActivityRow[]>(
        `/api/runs/${runId}/timeline?product=${product}${roundNum !== null ? `&round_num=${roundNum}` : ""}${
          dayNum !== null ? `&day_num=${dayNum}` : ""
        }`
      ),
    enabled: Boolean(runId)
  });
  const orderbookQuery = useQuery({
    queryKey: ["orderbook", runId, product, timestamp, roundNum, dayNum],
    queryFn: () =>
      apiFetch<OrderbookSnapshot>(
        `/api/runs/${runId}/orderbook?product=${product}&timestamp=${timestamp}${
          roundNum !== null ? `&round_num=${roundNum}` : ""
        }${dayNum !== null ? `&day_num=${dayNum}` : ""}`
      ),
    enabled: Boolean(runId && timestamp !== null)
  });
  const tradesQuery = useQuery({
    queryKey: ["trades", runId, product, timestamp, roundNum, dayNum],
    queryFn: () =>
      apiFetch<{ own_trades: TradeRow[]; market_trades: TradeRow[] }>(
        `/api/runs/${runId}/trades?product=${product}${timestamp !== null ? `&timestamp=${timestamp}` : ""}${
          roundNum !== null ? `&round_num=${roundNum}` : ""
        }${dayNum !== null ? `&day_num=${dayNum}` : ""}`
      ),
    enabled: Boolean(runId)
  });
  const logsQuery = useQuery({
    queryKey: ["logs", runId],
    queryFn: () => apiFetch<RunLogs>(`/api/runs/${runId}/logs`),
    enabled: Boolean(runId)
  });

  useEffect(() => {
    const run = runQuery.data;
    const firstDataset = run?.manifest.datasets?.[0];
    if (firstDataset) {
      setContext(firstDataset.round_num, firstDataset.day_num);
    }
  }, [runQuery.data, setContext]);

  useEffect(() => {
    const rows = timelineQuery.data ?? [];
    if (rows.length > 0 && timestamp === null) {
      setTimestamp(Number(rows[0].timestamp));
    }
  }, [timelineQuery.data, timestamp, setTimestamp]);

  const summary = runQuery.data?.summary;
  const products = Array.from(new Set((timelineQuery.data ?? []).map((row) => row.product)));
  return (
    <div className="page-stack">
      <section className="hero-banner compact-banner">
        <div>
          <p className="hero-kicker">Run Detail</p>
          <h2>{runId}</h2>
          <p>{runQuery.data?.manifest.trader_path ?? "Waiting for worker summary..."}</p>
        </div>
        <div className="stats-grid">
          <StatCard label="Status" value={runQuery.data?.manifest.status ?? "--"} />
          <StatCard label="Ticks" value={String(summary?.total_ticks ?? "--")} />
          <StatCard
            label="PnL"
            value={summary?.final_pnl !== undefined ? summary.final_pnl.toFixed(2) : "--"}
            tone={(summary?.final_pnl ?? 0) >= 0 ? "positive" : "negative"}
          />
        </div>
      </section>

      <Panel
        title="Timeline explorer"
        subtitle="Replay"
        actions={
          <div className="toolbar">
            <select value={product} onChange={(event) => setProduct(event.target.value)}>
              {products.length > 0 ? (
                products.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))
              ) : (
                <>
                  <option value="EMERALDS">EMERALDS</option>
                  <option value="TOMATOES">TOMATOES</option>
                </>
              )}
            </select>
          </div>
        }
      >
        <TimelineChart
          rows={timelineQuery.data ?? []}
          ownTrades={[]}
          decisionTrace={[]}
          product={""}
          roundNum={null}
          dayNum={null}
          selectedTimestamp={timestamp}
          onSelectTimestamp={setTimestamp}
        />
      </Panel>

      <div className="two-column-layout">
        <Panel title="Order book" subtitle="Snapshot">
          <OrderbookPanel snapshot={orderbookQuery.data ?? null} />
        </Panel>
        <Panel title="Positions" subtitle="Inventory">
          <PositionsPanel rows={timelineQuery.data ?? []} />
          <PnlChart rows={timelineQuery.data ?? []} />
        </Panel>
      </div>

      <div className="two-column-layout">
        <Panel title="Trades" subtitle="Execution">
          <TradesPanel
            ownTrades={tradesQuery.data?.own_trades ?? []}
            marketTrades={tradesQuery.data?.market_trades ?? []}
          />
        </Panel>
        <Panel title="Logs" subtitle="Debug">
          <LogsPanel
            sandbox={logsQuery.data?.sandbox ?? ""}
            decisionTrace={logsQuery.data?.decision_trace ?? []}
            events={logsQuery.data?.events ?? []}
          />
        </Panel>
      </div>

      <Panel title="Official comparison" subtitle="Calibration">
        <ImportOfficialLogForm runId={runId} />
      </Panel>
    </div>
  );
}
