import ReactECharts from "echarts-for-react";
import { ActivityRow } from "../../api/types";

const COLORS = ["#14b8a6", "#f97316", "#bc8cff", "#58a6ff", "#f85149", "#3fb950"];

type Props = {
  rows: ActivityRow[];
};

export function SummaryPnlChart({ rows }: Props) {
  // Group by product and compute per-product + total PnL
  const products = Array.from(new Set(rows.map((r) => r.product)));
  const timestamps = Array.from(new Set(rows.map((r) => Number(r.timestamp)))).sort((a, b) => a - b);

  // Build PnL maps per product
  const pnlByProduct: Record<string, Map<number, number>> = {};
  for (const p of products) {
    pnlByProduct[p] = new Map();
  }
  for (const r of rows) {
    pnlByProduct[r.product].set(Number(r.timestamp), Number(r.pnl) || 0);
  }

  // Total PnL per timestamp
  const totalPnl = timestamps.map((ts) =>
    products.reduce((sum, p) => sum + (pnlByProduct[p].get(ts) ?? 0), 0)
  );

  const series = [
    {
      name: "Total PnL",
      type: "line",
      data: totalPnl.map((v, i) => [timestamps[i], Math.round(v * 100) / 100]),
      symbol: "none",
      lineStyle: { color: "#e6edf3", width: 2.5 },
      itemStyle: { color: "#e6edf3" },
      areaStyle: {
        color: {
          type: "linear",
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(20,184,166,0.12)" },
            { offset: 1, color: "rgba(20,184,166,0)" },
          ],
        },
      },
      z: 10,
    },
    ...products.map((p, i) => ({
      name: p,
      type: "line",
      data: timestamps.map((ts) => [ts, Math.round((pnlByProduct[p].get(ts) ?? 0) * 100) / 100]),
      symbol: "none",
      lineStyle: { color: COLORS[i % COLORS.length], width: 1.2, type: "dashed" as const },
      itemStyle: { color: COLORS[i % COLORS.length] },
    })),
  ];

  const option = {
    animation: false,
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 16, bottom: 40 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(13,17,23,0.95)",
      borderColor: "rgba(48,54,61,0.9)",
      textStyle: { color: "#e6edf3", fontSize: 11 },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#7d8590", fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    xAxis: {
      type: "value" as const,
      axisLine: { lineStyle: { color: "rgba(48,54,61,0.5)" } },
      axisLabel: { color: "#484f58", fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value" as const,
      scale: true,
      axisLine: { show: false },
      axisLabel: { color: "#484f58", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(48,54,61,0.2)" } },
    },
    series,
  };

  return <ReactECharts option={option} style={{ height: 240 }} notMerge />;
}
