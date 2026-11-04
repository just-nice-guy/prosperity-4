import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import { ActivityRow, RawPriceRow, TradeRow } from "../../api/types";

type RawOrder = { price: number; quantity: number; symbol: string };
type DecisionEntry = {
  timestamp: number;
  round_num?: number;
  day_num?: number;
  payload: { orders?: Record<string, RawOrder[]> };
};

export type TimelineChartProps = {
  rows: ActivityRow[];
  ownTrades: TradeRow[];
  decisionTrace: DecisionEntry[];
  product: string;
  roundNum: number | null;
  dayNum: number | null;
  selectedTimestamp: number | null;
  onSelectTimestamp: (timestamp: number) => void;
  isFullscreen?: boolean;
  /** Raw CSV prices for overlay verification (optional) */
  rawPrices?: RawPriceRow[];
  /** When true, show all days concatenated with offset x-axis */
  viewAllDays?: boolean;
};

const AXIS_LABEL = { color: "#7d8590", fontSize: 10 } as const;
const SPLIT_LINE = { lineStyle: { color: "rgba(48,54,61,0.5)" } } as const;
const ALPHA = 0.25;

/** Offset timestamps so different days don't overlap on x-axis.
 *  day_num -2 → offset 0, day_num -1 → offset 1_000_000, etc. */
function dayOffsetX(dayNum: number, timestamp: number): number {
  return (dayNum + 2) * 1_000_000 + timestamp;
}

function buildFV(xValues: number[], midPrices: number[]): [number, number][] {
  if (!xValues.length) return [];
  let fv = midPrices[0];
  return xValues.map((x, i) => {
    fv = ALPHA * midPrices[i] + (1 - ALPHA) * fv;
    return [x, fv];
  });
}

function fillSize(qty: number, maxQty: number) {
  return Math.sqrt(Math.abs(qty) / maxQty) * 8 + 4;
}

