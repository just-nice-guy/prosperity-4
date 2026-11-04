import ReactECharts from "echarts-for-react";
import { ActivityRow } from "../../api/types";

const COLORS = ["#14b8a6", "#f97316", "#bc8cff", "#58a6ff", "#f85149", "#3fb950"];
const POS_LIMITS: Record<string, number> = {
  EMERALDS: 80,
  TOMATOES: 80,
};
const DEFAULT_LIMIT = 80;

export type PositionMode = "percent" | "quantity";

type Props = {
  rows: ActivityRow[];
  mode?: PositionMode;
};

export function PositionOverviewChart({ rows, mode = "percent" }: Props) {
  const products = Array.from(new Set(rows.map((r) => r.product)));
  const timestamps = Array.from(new Set(rows.map((r) => Number(r.timestamp)))).sort((a, b) => a - b);

  // Build position maps per product
  const posByProduct: Record<string, Map<number, number>> = {};
  for (const p of products) {
    posByProduct[p] = new Map();
  }
  for (const r of rows) {
    const pos = Number(r.position);
    if (mode === "percent") {
      const limit = POS_LIMITS[r.product] ?? DEFAULT_LIMIT;
      const pct = (pos / limit) * 100;
      posByProduct[r.product].set(Number(r.timestamp), Math.round(pct * 10) / 10);
    } else {
      posByProduct[r.product].set(Number(r.timestamp), pos);
    }
  }

  const series = products.map((p, i) => ({
    name: p,
    type: "line",
    step: "end" as const,
    data: timestamps.map((ts) => [ts, posByProduct[p].get(ts) ?? 0]),
    symbol: "none",
    lineStyle: { color: COLORS[i % COLORS.length], width: 1.5 },
    itemStyle: { color: COLORS[i % COLORS.length] },
  }));

  const isPercent = mode === "percent";

  const option = {
    animation: false,
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 16, bottom: 40 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(13,17,23,0.95)",
      borderColor: "rgba(48,54,61,0.9)",
      textStyle: { color: "#e6edf3", fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: [number, number]; color: string }>) => {
        const lines = params.map(
          (p) => `<span style="color:${p.color}">${p.seriesName}: ${p.value[1]}${isPercent ? "%" : ""}</span>`
        );
        return `t=${params[0]?.value[0]}<br/>${lines.join("<br/>")}`;
      },
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
      ...(isPercent ? { min: -110, max: 110 } : { scale: true }),
      axisLine: { show: false },
      axisLabel: {
        color: "#484f58",
        fontSize: 10,
        formatter: isPercent ? (v: number) => `${v}%` : undefined,
      },
      splitLine: { lineStyle: { color: "rgba(48,54,61,0.2)" } },
    },
    series: [
      // Limit reference lines (only in % mode)
      ...(isPercent ? [
        {
          name: "+Limit", type: "line" as const,
          data: [[timestamps[0], 100], [timestamps[timestamps.length - 1], 100]],
          symbol: "none" as const,
          lineStyle: { color: "rgba(248,81,73,0.3)", type: "dashed" as const, width: 1 },
          silent: true,
        },
        {
          name: "-Limit", type: "line" as const,
          data: [[timestamps[0], -100], [timestamps[timestamps.length - 1], -100]],
          symbol: "none" as const,
          lineStyle: { color: "rgba(248,81,73,0.3)", type: "dashed" as const, width: 1 },
          silent: true,
        },
      ] : []),
      ...series,
    ],
  };

  return <ReactECharts option={option} style={{ height: 240 }} notMerge />;
}
