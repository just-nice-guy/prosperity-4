"""
Run the PEPPER_ROOT trader against the local backtester in Prosperity
matching mode, over Round 1 historical days -2, -1, 0.

Usage from repo root:
    python Stage1/Round1/pepper/run_backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backtester" / "backend" / "src"))

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import DayRequest, EngineConfig, run_engine


TRADER_PATH = str(REPO / "Stage1" / "Round1" / "pepper" / "trader.py")
POS_LIMIT = 50


def main() -> None:
    config = EngineConfig(
        trader_path=TRADER_PATH,
        round_days=[
            DayRequest(round_num=1, day_num=-2),
            DayRequest(round_num=1, day_num=-1),
            DayRequest(round_num=1, day_num=0),
        ],
        data_roots=[str(REPO / "Stage1" / "Round1")],
        limit_overrides={"INTARIAN_PEPPER_ROOT": POS_LIMIT},
        matching_mode="prosperity",
        time_limit_ms=900,
    )
    trader = load_trader(TRADER_PATH)
    result = run_engine(config=config, trader=trader)

    print("\n" + "=" * 72)
    print(f"PEPPER_ROOT backtest — matching_mode = prosperity")
    print("=" * 72)
    print(f"run_id:          {result.run_id}")
    print(f"status:          {result.status}")
    print(f"total ticks:     {result.total_ticks}")
    print(f"total orders:    {result.total_orders}")
    print(f"total fills:     {result.total_fills}")
    print(f"final positions: {result.final_positions}")
    print(f"cash:            {result.cash_by_product}")
    print(f"MTM:             {result.mark_to_market_by_product}")
    print(f"FINAL PNL:       {result.final_pnl:.2f}")

    print("\n── Per-day summaries ───────────────────────────────────────────")
    for s in result.dataset_summaries:
        print(f"  {s}")

    print("\n── Sandbox log (last 30 lines) ─────────────────────────────────")
    lines = result.sandbox_log.splitlines()
    for line in lines[-30:]:
        print("  " + line)

    # Aggregate own trades
    print("\n── Own-trade aggregate ─────────────────────────────────────────")
    own = result.own_trade_rows
    print(f"  n_own_trades:    {len(own)}")
    if own:
        total_qty = sum(abs(int(t.get("quantity", 0))) for t in own)
        total_pnl_delta = 0.0
        buy_qty = sum(int(t.get("quantity", 0)) for t in own if int(t.get("quantity", 0)) > 0)
        sell_qty = sum(-int(t.get("quantity", 0)) for t in own if int(t.get("quantity", 0)) < 0)
        prices = [float(t.get("price", 0.0)) for t in own]
        print(f"  total buy qty:   {buy_qty}")
        print(f"  total sell qty:  {sell_qty}")
        print(f"  total qty:       {total_qty}")
        print(f"  price range:     [{min(prices):.1f}, {max(prices):.1f}]")

    # Activity stats
    acts = result.activity_rows
    print(f"\n── Activity rows: {len(acts)}")
    if acts:
        pnls = [float(a.get("profit_and_loss", 0.0)) for a in acts if a.get("product") == "INTARIAN_PEPPER_ROOT"]
        if pnls:
            print(f"  pepper min PnL:  {min(pnls):.2f}")
            print(f"  pepper max PnL:  {max(pnls):.2f}")
            print(f"  pepper final:    {pnls[-1]:.2f}")


if __name__ == "__main__":
    main()
