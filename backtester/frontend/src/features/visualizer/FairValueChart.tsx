import { useState } from "react";
import ReactECharts from "echarts-for-react";
import { ActivityRow, TradeRow } from "../../api/types";
import { LambdaSnapshot } from "./parseOfficialLog";

const N = (v: string | undefined | null): number | null =>
  v && v !== "" && v !== "None" ? Number(v) : null;

type Props = {
  rows: ActivityRow[];
  ownTrades: TradeRow[];
  botTrades?: TradeRow[];
  lambdaSnapshots: LambdaSnapshot[];
  product: string;
  selectedTimestamp: number | null;
  onSelectTimestamp: (t: number) => void;
};

/**
 * Fair-value comparison chart: shows our internal L (Holt-filtered fair value)
 * vs the visible market structure (bid_1/2, ask_1/2, mid) and overlays our
 * own trades + the quote levels we emitted at each tick.
 */
export function FairValueChart({
  rows,
  ownTrades,
  botTrades = [],
  lambdaSnapshots,
  product,
  selectedTimestamp,
  onSelectTimestamp,
}: Props) {
  const [ignoreNA, setIgnoreNA] = useState(false);

  // Always drop invalid values (<=0, NaN) to null so ECharts auto-scales Y
  // correctly when zooming. `ignoreNA` only controls whether lines connect
  // across gaps (connectNulls) — not axis scaling.
  const clean = (v: number | null): number | null =>
    v === null || v <= 0 || isNaN(v) ? null : v;

  const xs = rows.map((r) => Number(r.timestamp));
  const bid1 = rows.map((r) => [Number(r.timestamp), clean(N(r.bid_price_1))]);
  const bid2 = rows.map((r) => [Number(r.timestamp), clean(N(r.bid_price_2))]);
  const ask1 = rows.map((r) => [Number(r.timestamp), clean(N(r.ask_price_1))]);
  const ask2 = rows.map((r) => [Number(r.timestamp), clean(N(r.ask_price_2))]);
  const mid = rows.map((r) => [Number(r.timestamp), clean(N(r.mid_price))]);

  // Per-timestamp best bid/ask lookup, for passive vs aggressive classification
  const depthAt = new Map<number, { bb: number | null; ba: number | null }>();
  for (const r of rows) {
    depthAt.set(Number(r.timestamp), {
      bb: N(r.bid_price_1),
      ba: N(r.ask_price_1),
    });
  }

  // L (our fair value) from lambda snapshots, by timestamp
  const fvData: [number, number][] = lambdaSnapshots
    .filter((s) => s.L !== null)
    .map((s) => [s.timestamp, s.L as number]);

  // B (drift) — secondary axis, small values ±0.1 vs prices ~12000
  const driftData: [number, number][] = lambdaSnapshots
    .filter((s) => s.B !== null)
    .map((s) => [s.timestamp, s.B as number]);

  // Our quote levels per tick — flatten into scatter points
  const quoteBids: [number, number][] = [];
  const quoteAsks: [number, number][] = [];
  for (const s of lambdaSnapshots) {
    for (const q of s.bidQuotes) quoteBids.push([s.timestamp, q]);
    for (const q of s.askQuotes) quoteAsks.push([s.timestamp, q]);
  }

  // Own trades — keep only PASSIVE fills (resting limit orders that got hit).
  // Buy is passive when our price < best_ask at that ts (we sat on the bid).
  // Sell is passive when our price > best_bid at that ts (we sat on the ask).
  const ownBuys: [number, number, number][] = [];
  const ownSells: [number, number, number][] = [];
  for (const t of ownTrades) {
    if (t.symbol !== product) continue;
    const d = depthAt.get(t.timestamp);
    if (t.buyer === "SUBMISSION") {
      const passive = !d || d.ba === null || t.price < d.ba;
      if (passive) ownBuys.push([t.timestamp, t.price, t.quantity]);
    } else if (t.seller === "SUBMISSION") {
      const passive = !d || d.bb === null || t.price > d.bb;
      if (passive) ownSells.push([t.timestamp, t.price, t.quantity]);
    }
  }

  // Bot-to-bot trades
  const botDots: [number, number, number][] = [];
  for (const t of botTrades) {
    if (t.symbol !== product) continue;
    botDots.push([t.timestamp, t.price, t.quantity]);
  }

  const fillSize = (q: number): number => Math.max(6, Math.min(q * 2, 18));

  // Mark line for selected timestamp
  const markLine = selectedTimestamp !== null
    ? {
        silent: true,
        symbol: "none",
        lineStyle: { color: "rgba(255,255,255,0.15)", type: "solid" as const, width: 1 },
        data: [{ xAxis: selectedTimestamp }],
      }
    : undefined;

  const option = {
    animation: false,
    progressive: 0,
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 28, bottom: 60 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(13,17,23,0.95)",
      borderColor: "rgba(48,54,61,0.9)",
      textStyle: { color: "#e6edf3", fontSize: 11 },
      axisPointer: { type: "cross" as const, label: { backgroundColor: "#161b22" } },
    },
    legend: {
      data: ["Bid 1", "Bid 2", "Mid", "Ask 1", "Ask 2",
             "Fair Value (L)", "Drift (B)", "Our Bid Quote", "Our Ask Quote",
             "Passive Buy", "Passive Sell", "Bot Trade"],
      top: 4,
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
      type: "value" as const,
      axisLine: { lineStyle: { color: "rgba(48,54,61,0.5)" } },
      axisLabel: { color: "#484f58", fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value" as const,
        scale: true,
        axisLine: { show: false },
        axisLabel: { color: "#484f58", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(48,54,61,0.3)" } },
      },
      {
        type: "value" as const,
        scale: true,
        axisLine: { show: false },
        axisLabel: { color: "#f97316", fontSize: 9, formatter: (v: number) => v.toFixed(2) },
        splitLine: { show: false },
        position: "right" as const,
      },
    ],
    series: [
      // Market book lines
      {
        name: "Bid 1", type: "line" as const, data: bid1, symbol: "none" as const,
        connectNulls: ignoreNA, sampling: "lttb" as const,
        lineStyle: { color: "rgba(63,185,80,1)", width: 1.5,
                     ...(ignoreNA ? { type: "dashed" as const } : {}) },
        markLine,
      },
      {
        name: "Bid 2", type: "line" as const, data: bid2, symbol: "none" as const,
        connectNulls: ignoreNA, sampling: "lttb" as const,
        lineStyle: { color: "rgba(63,185,80,0.45)", width: 1, type: "dashed" as const },
      },
      {
        name: "Mid", type: "line" as const, data: mid, symbol: "none" as const,
        connectNulls: ignoreNA, sampling: "lttb" as const,
        lineStyle: { color: "rgba(125,133,144,0.6)", width: 1, type: "dashed" as const },
      },
      {
        name: "Ask 1", type: "line" as const, data: ask1, symbol: "none" as const,
        connectNulls: ignoreNA, sampling: "lttb" as const,
        lineStyle: { color: "rgba(248,81,73,1)", width: 1.5,
                     ...(ignoreNA ? { type: "dashed" as const } : {}) },
      },
      {
        name: "Ask 2", type: "line" as const, data: ask2, symbol: "none" as const,
        connectNulls: ignoreNA, sampling: "lttb" as const,
        lineStyle: { color: "rgba(248,81,73,0.45)", width: 1, type: "dashed" as const },
      },
      // Our fair value (the star of this chart)
      {
        name: "Fair Value (L)", type: "line" as const, data: fvData,
        symbol: "none" as const, sampling: "lttb" as const,
        lineStyle: { color: "#facc15", width: 2.5 },
        z: 5,
      },
      // Drift (B) on secondary axis — shows regime detection
      ...(driftData.length > 0 ? [{
        name: "Drift (B)" as const, type: "line" as const, data: driftData,
        symbol: "none" as const, sampling: "lttb" as const,
        yAxisIndex: 1,
        lineStyle: { color: "#f97316", width: 1.5 },
        areaStyle: {
          color: {
            type: "linear" as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(249,115,22,0.15)" },
              { offset: 0.5, color: "rgba(249,115,22,0)" },
              { offset: 1, color: "rgba(249,115,22,0.15)" },
            ],
          },
        },
        z: 4,
      }] : []),
      // Our quote levels per tick (small dots)
      {
        name: "Our Bid Quote", type: "scatter" as const, data: quoteBids,
        symbol: "circle", symbolSize: 3, large: true, largeThreshold: 2000,
        itemStyle: { color: "rgba(96,165,250,0.45)" }, z: 6,
      },
      {
        name: "Our Ask Quote", type: "scatter" as const, data: quoteAsks,
        symbol: "circle", symbolSize: 3, large: true, largeThreshold: 2000,
        itemStyle: { color: "rgba(251,146,60,0.45)" }, z: 6,
      },
      // Bot trades (orange diamonds, low z)
      ...(botDots.length > 0 ? [{
        name: "Bot Trade" as const, type: "scatter" as const,
        data: botDots.map(([ts, p, q]) => ({ value: [ts, p], symbolSize: fillSize(q) })),
        symbol: "diamond" as const,
        itemStyle: { color: "rgba(249,115,22,0.55)", borderColor: "rgba(255,180,100,0.5)", borderWidth: 1 },
        z: 7,
      }] : []),
      // Our passive buy fills
      {
        name: "Passive Buy" as const, type: "scatter" as const,
        data: ownBuys.map(([ts, p, q]) => ({ value: [ts, p], symbolSize: fillSize(q) })),
        symbol: "circle" as const,
        itemStyle: { color: "#3fb950", borderColor: "rgba(255,255,255,0.6)", borderWidth: 1 },
        z: 20,
      },
      // Our passive sell fills
      {
        name: "Passive Sell" as const, type: "scatter" as const,
        data: ownSells.map(([ts, p, q]) => ({ value: [ts, p], symbolSize: fillSize(q) })),
        symbol: "circle" as const,
        itemStyle: { color: "#f85149", borderColor: "rgba(255,255,255,0.6)", borderWidth: 1 },
        z: 20,
      },
    ],
  };

  const onEvents = {
    click: (params: { value?: unknown }) => {
      if (Array.isArray(params.value) && params.value.length >= 2) {
        const ts = Number(params.value[0]);
        if (!isNaN(ts)) onSelectTimestamp(ts);
      }
    },
  };

  return (
    <div style={{ position: "relative" }}>
      <ReactECharts
        option={option}
        style={{ height: 460 }}
        onEvents={onEvents}
        notMerge
      />
      <button
        onClick={() => setIgnoreNA((v) => !v)}
        title={ignoreNA
          ? "NA hidden: gaps connected with dashed lines"
          : "Click to hide NA/zero values and connect gaps"}
        style={{
          position: "absolute", top: 4, right: 8, zIndex: 10,
          padding: "3px 8px", fontSize: 11, fontFamily: "monospace",
          cursor: "pointer", border: "1px solid rgba(100,100,120,0.4)",
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
