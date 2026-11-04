/**
 * TickInspector — shows, for the selected timestamp:
 *   - Orders submitted by the trader (from decision_trace)
 *   - Fills received (fill_market_trade events)
 *   - Orders that expired unfilled (resting_order_expired events)
 *   - Whether each order was a passive quote or aggressive cross
 */

type RawOrder = { symbol: string; price: number; quantity: number };

type DecisionEntry = {
  timestamp: number;
  symbol: string | null;
  payload: {
    orders?: Record<string, RawOrder[]>;
    positions?: Record<string, number>;
    elapsed_ms?: number;
  };
};

type EventEntry = {
  kind: string;
  timestamp: number;
  symbol: string | null;
  payload: {
    price?: number;
    quantity?: number;
    buyer?: string;
    seller?: string;
    symbol?: string;
    order?: RawOrder;
    remaining_quantity?: number;
  };
};

type Props = {
  timestamp: number | null;
  product: string;
  decisionTrace: DecisionEntry[];
  events: EventEntry[];
};

function badge(label: string, color: string, bg: string) {
  return (
    <span
      style={{
        fontSize: 10,
        padding: "1px 6px",
        borderRadius: 4,
        background: bg,
        color,
        fontWeight: 700,
        letterSpacing: "0.04em",
        flexShrink: 0,
      }}
    >
      {label}
    </span>
  );
}

function classifyOrder(order: RawOrder, fills: EventEntry[], expirations: EventEntry[]) {
  const isBuy = order.quantity > 0;
  const qty = Math.abs(order.quantity);

  // Check if this order (by price) appears in fills or expirations
  const fillMatch = fills.find(
    (e) =>
      e.payload.price === order.price &&
      (isBuy
        ? e.payload.buyer === "SUBMISSION"
        : e.payload.seller === "SUBMISSION")
  );
  const expiredMatch = expirations.find(
    (e) =>
      e.payload.order?.price === order.price &&
      ((e.payload.order?.quantity ?? 0) > 0) === isBuy
  );

  const status = fillMatch
    ? "filled"
    : expiredMatch
    ? "expired"
    : "pending";

  const filledQty = fillMatch ? (fillMatch.payload.quantity ?? 0) : 0;
  const partial = filledQty > 0 && filledQty < qty;

  return { status, filledQty, partial };
}

export function TickInspector({ timestamp, product, decisionTrace, events }: Props) {
  if (timestamp === null) return null;

  // Find decision at this timestamp
  const decision = decisionTrace.find((d) => d.timestamp === timestamp);
  const tickOrders: RawOrder[] = (decision?.payload?.orders?.[product] ?? []);

  // Events at this timestamp for this product
  const tickEvents = events.filter(
    (e) => e.timestamp === timestamp && (e.symbol === product || e.symbol === null)
  );
  const fills = tickEvents.filter((e) => e.kind === "fill_market_trade");
  const expirations = tickEvents.filter((e) => e.kind === "resting_order_expired");

  const pos = decision?.payload?.positions?.[product] ?? null;
  const elapsed = decision?.payload?.elapsed_ms;

  if (!decision && fills.length === 0) {
    return (
      <div style={{ padding: "8px 16px", fontSize: 12, color: "var(--text-dim)" }}>
        No data for t={timestamp}
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 16px 12px" }}>
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 10,
          fontSize: 12,
          color: "var(--text-muted)",
        }}
      >
        <span style={{ fontFamily: "monospace", color: "var(--text)" }}>t={timestamp}</span>
        {pos !== null && (
          <span>
            Position:{" "}
            <strong style={{ color: pos > 0 ? "var(--bid)" : pos < 0 ? "var(--ask)" : "var(--text)" }}>
              {pos > 0 ? "+" : ""}{pos}
            </strong>
          </span>
        )}
        {elapsed !== undefined && (
          <span style={{ color: "var(--text-dim)" }}>
            {elapsed.toFixed(1)} ms
          </span>
        )}
        <span style={{ color: "var(--text-dim)" }}>
          {tickOrders.length} order{tickOrders.length !== 1 ? "s" : ""} submitted
          {fills.length > 0 && `, ${fills.length} fill${fills.length !== 1 ? "s" : ""}`}
          {expirations.length > 0 && `, ${expirations.length} expired`}
        </span>
      </div>

      {/* Orders table */}
      {tickOrders.length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 10 }}>
          <table>
            <thead>
              <tr>
                <th>Side</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Type</th>
                <th>Outcome</th>
                <th>Filled qty</th>
              </tr>
            </thead>
            <tbody>
              {tickOrders.map((order, i) => {
                const isBuy = order.quantity > 0;
                const { status, filledQty, partial } = classifyOrder(order, fills, expirations);
                return (
                  <tr key={i}>
                    <td>
                      {isBuy
                        ? badge("BID", "#3fb950", "rgba(63,185,80,0.12)")
                        : badge("ASK", "#f85149", "rgba(248,81,73,0.12)")}
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums", fontFamily: "monospace" }}>
                      {order.price}
                    </td>
                    <td className={isBuy ? "td-buy" : "td-sell"} style={{ fontWeight: 600 }}>
                      {isBuy ? "+" : ""}{order.quantity}
                    </td>
                    <td>
                      {badge("PASSIVE", "#7d8590", "rgba(125,133,144,0.12)")}
                    </td>
                    <td>
                      {status === "filled" && !partial &&
                        badge("FILLED", "#3fb950", "rgba(63,185,80,0.12)")}
                      {status === "filled" && partial &&
                        badge("PARTIAL", "#f97316", "rgba(249,115,22,0.12)")}
                      {status === "expired" &&
                        badge("EXPIRED", "#7d8590", "rgba(125,133,144,0.08)")}
                      {status === "pending" &&
                        badge("—", "#7d8590", "transparent")}
                    </td>
                    <td style={{ fontFamily: "monospace", color: filledQty > 0 ? "var(--text)" : "var(--text-dim)" }}>
                      {filledQty > 0 ? filledQty : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Fills summary */}
      {fills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {fills.map((f, i) => {
            const weBought = f.payload.buyer === "SUBMISSION";
            const price = f.payload.price ?? 0;
            const qty = f.payload.quantity ?? 0;
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "3px 8px",
                  borderRadius: 6,
                  background: weBought ? "rgba(63,185,80,0.10)" : "rgba(248,81,73,0.10)",
                  border: `1px solid ${weBought ? "rgba(63,185,80,0.25)" : "rgba(248,81,73,0.25)"}`,
                  fontSize: 12,
                }}
              >
                <span style={{ fontWeight: 700, color: weBought ? "#3fb950" : "#f85149" }}>
                  {weBought ? "▲ BOUGHT" : "▼ SOLD"}
                </span>
                <span style={{ fontFamily: "monospace" }}>{qty} @ {price}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
