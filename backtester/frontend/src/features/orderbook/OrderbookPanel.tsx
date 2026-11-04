import ReactECharts from "echarts-for-react";
import { OrderbookSnapshot } from "../../api/types";

type OrderbookPanelProps = {
  snapshot: OrderbookSnapshot | null;
};

export function OrderbookPanel({ snapshot }: OrderbookPanelProps) {
  if (!snapshot) {
    return (
      <div className="empty-state" style={{ padding: "32px 0" }}>
        <span style={{ fontSize: 22, opacity: 0.4 }}>📖</span>
        <span>Select a timestamp on the timeline to inspect the order book.</span>
      </div>
    );
  }

  const bidBars = snapshot.bid_prices.map((price, i) => [price, snapshot.bid_volumes[i]]);
  const askBars = snapshot.ask_prices.map((price, i) => [price, snapshot.ask_volumes[i]]);
  const midPrice = snapshot.mid_price;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10, fontSize: 12, color: "var(--text-muted)" }}>
        <span>
          <span style={{ color: "var(--bid)", fontWeight: 600 }}>●</span> Bid
        </span>
        <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, color: "var(--text)" }}>
          Mid {midPrice.toFixed(2)}
        </span>
        <span>
          Ask <span style={{ color: "var(--ask)", fontWeight: 600 }}>●</span>
        </span>
      </div>
      <ReactECharts
        style={{ height: 240 }}
        option={{
          animation: false,
          backgroundColor: "transparent",
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
          legend: { show: false },
          grid: { left: 44, right: 16, top: 8, bottom: 32 },
          xAxis: {
            type: "value",
            name: "price",
            scale: true,
            min: "dataMin",
            max: "dataMax",
            nameTextStyle: { color: "#7d8590", fontSize: 10 },
            axisLabel: { color: "#7d8590", fontSize: 10 },
          },
          yAxis: {
            type: "value",
            name: "vol",
            scale: true,
            nameTextStyle: { color: "#7d8590", fontSize: 10 },
            axisLabel: { color: "#7d8590", fontSize: 10 },
          },
          series: [
            {
              type: "bar",
              name: "Bids",
              data: bidBars,
              itemStyle: { color: "rgba(63, 185, 80, 0.75)", borderRadius: [2, 2, 0, 0] }
            },
            {
              type: "bar",
              name: "Asks",
              data: askBars,
              itemStyle: { color: "rgba(248, 81, 73, 0.75)", borderRadius: [2, 2, 0, 0] }
            }
          ]
        }}
      />
    </div>
  );
}
