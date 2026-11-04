import { OrderbookSnapshot } from "../../api/types";

type Props = {
  snapshot: OrderbookSnapshot | null;
};

type Level = {
  price: number;
  bidVol: number | null;
  askVol: number | null;
};

export function OrderBookTable({ snapshot }: Props) {
  if (!snapshot) {
    return (
      <div className="empty-state" style={{ padding: "24px 12px" }}>
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
          Click a timestamp on the chart to view the order book.
        </span>
      </div>
    );
  }

  // Build unified price levels
  const levels: Level[] = [];
  const bidMap = new Map<number, number>();
  const askMap = new Map<number, number>();

  for (let i = 0; i < snapshot.bid_prices.length; i++) {
    bidMap.set(snapshot.bid_prices[i], snapshot.bid_volumes[i]);
  }
  for (let i = 0; i < snapshot.ask_prices.length; i++) {
    askMap.set(snapshot.ask_prices[i], snapshot.ask_volumes[i]);
  }

  const allPrices = Array.from(new Set([...snapshot.bid_prices, ...snapshot.ask_prices]));
  allPrices.sort((a, b) => b - a); // Descending

  for (const price of allPrices) {
    levels.push({
      price,
      bidVol: bidMap.get(price) ?? null,
      askVol: askMap.get(price) ?? null,
    });
  }

  // Find the gap (spread)
  const bestBid = snapshot.bid_prices[0] ?? 0;
  const bestAsk = snapshot.ask_prices[0] ?? 0;
  const spread = bestAsk - bestBid;

  // Max volume for bar width
  const maxVol = Math.max(
    ...snapshot.bid_volumes,
    ...snapshot.ask_volumes,
    1
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 11 }}>
        <span style={{ color: "var(--text-dim)" }}>
          {snapshot.product} @ t={snapshot.timestamp}
        </span>
        <span style={{ color: "var(--text-dim)" }}>
          Mid: <strong style={{ color: "var(--text-muted)" }}>{snapshot.mid_price}</strong>
          {" "}Spread: <strong style={{ color: spread <= 2 ? "var(--green)" : spread <= 6 ? "var(--orange)" : "var(--red)" }}>{spread}</strong>
        </span>
      </div>
      <div className="table-wrap">
        <table style={{ fontSize: 11 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "right", width: "30%" }}>Bid Vol</th>
              <th style={{ textAlign: "center", width: "40%" }}>Price</th>
              <th style={{ textAlign: "left", width: "30%" }}>Ask Vol</th>
            </tr>
          </thead>
          <tbody>
            {levels.map((lvl, i) => {
              const isAsk = lvl.askVol !== null;
              const isBid = lvl.bidVol !== null;
              const isBestBid = lvl.price === bestBid;
              const isBestAsk = lvl.price === bestAsk;

              // Insert spread row
              const showSpread =
                i > 0 &&
                levels[i - 1].askVol !== null &&
                lvl.bidVol !== null &&
                spread > 0;

              return (
                <tr key={`${lvl.price}-${i}`}>
                  <td style={{ textAlign: "right", position: "relative" }}>
                    {isBid && (
                      <>
                        <div
                          style={{
                            position: "absolute",
                            right: 0,
                            top: 2,
                            bottom: 2,
                            width: `${(lvl.bidVol! / maxVol) * 100}%`,
                            background: "rgba(63,185,80,0.15)",
                            borderRadius: 2,
                          }}
                        />
                        <span style={{ position: "relative", color: "var(--bid)", fontWeight: isBestBid ? 700 : 400 }}>
                          {lvl.bidVol}
                        </span>
                      </>
                    )}
                  </td>
                  <td
                    style={{
                      textAlign: "center",
                      fontFamily: "monospace",
                      fontWeight: isBestBid || isBestAsk ? 700 : 400,
                      color: isAsk ? "var(--ask)" : isBid ? "var(--bid)" : "var(--text-muted)",
                      background: showSpread ? "rgba(255,255,255,0.02)" : undefined,
                    }}
                  >
                    {lvl.price}
                  </td>
                  <td style={{ textAlign: "left", position: "relative" }}>
                    {isAsk && (
                      <>
                        <div
                          style={{
                            position: "absolute",
                            left: 0,
                            top: 2,
                            bottom: 2,
                            width: `${(lvl.askVol! / maxVol) * 100}%`,
                            background: "rgba(248,81,73,0.15)",
                            borderRadius: 2,
                          }}
                        />
                        <span style={{ position: "relative", color: "var(--ask)", fontWeight: isBestAsk ? 700 : 400 }}>
                          {lvl.askVol}
                        </span>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
