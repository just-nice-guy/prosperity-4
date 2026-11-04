import { ActivityRow, TradeRow } from "../../api/types";

/** Per-tick state extracted from the lambdaLog text (set by `print()`). */
export type LambdaSnapshot = {
  timestamp: number;
  L: number | null;          // our fair-value estimate
  B: number | null;          // drift (Holt trend component)
  pos: number | null;        // our position
  fav: number | null;        // regime sign
  imb: number | null;        // imbalance
  bidQuotes: number[];       // our bid levels emitted at this tick
  askQuotes: number[];       // our ask levels emitted at this tick
};

export type ParsedOfficialLog = {
  sandboxLines: string[];
  activities: ActivityRow[];
  trades: TradeRow[];
  botTrades: TradeRow[];
  lambdaSnapshots: LambdaSnapshot[];   // parsed from print() output per tick
};

/**
 * Parse an official Prosperity platform log into structured data compatible
 * with our chart components.
 *
 * Supports two formats:
 *  1. **JSON** (`.log` file downloaded from the platform)
 *  2. **Plain text** (copy-pasted from the web UI)
 */
export function parseOfficialLog(text: string): ParsedOfficialLog {
  const trimmed = text.trim();

  // Try JSON format first
  if (trimmed.startsWith("{")) {
    try {
      const json = JSON.parse(trimmed);
      if (json.activitiesLog || json.tradeHistory || json.logs) {
        return parseJsonFormat(json);
      }
    } catch {
      // Not valid JSON — fall through to text parsing
    }
  }

  return parseTextFormat(trimmed);
}

// ── JSON format parser ──────────────────────────────────────────────────────

interface ProsperityLogJson {
  submissionId?: string;
  activitiesLog?: string;
  logs?: Array<{ sandboxLog?: string; lambdaLog?: string; timestamp?: number }>;
  tradeHistory?: Array<{
    timestamp: number;
    buyer: string;
    seller: string;
    symbol: string;
    currency: string;
    price: number;
    quantity: number;
  }>;
}

function parseJsonFormat(json: ProsperityLogJson): ParsedOfficialLog {
  const rawActivities = parseCsv(json.activitiesLog ?? "");

  // Extract sandbox log lines + lambda snapshots (parsed from print() text)
  const sandboxLines: string[] = [];
  const lambdaSnapshots: LambdaSnapshot[] = [];
  for (const entry of json.logs ?? []) {
    if (entry.sandboxLog) {
      for (const line of entry.sandboxLog.split("\n")) {
        if (line.trim()) sandboxLines.push(line.trim());
      }
    }
    if (entry.lambdaLog && entry.timestamp !== undefined) {
      const snap = parseLambdaLine(entry.lambdaLog, entry.timestamp);
      if (snap) lambdaSnapshots.push(snap);
    }
  }

  // Build trades from tradeHistory array (already structured)
  const allTrades: TradeRow[] = (json.tradeHistory ?? []).map((t) => ({
    round_num: 0,
    day_num: 0,
    timestamp: t.timestamp,
    symbol: t.symbol,
    currency: t.currency ?? "SEASHELLS",
    price: t.price,
    quantity: t.quantity,
    buyer: t.buyer ?? "",
    seller: t.seller ?? "",
    source: "official",
  }));

  // Only submission trades affect position/PnL
  const submissionTrades = allTrades.filter(
    (t) => t.buyer === "SUBMISSION" || t.seller === "SUBMISSION"
  );

  // Compute per-product position and PnL from trades + mid prices
  const productData = computeProductData(rawActivities, submissionTrades);

  const activities: ActivityRow[] = rawActivities.map((r) => {
    const ts = r["timestamp"] ?? "0";
    const prod = r["product"] ?? "";
    const data = productData.get(`${prod}:${ts}`) ?? { position: 0, pnl: 0 };
    return {
      round_num: "0",
      day_num: r["day"] ?? "0",
      timestamp: ts,
      product: prod,
      bid_price_1: r["bid_price_1"] ?? "",
      bid_price_2: r["bid_price_2"] ?? "",
      bid_price_3: r["bid_price_3"] ?? "",
      bid_volume_1: r["bid_volume_1"] ?? "",
      bid_volume_2: r["bid_volume_2"] ?? "",
      bid_volume_3: r["bid_volume_3"] ?? "",
      ask_price_1: r["ask_price_1"] ?? "",
      ask_price_2: r["ask_price_2"] ?? "",
      ask_price_3: r["ask_price_3"] ?? "",
      ask_volume_1: r["ask_volume_1"] ?? "",
      ask_volume_2: r["ask_volume_2"] ?? "",
      ask_volume_3: r["ask_volume_3"] ?? "",
      mid_price: r["mid_price"] ?? "",
      position: String(data.position),
      cash: "0",
      pnl: r["profit_and_loss"] ?? String(Math.round(data.pnl * 100) / 100),
    };
  });

  const botTrades = allTrades.filter(
    (t) => t.buyer !== "SUBMISSION" && t.seller !== "SUBMISSION"
  );

  return { sandboxLines, activities, trades: submissionTrades, botTrades, lambdaSnapshots };
}

