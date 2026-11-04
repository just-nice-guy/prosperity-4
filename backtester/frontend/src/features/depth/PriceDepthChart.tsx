import { useState } from "react";
import ReactECharts from "echarts-for-react";
import { ActivityRow, TradeRow } from "../../api/types";

const N = (v: string | undefined | null) => (v && v !== "" && v !== "None" ? Number(v) : null);

type Props = {
  rows: ActivityRow[];
  ownTrades: TradeRow[];
  botTrades?: TradeRow[];
  decisionTrace: Array<Record<string, unknown>>;
  product: string;
  selectedTimestamp: number | null;
  onSelectTimestamp: (t: number) => void;
};

export function PriceDepthChart({
  rows,
  ownTrades,
  botTrades = [],
  decisionTrace,
  product,
  selectedTimestamp,
  onSelectTimestamp,
}: Props) {
  const [ignoreNA, setIgnoreNA] = useState(false);
  const timestamps = rows.map((r) => Number(r.timestamp));

  // Price series - 3 levels of bid/ask
  // Always drop invalid values (<=0, NaN) to null so ECharts auto-scales Y
  // correctly when zooming. `ignoreNA` only controls whether lines connect
  // across gaps (connectNulls) — not axis scaling.
  const clean = (v: number | null) =>
    v === null || v <= 0 || isNaN(v) ? null : v;
  const bid1 = rows.map((r) => clean(N(r.bid_price_1)));
  const bid2 = rows.map((r) => clean(N(r.bid_price_2)));
  const bid3 = rows.map((r) => clean(N(r.bid_price_3)));
  const mid = rows.map((r) => clean(N(r.mid_price)));
  const ask1 = rows.map((r) => clean(N(r.ask_price_1)));
  const ask2 = rows.map((r) => clean(N(r.ask_price_2)));
  const ask3 = rows.map((r) => clean(N(r.ask_price_3)));

  // Only show level 3 series if they have actual data
  const hasBid3 = bid3.some((v) => v !== null);
  const hasAsk3 = ask3.some((v) => v !== null);

  // Map timestamp → category index (needed for scatter on category axis)
  const tsToIdx = new Map(timestamps.map((t, i) => [t, i]));

  // Build bid/ask lookup by timestamp for passive/aggressive classification
  const depthAt = new Map<number, { bb: number | null; ba: number | null }>();
  for (const r of rows) {
    depthAt.set(Number(r.timestamp), {
      bb: N(r.bid_price_1),
      ba: N(r.ask_price_1),
    });
  }

  // Order quotes from decision trace
  const bidQuotes: [number, number][] = [];
  const askQuotes: [number, number][] = [];
  for (const entry of decisionTrace) {
    const ts = Number(entry.timestamp);
    const idx = tsToIdx.get(ts);
    if (idx === undefined) continue;
    const orders = (entry.payload as Record<string, unknown>)?.orders as
      | Record<string, Array<{ price: number; quantity: number }>>
      | undefined;
    if (!orders?.[product]) continue;
    for (const o of orders[product]) {
      if (o.quantity > 0) bidQuotes.push([idx, o.price]);
      else if (o.quantity < 0) askQuotes.push([idx, o.price]);
    }
  }

  // Classify fills as passive or aggressive
  // Uses category index for x-position so scatter points render correctly
  const passiveBuy: [number, number, number][] = [];
  const aggressiveBuy: [number, number, number][] = [];
  const passiveSell: [number, number, number][] = [];
  const aggressiveSell: [number, number, number][] = [];

  for (const t of ownTrades) {
    if (t.symbol !== product) continue;
    const idx = tsToIdx.get(t.timestamp);
    if (idx === undefined) continue;
    const d = depthAt.get(t.timestamp);
    const row: [number, number, number] = [idx, t.price, t.quantity];
    if (t.buyer === "SUBMISSION") {
      (d && d.ba !== null && t.price >= d.ba ? aggressiveBuy : passiveBuy).push(row);
    } else {
      (d && d.bb !== null && t.price <= d.bb ? aggressiveSell : passiveSell).push(row);
    }
  }

  // Bot trades scatter data
  const botDots: [number, number, number][] = [];
  for (const t of botTrades) {
    if (t.symbol !== product) continue;
    const idx = tsToIdx.get(t.timestamp);
    if (idx !== undefined) {
      botDots.push([idx, t.price, t.quantity]);
    }
  }

  const fillSize = (q: number) => Math.max(6, Math.min(q * 2, 18));

  // Mark line for selected timestamp (use category index)
  const selectedIdx = selectedTimestamp !== null ? tsToIdx.get(selectedTimestamp) : undefined;
  const markLine = selectedIdx !== undefined
    ? {
        silent: true,
        symbol: "none",
        lineStyle: { color: "rgba(255,255,255,0.15)", type: "solid" as const, width: 1 },
        data: [{ xAxis: selectedIdx }],
      }
    : undefined;

  const legendData = [
    "Bid 1", "Bid 2", ...(hasBid3 ? ["Bid 3"] : []),
    "Mid",
    "Ask 1", "Ask 2", ...(hasAsk3 ? ["Ask 3"] : []),
    "Bid Quote", "Ask Quote",
    ...(botDots.length > 0 ? ["Bot Trade"] : []),
    "Passive Buy", "Agg Buy", "Passive Sell", "Agg Sell",
  ];

  const option = {
    animation: false,
    progressive: 0,
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 20, bottom: 60 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(13,17,23,0.95)",
      borderColor: "rgba(48,54,61,0.9)",
      textStyle: { color: "#e6edf3", fontSize: 11 },
      axisPointer: { type: "cross" as const, label: { backgroundColor: "#161b22" } },
    },
    legend: {
      data: legendData,
      bottom: 0,
      textStyle: { color: "#7d8590", fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    dataZoom: [
      {
        type: "slider" as const,
        bottom: 22,
        height: 18,
        borderColor: "transparent",
        backgroundColor: "rgba(255,255,255,0.03)",
        fillerColor: "rgba(20,184,166,0.08)",
        handleStyle: { color: "#14b8a6", borderColor: "#14b8a6" },
        textStyle: { color: "#484f58", fontSize: 10 },
        filterMode: "filter" as const,
      },
      { type: "inside" as const, filterMode: "filter" as const },
    ],
    xAxis: {
      type: "category" as const,
      data: timestamps,
      axisLine: { lineStyle: { color: "rgba(48,54,61,0.5)" } },
      axisLabel: { color: "#484f58", fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value" as const,
      scale: true,
      axisLine: { show: false },
      axisLabel: { color: "#484f58", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(48,54,61,0.3)" } },
    },
    series: [
      // Bid levels
      {
        name: "Bid 1", type: "line", data: bid1, symbol: "none",
        connectNulls: ignoreNA,
        lineStyle: { color: "rgba(63,185,80,1)", width: 1.5,
                     ...(ignoreNA ? { type: "dashed" as const } : {}) },
        itemStyle: { color: "rgba(63,185,80,1)" },
        markLine,
      },
      {
        name: "Bid 2", type: "line", data: bid2, symbol: "none",
        connectNulls: ignoreNA,
        lineStyle: { color: "rgba(63,185,80,0.45)", width: 1, type: "dashed" },
        itemStyle: { color: "rgba(63,185,80,0.45)" },
      },
      ...(hasBid3 ? [{
        name: "Bid 3", type: "line" as const, data: bid3, symbol: "none" as const,
        lineStyle: { color: "rgba(63,185,80,0.2)", width: 1, type: "dotted" as const },
        itemStyle: { color: "rgba(63,185,80,0.2)" },
      }] : []),
      // Mid price
      {
        name: "Mid", type: "line", data: mid, symbol: "none",
        connectNulls: ignoreNA,
        lineStyle: { color: "rgba(125,133,144,0.7)", width: 1.5, type: "dashed" },
        itemStyle: { color: "rgba(125,133,144,0.7)" },
      },
      // Ask levels
      {
        name: "Ask 1", type: "line", data: ask1, symbol: "none",
        connectNulls: ignoreNA,
        lineStyle: { color: "rgba(248,81,73,1)", width: 1.5,
                     ...(ignoreNA ? { type: "dashed" as const } : {}) },
        itemStyle: { color: "rgba(248,81,73,1)" },
      },
      {
        name: "Ask 2", type: "line", data: ask2, symbol: "none",
        connectNulls: ignoreNA,
        lineStyle: { color: "rgba(248,81,73,0.45)", width: 1, type: "dashed" },
        itemStyle: { color: "rgba(248,81,73,0.45)" },
      },
      ...(hasAsk3 ? [{
        name: "Ask 3", type: "line" as const, data: ask3, symbol: "none" as const,
        lineStyle: { color: "rgba(248,81,73,0.2)", width: 1, type: "dotted" as const },
        itemStyle: { color: "rgba(248,81,73,0.2)" },
      }] : []),
      // Order quotes
      {
        name: "Bid Quote", type: "scatter", data: bidQuotes,
        symbol: "circle", symbolSize: 5,
        itemStyle: { color: "rgba(88,166,255,0.7)" }, z: 10,
      },
      {
        name: "Ask Quote", type: "scatter", data: askQuotes,
        symbol: "circle", symbolSize: 5,
        itemStyle: { color: "rgba(249,115,22,0.7)" }, z: 10,
      },
      // Bot-to-bot trades — gray diamonds
      ...(botDots.length > 0 ? [{
        name: "Bot Trade" as const, type: "scatter" as const,
        data: botDots.map(([idx, p, q]) => ({ value: [idx, p], symbolSize: fillSize(q) })),
        symbol: "diamond" as const,
        itemStyle: { color: "rgba(249,115,22,0.6)", borderColor: "rgba(255,180,100,0.5)", borderWidth: 1 },
        z: 5,
      }] : []),
      // Passive buy fills — green circles
      {
        name: "Passive Buy", type: "scatter",
        data: passiveBuy.map(([idx, p, q]) => ({ value: [idx, p], symbolSize: fillSize(q) })),
        symbol: "circle",
        itemStyle: { color: "#3fb950", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 },
        z: 20,
      },
      // Aggressive buy fills — green triangles
      {
        name: "Agg Buy", type: "scatter",
        data: aggressiveBuy.map(([idx, p, q]) => ({ value: [idx, p], symbolSize: fillSize(q) })),
        symbol: "triangle",
        itemStyle: { color: "#3fb950", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 },
        z: 20,
      },
      // Passive sell fills — red circles
      {
        name: "Passive Sell", type: "scatter",
        data: passiveSell.map(([idx, p, q]) => ({ value: [idx, p], symbolSize: fillSize(q) })),
        symbol: "circle",
        itemStyle: { color: "#f85149", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 },
        z: 20,
      },
      // Aggressive sell fills — red inverted triangles
      {
        name: "Agg Sell", type: "scatter",
        data: aggressiveSell.map(([idx, p, q]) => ({ value: [idx, p], symbolSize: fillSize(q) })),
        symbol: "triangle", symbolRotate: 180,
        itemStyle: { color: "#f85149", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 },
        z: 20,
      },
    ],
  };

  const onEvents = {
    click: (params: { componentType: string; dataIndex?: number; value?: unknown }) => {
      if (params.componentType === "series" && params.dataIndex !== undefined) {
        const ts = timestamps[params.dataIndex];
        if (ts !== undefined) {
          onSelectTimestamp(ts);
          return;
        }
      }
      // Scatter fills use category index as x-value
      if (params.componentType === "series" && Array.isArray(params.value)) {
        const idx = Number(params.value[0]);
        const ts = timestamps[idx];
        if (ts !== undefined) onSelectTimestamp(ts);
      }
    },
  };

  return (
    <div style={{ position: "relative" }}>
      <ReactECharts
        option={option}
        style={{ height: 400 }}
        onEvents={onEvents}
        notMerge
      />
      <button
        onClick={() => setIgnoreNA((v) => !v)}
        title={ignoreNA
          ? "NA hidden: gaps connected with dashed lines"
          : "Click to hide NA/zero values and connect gaps"}
        style={{
          position: "absolute",
          top: 4,
          right: 8,
          zIndex: 10,
          padding: "3px 8px",
          fontSize: 11,
          fontFamily: "monospace",
          cursor: "pointer",
          border: "1px solid rgba(100,100,120,0.4)",
          borderRadius: 4,
          background: ignoreNA ? "rgba(20,184,166,0.25)" : "rgba(30,30,40,0.6)",
          color: ignoreNA ? "#14b8a6" : "#7d8590",
        }}
      >
        {ignoreNA ? "NA hidden" : "Ignore NA"}
      </button>
    </div>
  );
}
