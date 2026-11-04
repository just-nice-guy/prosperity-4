"""Generate continuous synthetic 10k-tick datasets from the 1k-tick base.

Continuity strategy
───────────────────
The source 1k base naturally drifts ~+101 ticks for PEPPER (start mid≈11998.5,
end mid≈12099.5). If we naively tile it 10x, every tile boundary creates a
−101 jump (back to the original start). Ugly and breaks the bot's filters.

Fix: each tile is played FORWARD or REVERSED. We track a `cumulative` price
level, and each tile starts EXACTLY where the previous one ended:

  Forward tile (drift +natural):
    start_mid = cumulative
    end_mid   = cumulative + natural_drift

  Reverse tile (drift −natural, source rows read right-to-left):
    start_mid = cumulative
    end_mid   = cumulative − natural_drift

After each tile, cumulative += signed drift. Result: prices form a continuous
walk across all 10 tiles.

For each row we apply `delta = tile_mid_at_p − source_mid_at_p` to ALL prices
(bids, asks, mid). Volumes and spread structure are preserved.

Scenarios are encoded as a 10-character string of F/R, one per tile:

  flat            FRFRFRFRFR  (oscillates, net drift ≈ 0)
  trend_up        FFFFFFFFFF  (+1010)
  trend_down      RRRRRRRRRR  (−1010)
  reversal_start  RFFFFFFFFF  (drops 101, rises 909 → net +808)
  reversal_middle FFFFFRRRRR  (peaks at mid +505, returns to start)
  reversal_end    FFFFFFFFFR  (rises 909, drops 101 → net +808)
  zigzag_long     FFRRFFRRFF  (chunks of 2 tiles)
  random_seed_<N> random F/R per tile

Usage:
    python Stage1/Round1/synthetic_datasets/generate_synthetic_datasets.py
"""
from __future__ import annotations

import io
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
SOURCE_PRICES = REPO / "Stage1" / "Round1" / "prices_round_1_day_0.csv"
SOURCE_TRADES = REPO / "Stage1" / "Round1" / "trades_round_1_day_0.csv"
OUT_DIR = REPO / "Stage1" / "Round1" / "synthetic_datasets" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_TICKS = 1000
N_TILES = 10
TICK_STEP = 100

# Price-column indices in the row layout
PRICE_COLS = [3, 5, 7, 9, 11, 13]   # bid_p1/2/3, ask_p1/2/3
MID_COL = 15
TS_COL = 1
PROD_COL = 2


def parse_source(path: Path) -> tuple[str, list[list[str]]]:
    """Header + base 1000-tick rows, with bad rows filtered out."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = lines[0]
    body = lines[1:]
    max_ts = (BASE_TICKS - 1) * TICK_STEP
    base_rows: list[list[str]] = []
    n_filtered = 0
    for r in body:
        cols = r.split(";")
        if int(cols[TS_COL]) > max_ts:
            continue
        bb, ba, mid = cols[3], cols[9], cols[MID_COL]
        is_bad = (bb == "" and ba == "") or (mid == "" or float(mid) == 0)
        if is_bad:
            n_filtered += 1
            continue
        base_rows.append(cols)
    if n_filtered > 0:
        print(f"  Filtered {n_filtered} bad rows (no orderbook / mid=0)")
    return header, base_rows


def split_by_product(rows: list[list[str]]) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = {}
    for r in rows:
        out.setdefault(r[PROD_COL], []).append(r)
    return out


def parse_trades(path: Path) -> tuple[str, list[list[str]]]:
    """Header + base trade rows in first 1k ticks. Cols: ts;buyer;seller;symbol;currency;price;qty."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = lines[0]
    body = lines[1:]
    max_ts = (BASE_TICKS - 1) * TICK_STEP
    base_trades: list[list[str]] = []
    for r in body:
        cols = r.split(";")
        if int(cols[0]) > max_ts:
            continue
        base_trades.append(cols)
    return header, base_trades


def split_trades_by_product(trades: list[list[str]]) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = {}
    for t in trades:
        out.setdefault(t[3], []).append(t)
    return out


def shift_row(row: list[str], delta: float) -> list[str]:
    """Shift all prices in a row by delta (rounded for ints, .1f for mid)."""
    new_row = list(row)
    for col in PRICE_COLS:
        if new_row[col]:
            new_row[col] = str(int(round(int(float(new_row[col])) + delta)))
    if new_row[MID_COL]:
        new_row[MID_COL] = f"{float(new_row[MID_COL]) + delta:.1f}"
    return new_row


