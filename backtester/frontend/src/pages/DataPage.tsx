import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { apiFetch } from "../api/client";
import { DatasetInfo, OrderbookSnapshot, RawPriceRow, RawTradeRow } from "../api/types";
import { OrderBookTable } from "../features/orderbook/OrderBookTable";

// ─── Dataset card ────────────────────────────────────────────────────────────

function FileRow({ label, available }: { label: string; available: boolean }) {
  return (
    <div className="dataset-file-row">
      <span className={`file-dot ${available ? "file-dot-ok" : "file-dot-miss"}`} />
      <span style={{ color: available ? "var(--text-muted)" : "var(--text-dim)" }}>{label}</span>
    </div>
  );
}

function DatasetCard({ dataset }: { dataset: DatasetInfo }) {
  const navigate = useNavigate();
  return (
    <div className="dataset-card" onClick={() => navigate("/backtest")} style={{ cursor: "pointer" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div className="dataset-card-title">Round {dataset.round_num} · Day {dataset.day_num}</div>
          <div className="dataset-card-sub">Round {dataset.round_num}</div>
        </div>
        <div style={{
          fontSize: 10,
          fontWeight: 600,
          padding: "2px 7px",
          borderRadius: "var(--radius-xs)",
          background: "var(--teal-dim)",
          color: "var(--teal)",
          border: "1px solid var(--teal-border)",
          whiteSpace: "nowrap"
        }}>
          Ready
        </div>
      </div>
      <div className="dataset-files">
        <FileRow label="prices" available={Boolean(dataset.prices_file)} />
        <FileRow label="trades" available={Boolean(dataset.trades_file)} />
        <FileRow label="observations" available={Boolean(dataset.observations_file)} />
      </div>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Offset timestamps so day -2 and day -1 don't overlap on the x-axis. */
function buildXTimestamp(row: { day_num: number; timestamp: number }): number {
  // Each day has ticks 0..999900 (step 100). Offset by day index.
  // day_num -2 → offset 0, day_num -1 → offset 1_000_000
  return (row.day_num + 2) * 1_000_000 + row.timestamp;
}

function buildSpreadSeries(prices: RawPriceRow[]): [number, number][] {
  return prices
    .filter((r) => r.best_bid !== null && r.best_ask !== null)
    .map((r) => [buildXTimestamp(r), Math.abs((r.best_ask as number) - (r.best_bid as number))]);
}

// ─── Charts ──────────────────────────────────────────────────────────────────

function snapshotKey(row: { round_num: number; day_num: number; timestamp: number }): string {
  return `${row.round_num}:${row.day_num}:${row.timestamp}`;
}

function OrderBookQuickView({ product, prices }: { product: string; prices: RawPriceRow[] }) {
  const snapshotOptions = useMemo(
    () =>
      prices.map((row) => ({
        key: snapshotKey(row),
        roundNum: row.round_num,
        dayNum: row.day_num,
        timestamp: row.timestamp,
        label: `R${row.round_num} D${row.day_num} t${row.timestamp}`,
      })),
    [prices]
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const activeOption =
    snapshotOptions.find((item) => item.key === selectedKey) ?? snapshotOptions[0] ?? null;

  const orderbookQuery = useQuery({
    queryKey: ["dataset-orderbook", product, activeOption?.key],
    queryFn: () =>
      apiFetch<OrderbookSnapshot>(
        `/api/datasets/orderbook?product=${product}&round_num=${activeOption!.roundNum}&day_num=${activeOption!.dayNum}&timestamp=${activeOption!.timestamp}`
      ),
    enabled: Boolean(activeOption),
  });

  return (
    <div className="data-orderbook">
      <div className="data-orderbook-header">
        <div>
          <div className="data-section-title">Order book</div>
          <div className="data-section-subtitle">
            {activeOption ? activeOption.label : "No snapshot"}
          </div>
        </div>
        <select
          className="data-snapshot-select"
          value={activeOption?.key ?? ""}
          onChange={(event) => setSelectedKey(event.target.value)}
        >
          {snapshotOptions.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      {orderbookQuery.isLoading && (
        <p className="muted-text" style={{ padding: "16px 0", margin: 0 }}>
          Loading order book...
        </p>
      )}
      {orderbookQuery.isError && (
        <p className="error-text" style={{ padding: "16px 0", margin: 0 }}>
          Failed to load order book.
        </p>
      )}
      {!orderbookQuery.isLoading && !orderbookQuery.isError && (
        <OrderBookTable snapshot={orderbookQuery.data ?? null} />
      )}
    </div>
  );
}

const AXIS_LABEL = { color: "#7d8590", fontSize: 10 };
const SPLIT_LINE = { lineStyle: { color: "rgba(48,54,61,0.5)" } };

function ProductCharts({ product }: { product: string }) {
  const pricesQuery = useQuery({
    queryKey: ["raw-prices", product],
    queryFn: () => apiFetch<RawPriceRow[]>(`/api/datasets/prices?product=${product}`)
  });
  const tradesQuery = useQuery({
    queryKey: ["raw-trades", product],
    queryFn: () => apiFetch<RawTradeRow[]>(`/api/datasets/trades?product=${product}`)
  });

  if (pricesQuery.isLoading) {
    return (
      <div style={{ padding: "28px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
        Loading market data…
      </div>
    );
  }

  if (pricesQuery.isError) {
    return <p className="error-text" style={{ padding: "12px 16px" }}>Failed to load price data.</p>;
  }

  const prices = pricesQuery.data ?? [];
  const trades = tradesQuery.data ?? [];

  if (prices.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "24px 0" }}>
        <span className="empty-state-icon">📊</span>
        <span>No data available for {product}.</span>
      </div>
    );
  }

  // Build bid/ask line data
  const bidLine = prices
    .filter((r) => r.best_bid !== null)
    .map((r) => [buildXTimestamp(r), r.best_bid as number]);
  const askLine = prices
    .filter((r) => r.best_ask !== null)
    .map((r) => [buildXTimestamp(r), r.best_ask as number]);

  // Build trade scatter: [x, price, qty]
  // Size each bubble proportionally to quantity (sqrt for perceptual accuracy)
  const maxQty = Math.max(1, ...trades.map((t) => t.quantity));
  const tradeScatter = trades.map((t) => ({
    value: [buildXTimestamp(t), t.price],
    symbolSize: Math.max(4, Math.round(Math.sqrt(t.quantity / maxQty) * 18 + 3))
  }));

  // Build day boundary markers for x-axis
  const dayLabels: { xAxis: number; label: { formatter: string; color: string; fontSize: number } }[] = [];
  const days = Array.from(new Set(prices.map((r) => r.day_num))).sort();
  for (const d of days) {
    const firstTs = prices.find((r) => r.day_num === d);
    if (firstTs) {
      dayLabels.push({
        xAxis: buildXTimestamp(firstTs),
        label: { formatter: `Day ${d}`, color: "#484f58", fontSize: 10 }
      });
    }
  }

  // Spread per tick
  const spreadSeries = buildSpreadSeries(prices);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>

      {/* ── Bid / Ask price chart ── */}
      <div style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "10px 16px 0",
          fontSize: 11,
          color: "var(--text-dim)"
        }}>
          <span style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Bid / Ask — all days
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ display: "inline-block", width: 20, height: 2, background: "var(--bid)", verticalAlign: "middle" }} />
            Bid
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ display: "inline-block", width: 20, height: 2, background: "var(--ask)", verticalAlign: "middle" }} />
            Ask
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "rgba(255,200,60,0.6)", border: "1px solid rgba(255,200,60,0.4)", verticalAlign: "middle" }} />
            Trades (size = volume)
          </span>
        </div>
        <ReactECharts
          style={{ height: 280 }}
          option={{
            animation: false,
            backgroundColor: "transparent",
            tooltip: {
              trigger: "axis",
              axisPointer: { type: "cross" },
              formatter: (params: unknown) => {
                const p = params as Array<{ seriesName: string; value: [number, number]; data?: { value: [number, number]; symbolSize: number } }>;
                const lines = p.map((item) => {
                  if (item.seriesName === "Trades") return null;
                  return `<span style="color:${item.seriesName === "Bid" ? "#3fb950" : "#f85149"}">${item.seriesName}</span>: ${item.value[1]}`;
                }).filter(Boolean);
                return lines.join("<br/>");
              }
            },
            grid: { left: 52, right: 16, top: 12, bottom: 32 },
            xAxis: {
              type: "value",
              axisLabel: {
                ...AXIS_LABEL,
                formatter: (val: number) => {
                  const dayIdx = Math.floor(val / 1_000_000);
                  const ts = val % 1_000_000;
                  return `D${dayIdx - 2} t${ts}`;
                }
              },
              splitLine: SPLIT_LINE,
              markLine: dayLabels.length > 0 ? { data: dayLabels, symbol: "none", lineStyle: { color: "rgba(255,255,255,0.06)", type: "dashed" } } : undefined
            },
            yAxis: {
              type: "value",
              scale: true,
              axisLabel: AXIS_LABEL,
              splitLine: SPLIT_LINE
            },
            series: [
              {
                type: "line",
                name: "Bid",
                data: bidLine,
                showSymbol: false,
                lineStyle: { width: 1.5, color: "rgba(63,185,80,0.85)" },
                emphasis: { disabled: true }
              },
              {
                type: "line",
                name: "Ask",
                data: askLine,
                showSymbol: false,
                lineStyle: { width: 1.5, color: "rgba(248,81,73,0.85)" },
                emphasis: { disabled: true }
              },
              {
                type: "scatter",
                name: "Trades",
                data: tradeScatter,
                itemStyle: {
                  color: "rgba(255,200,60,0.55)",
                  borderColor: "rgba(255,200,60,0.35)",
                  borderWidth: 1
                },
                emphasis: { disabled: true }
              }
            ]
          }}
        />
      </div>

      {/* ── Spread per tick ── */}
      <div>
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "10px 16px 0",
          fontSize: 11,
          color: "var(--text-dim)"
        }}>
          <span style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Spread — |ask₁ − bid₁| per tick
          </span>
          <span>{spreadSeries.length.toLocaleString()} ticks</span>
        </div>
        <ReactECharts
          style={{ height: 160 }}
          option={{
            animation: false,
            backgroundColor: "transparent",
            tooltip: {
              trigger: "axis",
              axisPointer: { type: "shadow" },
              formatter: (params: unknown) => {
                const p = params as Array<{ value: [number, number] }>;
                if (!p[0]) return "";
                return `Spread: <b>${p[0].value[1]}</b>`;
              }
            },
            grid: { left: 52, right: 16, top: 8, bottom: 28 },
            xAxis: {
              type: "value",
              axisLabel: {
                ...AXIS_LABEL,
                formatter: (val: number) => {
                  const dayIdx = Math.floor(val / 1_000_000);
                  const ts = val % 1_000_000;
                  return `D${dayIdx - 2} t${ts}`;
                }
              },
              splitLine: { show: false }
            },
            yAxis: {
              type: "value",
              scale: true,
              axisLabel: AXIS_LABEL,
              splitLine: SPLIT_LINE
            },
            series: [
              {
                type: "bar",
                data: spreadSeries,
                barWidth: 1,
                itemStyle: { color: "rgba(88,166,255,0.6)" }
              }
            ]
          }}
        />
      </div>

      <OrderBookQuickView product={product} prices={prices} />
    </div>
  );
}

