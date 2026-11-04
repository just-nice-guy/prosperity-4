import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { parseOfficialLog, ParsedOfficialLog } from "../features/visualizer/parseOfficialLog";
import { ActivityRow, TradeRow } from "../api/types";
import { PriceDepthChart } from "../features/depth/PriceDepthChart";
import { VolumeChart } from "../features/depth/VolumeChart";
import { SummaryPnlChart } from "../features/overview/SummaryPnlChart";
import { PositionOverviewChart, PositionMode } from "../features/overview/PositionOverviewChart";
import { OrderBookTable } from "../features/orderbook/OrderBookTable";
import { TimestampSlider } from "../features/navigation/TimestampSlider";
import { FairValueChart } from "../features/visualizer/FairValueChart";

const N = (v: string | undefined | null) => (v && v !== "" && v !== "None" ? Number(v) : null);

export function SyntheticsDetailPage() {
  const { label, scenario } = useParams<{ label: string; scenario: string }>();
  const [parsed, setParsed] = useState<ParsedOfficialLog | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [product, setProduct] = useState<string>("");
  const [selectedTimestamp, setSelectedTimestamp] = useState<number | null>(null);
  const [positionMode, setPositionMode] = useState<PositionMode>("percent");

  const logQuery = useQuery({
    queryKey: ["synthetics-log", label, scenario],
    queryFn: () => apiFetch<unknown>(`/api/synthetics/${label}/${scenario}/log`),
    enabled: !!label && !!scenario,
  });

  useEffect(() => {
    if (!logQuery.data) return;
    try {
      const text = JSON.stringify(logQuery.data);
      const result = parseOfficialLog(text);
      if (result.activities.length === 0) {
        setParseError("No activity rows in this log.");
        return;
      }
      setParsed(result);
      setParseError(null);
      const products = Array.from(new Set(result.activities.map((r) => r.product)));
      if (products.length > 0) setProduct(products[0]);
      const ts = Number(result.activities[0].timestamp);
      if (!isNaN(ts)) setSelectedTimestamp(ts);
    } catch (e) {
      setParseError(`Parse failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [logQuery.data]);

  const products = useMemo(
    () => (parsed ? Array.from(new Set(parsed.activities.map((r) => r.product))) : []),
    [parsed]
  );
  const filteredActivities = useMemo(
    () => (parsed ? parsed.activities.filter((r) => r.product === product) : []),
    [parsed, product]
  );
  const timestamps = useMemo(
    () => filteredActivities.map((r) => Number(r.timestamp)),
    [filteredActivities]
  );
  const filteredTrades = useMemo(
    () => (parsed ? parsed.trades.filter((t) => t.symbol === product) : []),
    [parsed, product]
  );
  const filteredBotTrades = useMemo(
    () => (parsed?.botTrades ? parsed.botTrades.filter((t) => t.symbol === product) : []),
    [parsed, product]
  );

  const orderbookSnapshot = useMemo(() => {
    if (!selectedTimestamp || !product) return null;
    const row = filteredActivities.find((r) => Number(r.timestamp) === selectedTimestamp);
    if (!row) return null;
    const bidPrices: number[] = [];
    const bidVolumes: number[] = [];
    const askPrices: number[] = [];
    const askVolumes: number[] = [];
    const bp1 = N(row.bid_price_1), bv1 = N(row.bid_volume_1);
    const bp2 = N(row.bid_price_2), bv2 = N(row.bid_volume_2);
    const bp3 = N(row.bid_price_3), bv3 = N(row.bid_volume_3);
    const ap1 = N(row.ask_price_1), av1 = N(row.ask_volume_1);
    const ap2 = N(row.ask_price_2), av2 = N(row.ask_volume_2);
    const ap3 = N(row.ask_price_3), av3 = N(row.ask_volume_3);
    if (bp1 !== null && bv1 !== null) { bidPrices.push(bp1); bidVolumes.push(bv1); }
    if (bp2 !== null && bv2 !== null) { bidPrices.push(bp2); bidVolumes.push(bv2); }
    if (bp3 !== null && bv3 !== null) { bidPrices.push(bp3); bidVolumes.push(bv3); }
    if (ap1 !== null && av1 !== null) { askPrices.push(ap1); askVolumes.push(av1); }
    if (ap2 !== null && av2 !== null) { askPrices.push(ap2); askVolumes.push(av2); }
    if (ap3 !== null && av3 !== null) { askPrices.push(ap3); askVolumes.push(av3); }
    return {
      round_num: 0,
      day_num: Number(row.day_num),
      timestamp: selectedTimestamp,
      product,
      bid_prices: bidPrices,
      bid_volumes: bidVolumes,
      ask_prices: askPrices,
      ask_volumes: askVolumes,
      mid_price: N(row.mid_price) ?? 0,
    };
  }, [filteredActivities, selectedTimestamp, product]);

  const finalPnl = filteredActivities.length > 0
    ? Number(filteredActivities[filteredActivities.length - 1].pnl)
    : undefined;

  if (logQuery.isLoading) {
    return (
      <div className="page">
        <div className="empty-state">Loading log…</div>
      </div>
    );
  }
  if (logQuery.error || parseError) {
    return (
      <div className="page">
        <div className="page-header">
          <Link to="/synthetics" className="btn btn-ghost" style={{ fontSize: 12 }}>
            ← Back to synthetics
          </Link>
        </div>
        <div style={{ color: "var(--red)", padding: 16 }}>
          {String(logQuery.error || parseError)}
        </div>
      </div>
    );
  }
  if (!parsed) return null;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">
            <Link to="/synthetics" style={{ color: "inherit" }}>Synthetics</Link>
            {" · "}{label}
          </p>
          <h1 className="page-title">{scenario}</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
            <span className="pill pill-completed">parsed</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {parsed.activities.length} activity rows · {parsed.trades.length} trades
            </span>
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
            <span className="stat-value">{timestamps.length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Trades</span>
            <span className="stat-value">{parsed.trades.length}</span>
          </div>
          <Link to="/synthetics" className="btn btn-ghost" style={{ fontSize: 11, padding: "6px 12px" }}>
            ← All scenarios
          </Link>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Navigation</p>
            <p className="panel-title">Timestamp</p>
          </div>
          <div className="toolbar">
            {products.length > 0 && (
              <div className="tabs">
                {products.map((p) => (
                  <button
                    key={p}
                    className={`tab${product === p ? " active" : ""}`}
                    onClick={() => {
                      setProduct(p);
                      const first = parsed.activities.find((r) => r.product === p);
                      if (first) setSelectedTimestamp(Number(first.timestamp));
                    }}
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="panel-body">
          <TimestampSlider
            timestamps={timestamps}
            selectedTimestamp={selectedTimestamp}
            onSelectTimestamp={setSelectedTimestamp}
          />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Market Data</p>
            <p className="panel-title">3-Level Price Depth</p>
          </div>
        </div>
        <div style={{ padding: "8px 0 4px" }}>
          <PriceDepthChart
            rows={filteredActivities}
            ownTrades={filteredTrades}
            botTrades={filteredBotTrades}
            decisionTrace={[]}
            product={product}
            selectedTimestamp={selectedTimestamp}
            onSelectTimestamp={setSelectedTimestamp}
          />
        </div>
      </div>

      {parsed.lambdaSnapshots.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Strategy</p>
              <p className="panel-title">Fair Value (L) vs Market &amp; Our Quotes</p>
            </div>
          </div>
          <div style={{ padding: "8px 0 4px" }}>
            <FairValueChart
              rows={filteredActivities}
              ownTrades={filteredTrades}
              botTrades={filteredBotTrades}
              lambdaSnapshots={parsed.lambdaSnapshots}
              product={product}
              selectedTimestamp={selectedTimestamp}
              onSelectTimestamp={setSelectedTimestamp}
            />
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Market Data</p>
            <p className="panel-title">Volume Depth</p>
          </div>
        </div>
        <div style={{ padding: "4px 0" }}>
          <VolumeChart
            rows={filteredActivities}
            selectedTimestamp={selectedTimestamp}
            onSelectTimestamp={setSelectedTimestamp}
          />
        </div>
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Snapshot</p>
              <p className="panel-title">Order Book</p>
            </div>
          </div>
          <div className="panel-body">
            <OrderBookTable snapshot={orderbookSnapshot} />
          </div>
        </div>
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Overview</p>
              <p className="panel-title">PnL by Product</p>
            </div>
          </div>
          <div className="panel-body">
            <SummaryPnlChart rows={parsed.activities} />
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Inventory</p>
            <p className="panel-title">Position</p>
          </div>
          <div className="tabs" style={{ fontSize: 11 }}>
            <button
              className={`tab${positionMode === "percent" ? " active" : ""}`}
              onClick={() => setPositionMode("percent")}
            >
              % of Limit
            </button>
            <button
              className={`tab${positionMode === "quantity" ? " active" : ""}`}
              onClick={() => setPositionMode("quantity")}
            >
              Net Qty
            </button>
          </div>
        </div>
        <div className="panel-body">
          <PositionOverviewChart rows={parsed.activities} mode={positionMode} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Execution</p>
            <p className="panel-title">Trade History</p>
          </div>
        </div>
        <div className="panel-body-sm">
          <TradeTable trades={parsed.trades} activities={parsed.activities} />
        </div>
      </div>
    </div>
  );
}

function TradeTable({ trades, activities }: { trades: TradeRow[]; activities: ActivityRow[] }) {
  const depthAt = useMemo(() => {
    const m = new Map<string, { bb: number | null; ba: number | null }>();
    for (const r of activities) {
      m.set(`${r.product}:${r.timestamp}`, {
        bb: N(r.bid_price_1),
        ba: N(r.ask_price_1),
      });
    }
    return m;
  }, [activities]);

  if (trades.length === 0) {
    return <div className="empty-state"><span>No trades.</span></div>;
  }
  return (
    <div className="table-wrap">
      <table style={{ fontSize: 11 }}>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Instrument</th>
            <th>Side</th>
            <th>Type</th>
            <th style={{ textAlign: "right" }}>Price</th>
            <th style={{ textAlign: "right" }}>Qty</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => {
            const isBuy = t.buyer === "SUBMISSION";
            const isSell = t.seller === "SUBMISSION";
            const side = isBuy ? "BUY" : isSell ? "SELL" : "MKT";
            const color = isBuy ? "var(--bid, #3fb950)" : isSell ? "var(--ask, #f85149)" : "var(--text-dim)";
            const d = depthAt.get(`${t.symbol}:${t.timestamp}`);
            let fillType = "—";
            if (isBuy) fillType = d && d.ba !== null && t.price >= d.ba ? "Aggressive" : "Passive";
            else if (isSell) fillType = d && d.bb !== null && t.price <= d.bb ? "Aggressive" : "Passive";
            return (
              <tr key={i}>
                <td style={{ fontFamily: "monospace" }}>{t.timestamp}</td>
                <td style={{ fontWeight: 500 }}>{t.symbol}</td>
                <td style={{ color, fontWeight: 600 }}>{side}</td>
                <td style={{ fontSize: 10, color: "var(--text-muted, #8b949e)" }}>{fillType}</td>
                <td style={{ textAlign: "right", fontFamily: "monospace" }}>{t.price}</td>
                <td style={{ textAlign: "right", fontFamily: "monospace" }}>{t.quantity}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
