import { TradeRow } from "../../api/types";

type TradesPanelProps = {
  ownTrades: TradeRow[];
  marketTrades: TradeRow[];
};

function TradeRowEl({ row, source }: { row: TradeRow; source: "own" | "market" }) {
  // Quantities are always positive in the store — direction comes from buyer/seller
  const isBuy = source === "own" ? row.buyer === "SUBMISSION" : row.quantity > 0;
  return (
    <tr>
      <td className="td-mono">{row.timestamp}</td>
      <td style={{ fontWeight: 600, fontSize: 11, letterSpacing: "0.04em" }}>{row.symbol}</td>
      <td style={{ fontVariantNumeric: "tabular-nums" }}>{row.price}</td>
      <td className={isBuy ? "td-buy" : "td-sell"} style={{ fontWeight: 600 }}>
        {isBuy ? "+" : "-"}{row.quantity}
      </td>
      <td className="td-mono">{row.buyer || "—"}</td>
      <td className="td-mono">{row.seller || "—"}</td>
      <td>
        <span
          style={{
            fontSize: 10,
            padding: "1px 6px",
            borderRadius: "var(--radius-xs)",
            background: source === "own" ? "var(--teal-dim)" : "rgba(255,255,255,0.04)",
            color: source === "own" ? "var(--teal)" : "var(--text-dim)",
            border: `1px solid ${source === "own" ? "var(--teal-border)" : "var(--border-subtle)"}`,
            fontWeight: 600,
            letterSpacing: "0.04em"
          }}
        >
          {source}
        </span>
      </td>
    </tr>
  );
}

export function TradesPanel({ ownTrades, marketTrades }: TradesPanelProps) {
  const rows: Array<{ row: TradeRow; source: "own" | "market" }> = [
    ...ownTrades.map((row) => ({ row, source: "own" as const })),
    ...marketTrades.map((row) => ({ row, source: "market" as const }))
  ]
    .sort((a, b) => b.row.timestamp - a.row.timestamp)
    .slice(0, 50);

  if (rows.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "24px 0" }}>
        <span style={{ fontSize: 22, opacity: 0.4 }}>📋</span>
        <span>No trades for the current filter.</span>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Symbol</th>
            <th>Price</th>
            <th>Qty</th>
            <th>Buyer</th>
            <th>Seller</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ row, source }, i) => (
            <TradeRowEl key={`${row.timestamp}-${row.symbol}-${i}`} row={row} source={source} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