function buildOption(
  rows: ActivityRow[],
  ownTrades: TradeRow[],
  decisionTrace: DecisionEntry[],
  product: string,
  roundNum: number | null,
  dayNum: number | null,
  rawPrices?: RawPriceRow[],
  viewAllDays?: boolean,
  ignoreNA?: boolean,
): echarts.EChartsOption {
  // Compute x-value for each activity row
  const xOf = (r: ActivityRow) =>
    viewAllDays
      ? dayOffsetX(Number(r.day_num), Number(r.timestamp))
      : Number(r.timestamp);

  const midData = rows.map((r) => {
    const v = Number(r.mid_price);
    return [xOf(r), (ignoreNA && (v <= 0 || isNaN(v))) ? null : v];
  });
  const bidData = rows.map((r) => {
    const v = Number(r.bid_price_1);
    return [xOf(r), (ignoreNA && (v <= 0 || isNaN(v))) ? null : v];
  });
  const askData = rows.map((r) => {
    const v = Number(r.ask_price_1);
    return [xOf(r), (ignoreNA && (v <= 0 || isNaN(v))) ? null : v];
  });
  const fvData = buildFV(
    rows.map(xOf),
    rows.map((r) => Number(r.mid_price)),
  );

  // Compute explicit Y-axis bounds from price data so the chart doesn't
  // collapse to a flat line when there are many data points or scatter
  // outliers.  Padding 1% of the range on each side.
  const allPriceVals = [
    ...midData.map((d) => d[1] as number),
    ...bidData.map((d) => d[1] as number).filter((v) => v != null && v > 0),
    ...askData.map((d) => d[1] as number).filter((v) => v != null && v > 0),
  ];
  const priceYMin = allPriceVals.length > 0 ? Math.min(...allPriceVals) : 0;
  const priceYMax = allPriceVals.length > 0 ? Math.max(...allPriceVals) : 1;
  const priceYPad = Math.max(1, (priceYMax - priceYMin) * 0.02);

  const pnlData: [number, number][] = [];
  const posData: [number, number][] = [];
  for (const r of rows) {
    pnlData.push([xOf(r), Number(r.pnl)]);
    posData.push([xOf(r), Number(r.position)]);
  }

  const bidOrderDots: [number, number][] = [];
  const askOrderDots: [number, number][] = [];
  for (const entry of decisionTrace) {
    // Filter to current day — entries from other days share the same timestamp range
    if (!viewAllDays) {
      if (roundNum !== null && entry.round_num !== undefined && entry.round_num !== roundNum) continue;
      if (dayNum !== null && entry.day_num !== undefined && entry.day_num !== dayNum) continue;
    }
    const entryX = viewAllDays && entry.day_num !== undefined
      ? dayOffsetX(entry.day_num, entry.timestamp)
      : entry.timestamp;
    for (const o of entry.payload.orders?.[product] ?? []) {
      if (o.quantity > 0) bidOrderDots.push([entryX, o.price]);
      else askOrderDots.push([entryX, o.price]);
    }
  }

  // Build raw price overlay data (for verification against raw CSV)
  const rawBidData: [number, number][] = [];
  const rawAskData: [number, number][] = [];
  if (rawPrices && rawPrices.length > 0) {
    for (const rp of rawPrices) {
      const rpX = viewAllDays ? dayOffsetX(rp.day_num, rp.timestamp) : rp.timestamp;
      if (rp.best_bid !== null) rawBidData.push([rpX, rp.best_bid]);
      if (rp.best_ask !== null) rawAskData.push([rpX, rp.best_ask]);
    }
  }

  // Map x-value → depth for passive/aggressive classification
  const depthAt = new Map(
    rows.map((r) => [xOf(r), { bb: Number(r.bid_price_1), ba: Number(r.ask_price_1) }])
  );
  const maxQty = Math.max(1, ...ownTrades.map((t) => t.quantity));
  const szFn = (val: [number, number, number]) => fillSize(val[2], maxQty);

  const passiveBuy: [number, number, number][] = [];
  const aggressiveBuy: [number, number, number][] = [];
  const passiveSell: [number, number, number][] = [];
  const aggressiveSell: [number, number, number][] = [];

  for (const t of ownTrades) {
    const tX = viewAllDays ? dayOffsetX(t.day_num, t.timestamp) : t.timestamp;
    const d = depthAt.get(tX);
    const row: [number, number, number] = [tX, t.price, t.quantity];
    if (t.buyer === "SUBMISSION") {
      (d && t.price >= d.ba ? aggressiveBuy : passiveBuy).push(row);
    } else {
      (d && t.price <= d.bb ? aggressiveSell : passiveSell).push(row);
    }
  }

  // X-axis label formatter for all-days mode
  const allDaysLabelFormatter = (val: number) => {
    const dayIdx = Math.floor(val / 1_000_000);
    const ts = val % 1_000_000;
    return `D${dayIdx - 2} t${ts}`;
  };

  return {
    animation: false,
    progressive: 0,
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", link: [{ xAxisIndex: "all" }] },
      confine: true,
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    legend: {
      data: [
        "Bid", "Mid", "Ask", "Fair Value",
        "Order bid", "Order ask",
        "PnL", "Position",
        "Passive buy", "Agg buy", "Passive sell", "Agg sell",
        ...(rawBidData.length > 0 ? ["Raw Bid", "Raw Ask"] : []),
      ],
      textStyle: { color: "#7d8590", fontSize: 10 },
      left: "center",
      top: 4,
      itemWidth: 12,
      itemHeight: 8,
    },
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1, 2], filterMode: "filter" },
      {
        type: "slider",
        xAxisIndex: [0, 1, 2],
        height: 18,
        bottom: 2,
        borderColor: "transparent",
        backgroundColor: "rgba(255,255,255,0.02)",
        fillerColor: "rgba(20,184,166,0.08)",
        handleStyle: { color: "#14b8a6" },
        textStyle: { color: "#7d8590", fontSize: 9 },
        filterMode: "filter",
      },
    ],

    // 3 stacked grids: price (top), pnl (mid), position (bottom)
    grid: [
      { left: 62, right: 62, top: 40, bottom: "46%" },    // price
      { left: 62, right: 62, top: "58%", bottom: "26%" },  // pnl
      { left: 62, right: 62, top: "78%", bottom: 36 },     // position
    ],

    xAxis: [
      // price x-axis (hidden labels — shared via dataZoom)
      {
        type: "value", gridIndex: 0, min: "dataMin", max: "dataMax",
        axisLabel: { show: false }, axisTick: { show: false },
        splitLine: SPLIT_LINE,
      },
      // pnl x-axis (hidden)
      {
        type: "value", gridIndex: 1, min: "dataMin", max: "dataMax",
        axisLabel: { show: false }, axisTick: { show: false },
        splitLine: SPLIT_LINE,
      },
      // position x-axis (shows labels)
      {
        type: "value", gridIndex: 2, min: "dataMin", max: "dataMax",
        axisLabel: viewAllDays
          ? { ...AXIS_LABEL, formatter: allDaysLabelFormatter }
          : AXIS_LABEL,
        splitLine: SPLIT_LINE,
      },
    ],

    yAxis: [
      // 0: price — explicit min/max to prevent flat-line on large datasets
      {
        type: "value", gridIndex: 0, name: "price", scale: true,
        min: priceYMin - priceYPad, max: priceYMax + priceYPad,
        nameTextStyle: { color: "#7d8590", fontSize: 10 },
        axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE,
      },
      // 1: pnl
      {
        type: "value", gridIndex: 1, name: "PnL", scale: true,
        nameTextStyle: { color: "#f97316", fontSize: 10 },
        axisLabel: { ...AXIS_LABEL, color: "#f97316" },
        splitLine: { lineStyle: { color: "rgba(48,54,61,0.3)" } },
      },
      // 2: position
      {
        type: "value", gridIndex: 2, name: "position", scale: true,
        nameTextStyle: { color: "#a78bfa", fontSize: 10 },
        axisLabel: { ...AXIS_LABEL, color: "#a78bfa" },
        splitLine: { lineStyle: { color: "rgba(48,54,61,0.3)" } },
      },
    ],

    series: [
      // ── Price panel (xAxisIndex: 0, yAxisIndex: 0) ──
      {
        type: "line", name: "Bid", xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, data: bidData, sampling: "lttb",
        connectNulls: !!ignoreNA,
        lineStyle: { width: 1.5, color: "rgba(63,185,80,0.85)",
                     ...(ignoreNA ? { type: "dashed" } : {}) }, z: 1,
      },
      {
        type: "line", name: "Ask", xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, data: askData, sampling: "lttb",
        connectNulls: !!ignoreNA,
        lineStyle: { width: 1.5, color: "rgba(248,81,73,0.85)",
                     ...(ignoreNA ? { type: "dashed" } : {}) }, z: 1,
      },
      {
        type: "line", name: "Mid", xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, data: midData, sampling: "lttb",
        connectNulls: !!ignoreNA,
        lineStyle: { width: 2, color: "#14b8a6" }, z: 3,
      },
      {
        type: "line", name: "Fair Value", xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, data: fvData, sampling: "lttb",
        lineStyle: { width: 1.5, color: "#facc15", type: "dotted" }, z: 4,
      },
      {
        type: "scatter", name: "Order bid", xAxisIndex: 0, yAxisIndex: 0,
        data: bidOrderDots, symbolSize: 2, large: true, largeThreshold: 2000,
        itemStyle: { color: "rgba(96,165,250,0.6)" }, z: 2,
      },
      {
        type: "scatter", name: "Order ask", xAxisIndex: 0, yAxisIndex: 0,
        data: askOrderDots, symbolSize: 2, large: true, largeThreshold: 2000,
        itemStyle: { color: "rgba(251,146,60,0.6)" }, z: 2,
      },
      {
        type: "scatter", name: "Passive buy", xAxisIndex: 0, yAxisIndex: 0,
        symbol: "circle", data: passiveBuy, symbolSize: szFn,
        itemStyle: { color: "#3fb950", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 }, z: 6,
      },
      {
        type: "scatter", name: "Agg buy", xAxisIndex: 0, yAxisIndex: 0,
        symbol: "triangle", data: aggressiveBuy, symbolSize: szFn,
        itemStyle: { color: "#3fb950", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 }, z: 6,
      },
      {
        type: "scatter", name: "Passive sell", xAxisIndex: 0, yAxisIndex: 0,
        symbol: "circle", data: passiveSell, symbolSize: szFn,
        itemStyle: { color: "#f85149", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 }, z: 6,
      },
      {
        type: "scatter", name: "Agg sell", xAxisIndex: 0, yAxisIndex: 0,
        symbol: "triangle", symbolRotate: 180, data: aggressiveSell, symbolSize: szFn,
        itemStyle: { color: "#f85149", borderColor: "rgba(255,255,255,0.55)", borderWidth: 1 }, z: 6,
      },

      // ── Raw CSV overlay (verification) ──
      ...(rawBidData.length > 0 ? [
        {
          type: "line" as const, name: "Raw Bid", xAxisIndex: 0, yAxisIndex: 0,
          showSymbol: false, data: rawBidData,
          lineStyle: { width: 2, color: "#22d3ee", type: "dotted" as const }, z: 0,
        },
        {
          type: "line" as const, name: "Raw Ask", xAxisIndex: 0, yAxisIndex: 0,
          showSymbol: false, data: rawAskData,
          lineStyle: { width: 2, color: "#fb923c", type: "dotted" as const }, z: 0,
        },
      ] : []),

      // ── PnL panel (xAxisIndex: 1, yAxisIndex: 1) ──
      {
        type: "line", name: "PnL", xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, data: pnlData,
        lineStyle: { width: 2, color: "#f97316" }, z: 2,
      },

      // ── Position panel (xAxisIndex: 2, yAxisIndex: 2) ──
      {
        type: "line", name: "Position", xAxisIndex: 2, yAxisIndex: 2,
        step: "end", showSymbol: false, data: posData,
        lineStyle: { width: 2, color: "#a78bfa" }, z: 2,
      },
    ],
  };
}