/**
 * Parse one line of lambda log text into a structured snapshot.
 * Expected format (from our trader's print()):
 *   t=<ts> pos=<p> fav=<f> ... B=<b> imb=<i> L=<L> ... b=[...] a=[...] ...
 */
function parseLambdaLine(line: string, ts: number): LambdaSnapshot | null {
  const grab = (key: string): string | null => {
    const re = new RegExp(`${key}=([+-]?[0-9]*\\.?[0-9]+)`);
    const m = line.match(re);
    return m ? m[1] : null;
  };
  const grabList = (key: string): number[] => {
    const re = new RegExp(`${key}=\\[([^\\]]*)\\]`);
    const m = line.match(re);
    if (!m) return [];
    return m[1].split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => !isNaN(n));
  };

  const Lstr = grab("L");
  if (Lstr === null) return null;

  return {
    timestamp: ts,
    L: Number(Lstr),
    B: grab("B") !== null ? Number(grab("B")) : null,
    pos: grab("pos") !== null ? Number(grab("pos")) : null,
    fav: grab("fav") !== null ? Number(grab("fav")) : null,
    imb: grab("imb") !== null ? Number(grab("imb")) : null,
    bidQuotes: grabList("b"),
    askQuotes: grabList("a"),
  };
}

// ── Text format parser (legacy) ─────────────────────────────────────────────

