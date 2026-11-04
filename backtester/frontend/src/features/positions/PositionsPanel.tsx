import { ActivityRow } from "../../api/types";

function InfoTip({ text }: { text: string }) {
  return (
    <span
      title={text}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 13,
        height: 13,
        borderRadius: "50%",
        border: "1px solid var(--border)",
        color: "var(--text-dim)",
        fontSize: 9,
        fontWeight: 700,
        cursor: "help",
        marginLeft: 4,
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      i
    </span>
  );
}

type PositionsPanelProps = {
  rows: ActivityRow[];
};

export function PositionsPanel({ rows }: PositionsPanelProps) {
  const latest = rows[rows.length - 1];
  if (!latest) {
    return <p className="muted-text">No position state available.</p>;
  }

  const pnl = Number(latest.pnl);
  const pos = Number(latest.position);

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <span className="stat-label" style={{ display: "flex", alignItems: "center" }}>
          Product
          <InfoTip text="Instrument shown. Use product tabs above to switch." />
        </span>
        <span className="stat-value" style={{ fontSize: 14 }}>{latest.product}</span>
      </div>

      <div className="stat-card">
        <span className="stat-label" style={{ display: "flex", alignItems: "center" }}>
          Position
          <InfoTip text="Units held at end of simulation. Positive = long (net buyer). Negative = short (net seller). Limit is ±80." />
        </span>
        <span
          className="stat-value"
          style={{ color: pos > 0 ? "var(--bid)" : pos < 0 ? "var(--ask)" : undefined }}
        >
          {pos > 0 ? "+" : ""}{pos}
        </span>
      </div>

      <div className="stat-card">
        <span className="stat-label" style={{ display: "flex", alignItems: "center" }}>
          Cash
          <InfoTip text="Realised cash flow: sum of all (sell_price × qty) minus (buy_price × qty) fills. Does not include the mark-to-market value of any open position." />
        </span>
        <span className="stat-value" style={{ fontSize: 14 }}>{Number(latest.cash).toFixed(2)}</span>
      </div>

      <div className={`stat-card ${pnl >= 0 ? "stat-card-positive" : "stat-card-negative"}`}>
        <span className="stat-label" style={{ display: "flex", alignItems: "center" }}>
          Product PnL
          <InfoTip text="Cash + mark-to-market (position × last mid price) for this product only. The Final PnL shown in the header sums all products together, which is why they may differ." />
        </span>
        <span className="stat-value">{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</span>
      </div>
    </div>
  );
}
