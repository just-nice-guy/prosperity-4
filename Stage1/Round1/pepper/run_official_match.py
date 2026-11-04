"""Local backtest matching the EXACT data Prosperity uses for one submission:
day 0 only, first 1000 ticks (timestamps 0 to 99,900), matching=prosperity.

Use this to compare against official runs (180495, 222492, 227963, etc.).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backtester" / "backend" / "src"))

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import DayRequest, EngineConfig, run_engine

TRADER_PATH = str(REPO / "Stage1" / "Round1" / "pepper" / "trader.py")
POS_LIMIT = 80
TICKS = 1000   # 100k timestamps = 1000 ticks (matches Prosperity submission scope)


def main() -> None:
    config = EngineConfig(
        trader_path=TRADER_PATH,
        round_days=[DayRequest(round_num=1, day_num=0)],
        data_roots=[str(REPO / "Stage1" / "Round1")],
        limit_overrides={"INTARIAN_PEPPER_ROOT": POS_LIMIT},
        matching_mode="prosperity",
        time_limit_ms=900,
        day_tick_ranges={"1:0": [(0, TICKS)]},   # first TICKS only
    )
    trader = load_trader(TRADER_PATH)
    result = run_engine(config=config, trader=trader)

    print("=" * 72)
    print(f"Official-match backtest — day 0, first {TICKS} ticks, prosperity")
    print(f"  Matches scope of Prosperity submission runs (180495, 222492, …)")
    print("=" * 72)
    print(f"  PnL:           {result.final_pnl:+.2f}")
    print(f"  Final pos:     {result.final_positions}")
    print(f"  Orders:        {result.total_orders}")
    print(f"  Fills:         {result.total_fills}")
    print(f"  Ticks:         {result.total_ticks}")

    # Per-tick position trajectory check
    pep = [a for a in result.activity_rows if a.get("product") == "INTARIAN_PEPPER_ROOT"]
    if pep:
        positions = [int(a.get("position", 0)) for a in pep]
        print(f"  Pos range:     [{min(positions):+d}, {max(positions):+d}] (must stay in ±{POS_LIMIT})")

    # Trade type counts vs official-style classification
    own = result.own_trade_rows
    n_buy = sum(1 for t in own if int(t.get("quantity", 0)) > 0)
    n_sell = sum(1 for t in own if int(t.get("quantity", 0)) < 0)
    qty_buy = sum(int(t["quantity"]) for t in own if int(t["quantity"]) > 0)
    qty_sell = sum(-int(t["quantity"]) for t in own if int(t["quantity"]) < 0)
    print(f"  Own trades:    {len(own)}  ({n_buy} buy / {n_sell} sell)")
    print(f"  Total qty:     buy={qty_buy}  sell={qty_sell}")


if __name__ == "__main__":
    main()
