import { useCallback, useMemo, useRef, useState } from "react";
import { parseOfficialLog, ParsedOfficialLog } from "../features/visualizer/parseOfficialLog";
import { ActivityRow, TradeRow } from "../api/types";
import { PriceDepthChart } from "../features/depth/PriceDepthChart";
import { VolumeChart } from "../features/depth/VolumeChart";
import { SummaryPnlChart } from "../features/overview/SummaryPnlChart";
import { PositionOverviewChart, PositionMode } from "../features/overview/PositionOverviewChart";
import { OrderBookTable } from "../features/orderbook/OrderBookTable";
import { TimestampSlider } from "../features/navigation/TimestampSlider";
import { FairValueChart } from "../features/visualizer/FairValueChart";

export function VisualizerPage() {
  const [rawText, setRawText] = useState("");
  const [parsed, setParsed] = useState<ParsedOfficialLog | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [product, setProduct] = useState<string>("");
  const [selectedTimestamp, setSelectedTimestamp] = useState<number | null>(null);
  const [positionMode, setPositionMode] = useState<PositionMode>("percent");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const doParse = useCallback((text: string) => {
    try {
      const result = parseOfficialLog(text);
      if (result.activities.length === 0) {
        setParseError("No activity data found. Check that the file is a valid Prosperity log (JSON or text).");
        return;
      }
      setParsed(result);
      setParseError(null);
      const products = Array.from(new Set(result.activities.map((r) => r.product)));
      if (products.length > 0) setProduct(products[0]);
      const ts = Number(result.activities[0].timestamp);
      if (!isNaN(ts)) setSelectedTimestamp(ts);
    } catch (e) {
      setParseError(`Parse error: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, []);

  const handleParse = useCallback(() => doParse(rawText), [rawText, doParse]);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      setRawText(text);
      doParse(text);
    };
    reader.onerror = () => setParseError("Failed to read file.");
    reader.readAsText(file);
    // Reset so the same file can be re-selected
    e.target.value = "";
  }, [doParse]);

  const handleClear = useCallback(() => {
    setParsed(null);
    setParseError(null);
    setRawText("");
    setProduct("");
    setSelectedTimestamp(null);
  }, []);

  // Derived data
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

  // Build orderbook snapshot for the selected timestamp
  const orderbookSnapshot = useMemo(() => {
    if (!selectedTimestamp || !product) return null;
    const row = filteredActivities.find((r) => Number(r.timestamp) === selectedTimestamp);
    if (!row) return null;

    const N = (v: string | undefined | null) => (v && v !== "" && v !== "None" ? Number(v) : null);

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

  // ── Import form (no data loaded yet) ─────────────────────────────────────
  if (!parsed) {
    return (
      <div className="page">
        <div className="page-header">
          <div className="page-header-left">
            <p className="page-eyebrow">Visualizer</p>
            <h1 className="page-title">Official Log Visualizer</h1>
            <p className="page-desc">
              Paste your official Prosperity platform log below to visualize it.
              Export logs from the Prosperity website and paste the full text.
            </p>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Import</p>
              <p className="panel-title">Paste Official Log</p>
            </div>
          </div>
          <div className="panel-body">
            <input
              ref={fileInputRef}
              type="file"
              accept=".log,.json,.txt"
              onChange={handleFileUpload}
              style={{ display: "none" }}
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: "2px dashed var(--border-subtle)",
                borderRadius: "var(--radius-sm, 6px)",
                padding: "32px 16px",
                textAlign: "center",
                cursor: "pointer",
                background: "var(--bg-inset, #0d1117)",
                marginBottom: 12,
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>&#128194;</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                Click to upload a <strong>.log</strong> file from the Prosperity platform
              </div>
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
                Supports JSON format (downloaded file) and plain text (copy-pasted)
              </div>
            </div>
            <details style={{ marginBottom: 8 }}>
              <summary style={{ fontSize: 12, color: "var(--text-dim)", cursor: "pointer" }}>
                Or paste log text manually
              </summary>
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder={'{"submissionId":"...","activitiesLog":"day;timestamp;...","logs":[...],"tradeHistory":[...]}'}
                style={{
                  width: "100%",
                  minHeight: 200,
                  marginTop: 8,
                  background: "var(--bg-inset, #0d1117)",
                  color: "var(--text)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm, 6px)",
                  padding: 12,
                  fontFamily: "monospace",
                  fontSize: 12,
                  resize: "vertical",
                }}
              />
              <button
                className="btn btn-primary"
                onClick={handleParse}
                disabled={!rawText.trim()}
                style={{ marginTop: 8 }}
              >
                Parse & Visualize
              </button>
            </details>
            {parseError && (
              <div style={{ color: "var(--red, #f85149)", marginTop: 8, fontSize: 12 }}>
                {parseError}
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Help</p>
              <p className="panel-title">How to export logs</p>
            </div>
          </div>
          <div className="panel-body" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            <ol style={{ paddingLeft: 20, lineHeight: 1.8 }}>
              <li>Go to the Prosperity platform and run your algorithm</li>
              <li>Once the run completes, download the <strong>.log</strong> file (JSON format)</li>
              <li>Upload it using the button above</li>
            </ol>
            <p style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 8 }}>
              Both the JSON download format and the plain-text copy-paste format are supported.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── Visualization view ───────────────────────────────────────────────────
  const finalPnl = filteredActivities.length > 0
    ? Number(filteredActivities[filteredActivities.length - 1].pnl)
    : undefined;

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <p className="page-eyebrow">Visualizer</p>
          <h1 className="page-title">Official Log Visualizer</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
            <span className="pill pill-completed">parsed</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {parsed.activities.length} activity rows &middot; {parsed.trades.length} trades
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
            <span className="stat-label">Products</span>
            <span className="stat-value">{products.length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Ticks</span>
            <span className="stat-value">{timestamps.length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Trades</span>
            <span className="stat-value">{parsed.trades.length}</span>
          </div>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11, padding: "6px 12px" }}
            onClick={handleClear}
          >
            Clear & Import New
          </button>
        </div>
      </div>

      {/* Timestamp slider */}
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
                      // Reset timestamp to first for new product
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

      {/* Price Depth Chart */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-header-left">
            <p className="panel-eyebrow">Market Data</p>
            <p className="panel-title">3-Level Price Depth</p>
          </div>
          {selectedTimestamp !== null && (
            <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>
              t={selectedTimestamp}
            </span>
          )}
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

      {/* Fair Value Chart — our L vs market levels + our quotes */}
      {parsed.lambdaSnapshots.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Strategy</p>
              <p className="panel-title">Fair Value (L) vs Market &amp; Our Quotes</p>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>
              {parsed.lambdaSnapshots.length} ticks logged
            </span>
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

      {/* Volume Chart */}
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

      {/* Orderbook + PnL Overview side by side */}
      <div className="two-col">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Snapshot</p>
              <p className="panel-title">Order Book</p>
            </div>
            {selectedTimestamp !== null && (
              <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>
                t={selectedTimestamp}
              </span>
            )}
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

      {/* Position Overview */}
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

      {/* Trades Table */}
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

      {/* Sandbox Logs */}
      {parsed.sandboxLines.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="panel-header-left">
              <p className="panel-eyebrow">Debug</p>
              <p className="panel-title">Sandbox Logs</p>
            </div>
          </div>
          <div className="panel-body">
            <pre style={{
              margin: 0,
              fontFamily: "monospace",
              fontSize: 11,
              color: "var(--text-muted)",
              whiteSpace: "pre-wrap",
              maxHeight: 300,
              overflow: "auto",
            }}>
              {parsed.sandboxLines.join("\n")}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Trade table with instrument + passive/aggressive ─────────────────────────

const N = (v: string | undefined | null) => (v && v !== "" && v !== "None" ? Number(v) : null);

function TradeTable({ trades, activities }: { trades: TradeRow[]; activities: ActivityRow[] }) {
  // Build bid/ask lookup by (product, timestamp) for passive/aggressive classification
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
    return (
      <div className="empty-state">
        <span className="empty-state-icon">&#128200;</span>
        <span>No trades.</span>
      </div>
    );
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

            // Classify passive vs aggressive
            const d = depthAt.get(`${t.symbol}:${t.timestamp}`);
            let fillType = "—";
            if (isBuy) {
              fillType = d && d.ba !== null && t.price >= d.ba ? "Aggressive" : "Passive";
            } else if (isSell) {
              fillType = d && d.bb !== null && t.price <= d.bb ? "Aggressive" : "Passive";
            }
            const typeColor = fillType === "Aggressive" ? "var(--text-dim)" : "var(--text-muted, #8b949e)";

            return (
              <tr key={i}>
                <td style={{ fontFamily: "monospace" }}>{t.timestamp}</td>
                <td style={{ fontWeight: 500 }}>{t.symbol}</td>
                <td style={{ color, fontWeight: 600 }}>{side}</td>
                <td style={{ fontSize: 10, color: typeColor }}>{fillType}</td>
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