export function TimelineChart({
  rows,
  ownTrades,
  decisionTrace,
  product,
  roundNum,
  dayNum,
  selectedTimestamp,
  onSelectTimestamp,
  isFullscreen = false,
  rawPrices,
  viewAllDays = false,
}: TimelineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const callbackRef = useRef(onSelectTimestamp);
  callbackRef.current = onSelectTimestamp;

  const [ignoreNA, setIgnoreNA] = useState(false);

  const option = useMemo(
    () => buildOption(rows, ownTrades, decisionTrace, product, roundNum, dayNum, rawPrices, viewAllDays, ignoreNA),
    [rows, ownTrades, decisionTrace, product, roundNum, dayNum, rawPrices, viewAllDays, ignoreNA],
  );

  // Create / dispose the ECharts instance directly (StrictMode safe)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Dispose any leftover instance on this DOM node
    const existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    const chart = echarts.init(el, undefined, { renderer: "svg" });
    chartRef.current = chart;

    chart.setOption(option, true);

    chart.on("click", (params) => {
      const val = (params as { value?: unknown[] }).value;
      if (Array.isArray(val) && val.length >= 2) {
        startTransition(() => callbackRef.current(Number(val[0])));
      }
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push option updates without recreating the instance
  useEffect(() => {
    if (chartRef.current && !chartRef.current.isDisposed()) {
      chartRef.current.setOption(option, true);
    }
  }, [option]);

  // Resize when fullscreen toggles
  useEffect(() => {
    if (chartRef.current && !chartRef.current.isDisposed()) {
      const id = setTimeout(() => chartRef.current?.resize(), 50);
      return () => clearTimeout(id);
    }
  }, [isFullscreen]);

  return (
    <div style={{ position: "relative", height: isFullscreen ? "calc(100vh - 52px)" : 620, width: "100%" }}>
      <div
        ref={containerRef}
        style={{ height: "100%", width: "100%" }}
      />
      <button
        onClick={() => setIgnoreNA((v) => !v)}
        title={ignoreNA ? "Showing: NA values hidden, gaps connected with dashed lines" : "Showing: all data including NA/zero values"}
        style={{
          position: "absolute",
          top: 6,
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
