import ReactECharts from "echarts-for-react";
import { ActivityRow } from "../../api/types";

const N = (v: string | undefined | null) => (v && v !== "" && v !== "None" ? Number(v) : null);

type Props = {
  rows: ActivityRow[];
  selectedTimestamp: number | null;
  onSelectTimestamp: (t: number) => void;
};

export function VolumeChart({ rows, selectedTimestamp, onSelectTimestamp }: Props) {
  const timestamps = rows.map((r) => Number(r.timestamp));

  const bidVol1 = rows.map((r) => N(r.bid_volume_1));
  const bidVol2 = rows.map((r) => N(r.bid_volume_2));
  const bidVol3 = rows.map((r) => N(r.bid_volume_3));
  const askVol1 = rows.map((r) => (N(r.ask_volume_1) !== null ? -(N(r.ask_volume_1) as number) : null));
  const askVol2 = rows.map((r) => (N(r.ask_volume_2) !== null ? -(N(r.ask_volume_2) as number) : null));
  const askVol3 = rows.map((r) => (N(r.ask_volume_3) !== null ? -(N(r.ask_volume_3) as number) : null));

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
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 12, bottom: 50 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "rgba(13,17,23,0.95)",
      borderColor: "rgba(48,54,61,0.9)",
      textStyle: { color: "#e6edf3", fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number | null }>) => {
        const lines = params
          .filter((p) => p.value !== null)
          .map((p) => {
            const v = Math.abs(p.value as number);
            return `<span style="color:${p.seriesName.includes("Ask") ? "#f85149" : "#3fb950"}">${p.seriesName}: ${v}</span>`;
          });
        return lines.join("<br/>");
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#7d8590", fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    dataZoom: [
      {
        type: "slider" as const,
        bottom: 18,
        height: 14,
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
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value" as const,
      axisLine: { show: false },
      axisLabel: {
        color: "#484f58",
        fontSize: 10,
        formatter: (v: number) => String(Math.abs(v)),
      },
      splitLine: { lineStyle: { color: "rgba(48,54,61,0.2)" } },
    },
    series: [
      {
        name: "Bid Vol 1",
        type: "bar",
        stack: "bid",
        data: bidVol1,
        itemStyle: { color: "rgba(63,185,80,0.9)" },
        barMaxWidth: 4,
        markLine,
      },
      {
        name: "Bid Vol 2",
        type: "bar",
        stack: "bid",
        data: bidVol2,
        itemStyle: { color: "rgba(63,185,80,0.5)" },
        barMaxWidth: 4,
      },
      {
        name: "Bid Vol 3",
        type: "bar",
        stack: "bid",
        data: bidVol3,
        itemStyle: { color: "rgba(63,185,80,0.25)" },
        barMaxWidth: 4,
      },
      {
        name: "Ask Vol 1",
        type: "bar",
        stack: "ask",
        data: askVol1,
        itemStyle: { color: "rgba(248,81,73,0.9)" },
        barMaxWidth: 4,
      },
      {
        name: "Ask Vol 2",
        type: "bar",
        stack: "ask",
        data: askVol2,
        itemStyle: { color: "rgba(248,81,73,0.5)" },
        barMaxWidth: 4,
      },
      {
        name: "Ask Vol 3",
        type: "bar",
        stack: "ask",
        data: askVol3,
        itemStyle: { color: "rgba(248,81,73,0.25)" },
        barMaxWidth: 4,
      },
    ],
  };

  const onEvents = {
    click: (params: { componentType: string; dataIndex?: number }) => {
      if (params.componentType === "series" && params.dataIndex !== undefined) {
        const ts = timestamps[params.dataIndex];
        if (ts !== undefined) onSelectTimestamp(ts);
      }
    },
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: 160 }}
      onEvents={onEvents}
      notMerge
    />
  );
}