// ─── Product row (expandable) ─────────────────────────────────────────────────

function ProductRow({
  product,
  expanded,
  onToggle
}: {
  product: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dotColor = product === "EMERALDS" ? "var(--green)" : "var(--orange)";

  return (
    <div style={{ borderBottom: "1px solid var(--border-subtle)" }}>
      {/* Header row — clickable */}
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          cursor: "pointer",
          transition: "background 0.12s",
          userSelect: "none"
        }}
        onMouseEnter={(e) => ((e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.02)")}
        onMouseLeave={(e) => ((e.currentTarget as HTMLDivElement).style.background = "transparent")}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, display: "inline-block", flexShrink: 0 }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{product}</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{product}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {expanded ? "Hide chart" : "Show chart"}
          </span>
          <span style={{
            fontSize: 11,
            color: "var(--text-dim)",
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.18s",
            display: "inline-block",
            lineHeight: 1
          }}>▾</span>
        </div>
      </div>

      {/* Expanded chart area */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--border-subtle)", background: "rgba(0,0,0,0.14)" }}>
          <ProductCharts product={product} />
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DataPage() {
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiFetch<DatasetInfo[]>("/api/datasets")
  });
  const productsQuery = useQuery({
    queryKey: ["products"],
    queryFn: () => apiFetch<string[]>("/api/datasets/products")
  });

  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);

  const datasets = datasetsQuery.data ?? [];
  const products = productsQuery.data ?? [];

  const toggle = (product: string) =>
    setExpandedProduct((prev) => (prev === product ? null : product));

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Market Data</p>
          <h1 className="page-title">Available Datasets</h1>
          <p className="page-desc">Historical price and trade data for simulation.</p>
        </div>
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-label">Datasets</span>
            <span className="stat-value">{datasetsQuery.isLoading ? "…" : datasets.length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Products</span>
            <span className="stat-value">{productsQuery.isLoading ? "…" : products.length}</span>
          </div>
        </div>
      </div>

      {/* Dataset registry */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Files</p>
            <p className="panel-title">Dataset Registry</p>
          </div>
        </div>
        <div className="panel-body">
          {datasetsQuery.isLoading && <p className="muted-text">Loading datasets…</p>}
          {datasetsQuery.isError && <p className="error-text">Failed to load datasets.</p>}
          {datasets.length === 0 && !datasetsQuery.isLoading && (
            <div className="empty-state">
              <span className="empty-state-icon">📂</span>
              <span>No datasets discovered. Start the backend with the data path configured.</span>
            </div>
          )}
          {datasets.length > 0 && (
            <div className="dataset-grid">
              {datasets.map((ds) => (
                <DatasetCard key={`${ds.round_num}:${ds.day_num}`} dataset={ds} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Instruments */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Instruments</p>
            <p className="panel-title">Market Data Explorer</p>
          </div>
          <div className="product-tags">
            {products.map((p) => (
              <span key={p} className="product-tag">{p}</span>
            ))}
          </div>
        </div>

        <div>
          {productsQuery.isLoading && (
            <p className="muted-text" style={{ padding: "16px" }}>Loading products…</p>
          )}
          {!productsQuery.isLoading && products.length === 0 && (
            <div className="empty-state"><span>No products found in datasets.</span></div>
          )}
          {products.map((product) => (
            <ProductRow
              key={product}
              product={product}
              expanded={expandedProduct === product}
              onToggle={() => toggle(product)}
            />
          ))}
        </div>

        {/* Schema reference */}
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>Prices columns</div>
              <div style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace", lineHeight: 1.8 }}>
                day · timestamp · product<br />
                bid_price_1..3 · bid_volume_1..3<br />
                ask_price_1..3 · ask_volume_1..3<br />
                mid_price · profit_and_loss
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>Trades columns</div>
              <div style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace", lineHeight: 1.8 }}>
                timestamp · buyer · seller<br />
                symbol · currency<br />
                price · quantity
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
