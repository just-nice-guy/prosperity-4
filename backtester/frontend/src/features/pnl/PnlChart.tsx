import ReactECharts from "echarts-for-react";
import { ActivityRow } from "../../api/types";

type PnlChartProps = {
  rows: ActivityRow[];
};

export function PnlChart({ rows }: PnlChartProps) {
  const data = rows.map((row) => [Number(row.timestamp), Number(row.pnl)]);
  const lastPnl = data.length > 0 ? data[data.length - 1][1] : 0;
  const color = lastPnl >= 0 ? "#3fb950" : "#f85149";
  const areaColor = lastPnl >= 0 ? "rgba(63, 185, 80, 0.13)" : "rgba(248, 81, 73, 0.13)";

  return (
    <ReactECharts
      style={{ height: 180 }}
      option={{
        animation: false,
        backgroundColor: "transparent",
        tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
        grid: { left: 44, right: 16, top: 12, bottom: 28 },
        xAxis: {
          type: "value",
          axisLabel: { color: "#7d8590", fontSize: 10 },
          splitLine: { lineStyle: { color: "rgba(48,54,61,0.5)" } }
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: { color: "#7d8590", fontSize: 10 },
          splitLine: { lineStyle: { color: "rgba(48,54,61,0.5)" } }
        },
        series: [
          {
            type: "line",
            name: "PnL",
            showSymbol: false,
            data,
            lineStyle: { width: 2, color },
            areaStyle: { color: areaColor }
          }
        ]
      }}
    />
  );
}