function parseTextFormat(text: string): ParsedOfficialLog {
  const sections = splitSections(text);

  const sandboxLines = (sections["Sandbox logs"] ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const activityCsv = sections["Activities log"] ?? "";
  const tradeCsv = sections["Trade History"] ?? "";

  const rawActivities = parseCsv(activityCsv);
  const rawTrades = parseCsv(tradeCsv);

  // Build TradeRow objects from CSV rows, filtering to submission trades only
  const allTrades: TradeRow[] = rawTrades.map((r) => ({
    round_num: 0,
    day_num: Number(r["day"] ?? 0),
    timestamp: Number(r["timestamp"] ?? 0),
    symbol: r["symbol"] ?? r["product"] ?? "",
    currency: r["currency"] ?? "SEASHELLS",
    price: Number(r["price"] ?? 0),
    quantity: Number(r["quantity"] ?? 0),
    buyer: r["buyer"] ?? "",
    seller: r["seller"] ?? "",
    source: "official",
  }));

  const submissionTrades = allTrades.filter(
    (t) => t.buyer === "SUBMISSION" || t.seller === "SUBMISSION"
  );

  const productData = computeProductData(rawActivities, submissionTrades);

  const activities: ActivityRow[] = rawActivities.map((r) => {
    const ts = r["timestamp"] ?? "0";
    const prod = r["product"] ?? "";
    const data = productData.get(`${prod}:${ts}`) ?? { position: 0, pnl: 0 };
    return {
      round_num: "0",
      day_num: r["day"] ?? "0",
      timestamp: ts,
      product: prod,
      bid_price_1: r["bid_price_1"] ?? "",
      bid_price_2: r["bid_price_2"] ?? "",
      bid_price_3: r["bid_price_3"] ?? "",
      bid_volume_1: r["bid_volume_1"] ?? "",
      bid_volume_2: r["bid_volume_2"] ?? "",
      bid_volume_3: r["bid_volume_3"] ?? "",
      ask_price_1: r["ask_price_1"] ?? "",
      ask_price_2: r["ask_price_2"] ?? "",
      ask_price_3: r["ask_price_3"] ?? "",
      ask_volume_1: r["ask_volume_1"] ?? "",
      ask_volume_2: r["ask_volume_2"] ?? "",
      ask_volume_3: r["ask_volume_3"] ?? "",
      mid_price: r["mid_price"] ?? "",
      position: String(data.position),
      cash: "0",
      pnl: r["profit_and_loss"] ?? String(Math.round(data.pnl * 100) / 100),
    };
  });

  const botTrades = allTrades.filter(
    (t) => t.buyer !== "SUBMISSION" && t.seller !== "SUBMISSION"
  );

  return { sandboxLines, activities, trades: submissionTrades, botTrades, lambdaSnapshots: [] };
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function splitSections(text: string): Record<string, string> {
  const sections: Record<string, string[]> = {};
  let current = "root";
  sections[current] = [];

  for (const line of text.split("\n")) {
    const stripped = line.trim().replace(/:$/, "");
    if (
      stripped === "Sandbox logs" ||
      stripped === "Activities log" ||
      stripped === "Trade History"
    ) {
      current = stripped;
      if (!sections[current]) sections[current] = [];
      continue;
    }
    if (!sections[current]) sections[current] = [];
    sections[current].push(line);
  }

  const result: Record<string, string> = {};
  for (const [name, lines] of Object.entries(sections)) {
    result[name] = lines.join("\n").trim();
  }
  return result;
}

function parseCsv(text: string): Record<string, string>[] {
  const cleaned = text.trim();
  if (!cleaned) return [];

  const lines = cleaned.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length < 2) return [];

  const firstLine = lines[0];
  const delimiter = firstLine.split(";").length >= firstLine.split(",").length ? ";" : ",";

  const headers = firstLine.split(delimiter).map((h) => h.trim());
  const rows: Record<string, string>[] = [];

  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(delimiter);
    const row: Record<string, string> = {};
    for (let j = 0; j < headers.length; j++) {
      row[headers[j]] = (values[j] ?? "").trim();
    }
    rows.push(row);
  }

  return rows;
}

/**
 * Compute per-product position (carry-forward) and mark-to-market PnL.
 *
 * Only counts trades where SUBMISSION is buyer or seller.
 * Returns Map<"product:timestamp", { position, pnl }>.
 */
function computeProductData(
  rawActivities: Record<string, string>[],
  submissionTrades: TradeRow[],
): Map<string, { position: number; pnl: number }> {
  // Index trade deltas by product:timestamp
  const tradeDeltaMap = new Map<string, { qty: number; cash: number }>();
  for (const t of submissionTrades) {
    const key = `${t.symbol}:${t.timestamp}`;
    const existing = tradeDeltaMap.get(key) ?? { qty: 0, cash: 0 };
    if (t.buyer === "SUBMISSION") {
      existing.qty += t.quantity;
      existing.cash -= t.price * t.quantity;
    } else {
      existing.qty -= t.quantity;
      existing.cash += t.price * t.quantity;
    }
    tradeDeltaMap.set(key, existing);
  }

  // Walk activities in order, carry forward position & cash per product
  const state: Record<string, { position: number; cash: number }> = {};
  const result = new Map<string, { position: number; pnl: number }>();

  for (const r of rawActivities) {
    const prod = r["product"] ?? "";
    const ts = Number(r["timestamp"] ?? 0);
    const mid = Number(r["mid_price"] ?? 0);

    if (!state[prod]) state[prod] = { position: 0, cash: 0 };

    // Apply trade deltas at this timestamp
    const delta = tradeDeltaMap.get(`${prod}:${ts}`);
    if (delta) {
      state[prod].position += delta.qty;
      state[prod].cash += delta.cash;
    }

    const pnl = state[prod].cash + state[prod].position * mid;
    result.set(`${prod}:${ts}`, { position: state[prod].position, pnl });
  }

  return result;
}