def build_dataset_rows(
    pattern: str,
    rows_by_product: dict[str, list[list[str]]],
    trades_by_product: dict[str, list[list[str]]],
) -> tuple[list[list[str]], list[list[str]]]:
    """Build (price_rows, trade_rows) for a 10-char F/R pattern.

    Per product: each tile is played forward or reverse. Cumulative price
    level carries over → continuity at every tile boundary. Within a tile
    the offset (delta) is constant: delta = cumulative − ref_mid (where
    ref_mid is first_mid for F or last_mid for R). Same delta applied to
    BOTH the price rows and the trade rows in that tile.

    Trade timestamps in reverse tiles are mirrored: a source trade at local
    ts T appears at local ts (L−1)·TICK_STEP − T inside the tile.
    """
    assert len(pattern) == N_TILES
    products = sorted(rows_by_product.keys())

    out_prices: dict[str, list[list[str]]] = {p: [] for p in products}
    out_trades: list[list[str]] = []

    for prod in products:
        source = rows_by_product[prod]
        src_trades = trades_by_product.get(prod, [])
        L = len(source)
        first_mid = float(source[0][MID_COL])
        last_mid = float(source[-1][MID_COL])
        natural_drift = last_mid - first_mid

        cumulative = first_mid

        for k in range(N_TILES):
            direction = pattern[k]
            ref_mid = first_mid if direction == "F" else last_mid
            tile_delta = cumulative - ref_mid    # constant within this tile
            tile_base_ts = k * L * TICK_STEP

            # Prices
            for p in range(L):
                src_idx = p if direction == "F" else (L - 1 - p)
                src_row = source[src_idx]
                shifted = shift_row(src_row, tile_delta)
                shifted[0] = "0"
                shifted[TS_COL] = str(tile_base_ts + p * TICK_STEP)
                shifted[16] = "0.0"
                out_prices[prod].append(shifted)

            # Trades for this product, this tile
            for t in src_trades:
                src_ts = int(t[0])
                # Local ts in tile: forward = src_ts; reverse = mirror
                if direction == "F":
                    local_ts = src_ts
                else:
                    local_ts = (L - 1) * TICK_STEP - src_ts
                if local_ts < 0 or local_ts >= L * TICK_STEP:
                    continue
                new_ts = tile_base_ts + local_ts
                new_price = float(t[5]) + tile_delta
                new_trade = list(t)
                new_trade[0] = str(new_ts)
                new_trade[5] = f"{new_price:.1f}"
                out_trades.append(new_trade)

            cumulative += (natural_drift if direction == "F" else -natural_drift)

    # Interleave price rows by (ts, product)
    all_prices: list[list[str]] = []
    for prod in products:
        all_prices.extend(out_prices[prod])
    all_prices.sort(key=lambda r: (int(r[TS_COL]), r[PROD_COL]))

    # Sort trades by timestamp
    out_trades.sort(key=lambda r: int(r[0]))

    return all_prices, out_trades


def write_dataset(
    name: str,
    price_header: str,
    price_rows: list[list[str]],
    trade_header: str,
    trade_rows: list[list[str]],
) -> tuple[Path, Path]:
    """Write both prices and trades CSVs (canonical naming so the engine
    finds them via round_registry)."""
    prices_path = OUT_DIR / f"prices_round_99_day_0__{name}.csv"
    prices_path.write_text(
        price_header + "\n" + "\n".join(";".join(r) for r in price_rows) + "\n",
        encoding="utf-8",
    )
    trades_path = OUT_DIR / f"trades_round_99_day_0__{name}.csv"
    trades_path.write_text(
        trade_header + "\n" + "\n".join(";".join(r) for r in trade_rows) + "\n",
        encoding="utf-8",
    )
    return prices_path, trades_path


def random_pattern(seed: int, n: int = N_TILES) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("FR") for _ in range(n))


def main() -> None:
    print(f"Sources:\n  prices = {SOURCE_PRICES}\n  trades = {SOURCE_TRADES}")
    print(f"Output: {OUT_DIR}")
    price_header, base_rows = parse_source(SOURCE_PRICES)
    trade_header, base_trades = parse_trades(SOURCE_TRADES)
    rows_by_product = split_by_product(base_rows)
    trades_by_product = split_trades_by_product(base_trades)
    L_per = {p: len(rs) for p, rs in rows_by_product.items()}
    T_per = {p: len(ts) for p, ts in trades_by_product.items()}
    print(f"Loaded prices: {L_per}")
    print(f"Loaded trades: {T_per}")

    scenarios = [
        ("flat",            "FRFRFRFRFR"),
        ("trend_up",        "FFFFFFFFFF"),
        ("trend_down",      "RRRRRRRRRR"),
        ("reversal_start",  "RFFFFFFFFF"),
        ("reversal_middle", "FFFFFRRRRR"),
        ("reversal_end",    "FFFFFFFFFR"),
        ("zigzag_long",     "FFRRFFRRFF"),
        ("random_seed_1",   random_pattern(1)),
        ("random_seed_2",   random_pattern(2)),
        ("random_seed_3",   random_pattern(3)),
        ("random_seed_4",   random_pattern(4)),
        ("random_seed_5",   random_pattern(5)),
    ]

    for name, pattern in scenarios:
        prices, trades = build_dataset_rows(pattern, rows_by_product, trades_by_product)
        write_dataset(name, price_header, prices, trade_header, trades)
        pep_rows = [r for r in prices if r[PROD_COL] == "INTARIAN_PEPPER_ROOT"]
        first = float(pep_rows[0][MID_COL])
        last = float(pep_rows[-1][MID_COL])
        peak = max(float(r[MID_COL]) for r in pep_rows)
        trough = min(float(r[MID_COL]) for r in pep_rows)
        print(f"  {name:18s}  pattern={pattern}  pep mid: start={first:.0f}  end={last:.0f}  range=[{trough:.0f}, {peak:.0f}]  trades={len(trades)}")


if __name__ == "__main__":
    main()
