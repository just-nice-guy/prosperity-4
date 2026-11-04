"""
Eval-day analysis — replay final/trader.py (the Round-1 uploaded merged
trader: PEPPER=v10 + OSMIUM=moyen2) against the Round-2 dataset.

Round 2 data contains:
    round=2 day=-1  (same as Round-1 day -1)
    round=2 day=0   (same as Round-1 day 0)
    round=2 day=1   (the new day — probably the Round-1 evaluation day)

Each day is replayed with a FRESH trader instance so we can see per-day
PnL in isolation (the engine itself already spins up a new trader per
day, but running each day as its own EngineConfig also gives us clean
per-day position starts).

Usage from repo root (bash):
    python Stage1/Round2/eval_day_analysis.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtester" / "backend" / "src"))

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import DayRequest, EngineConfig, run_engine


TRADER_PATH = str(REPO / "Stage1" / "Round1" / "final" / "trader.py")
POS_LIMITS = {"INTARIAN_PEPPER_ROOT": 80, "ASH_COATED_OSMIUM": 80}

DAYS = [
    DayRequest(round_num=2, day_num=-1),
    DayRequest(round_num=2, day_num=0),
    DayRequest(round_num=2, day_num=1),
]


def run_single_day(day: DayRequest) -> dict:
    trader = load_trader(TRADER_PATH)
    config = EngineConfig(
        trader_path=TRADER_PATH,
        round_days=[day],
        data_roots=[str(Path(__file__).resolve().parent)],
        limit_overrides=POS_LIMITS,
        matching_mode="prosperity",
        time_limit_ms=900,
    )
    return {"day": day, "result": run_engine(config=config, trader=trader)}


def summarize(day: DayRequest, result) -> dict:
    acts = result.activity_rows
    by_product_path = defaultdict(lambda: {"min": 0.0, "max": 0.0, "final": 0.0, "min_pos": 0, "max_pos": 0})
    for row in acts:
        prod = row.get("product")
        # `pnl` in activity rows = mark_to_market_by_product[product] = cash + pos*mid.
        pnl = float(row.get("pnl", 0.0))
        pos = int(row.get("position", 0))
        rec = by_product_path[prod]
        rec["min"] = min(rec["min"], pnl)
        rec["max"] = max(rec["max"], pnl)
        rec["final"] = pnl
        rec["min_pos"] = min(rec["min_pos"], pos)
        rec["max_pos"] = max(rec["max_pos"], pos)

    by_product_final = {prod: rec["final"] for prod, rec in by_product_path.items()}

    # Own trade aggregates per product — direction comes from buyer/seller
    own = result.own_trade_rows
    trades_by_prod = defaultdict(lambda: {"n": 0, "buy": 0, "sell": 0})
    for t in own:
        sym = t.get("symbol")
        q = int(t.get("quantity", 0))
        rec = trades_by_prod[sym]
        rec["n"] += 1
        if t.get("buyer") == "SUBMISSION":
            rec["buy"] += q
        elif t.get("seller") == "SUBMISSION":
            rec["sell"] += q

    return {
        "round": day.round_num,
        "day": day.day_num,
        "final_pnl_total": round(result.final_pnl, 2),
        "per_product_final_pnl": {k: round(v, 2) for k, v in by_product_final.items()},
        "per_product_pnl_range": {
            k: (round(v["min"], 2), round(v["max"], 2)) for k, v in by_product_path.items()
        },
        "per_product_pos_range": {
            k: (v["min_pos"], v["max_pos"]) for k, v in by_product_path.items()
        },
        "final_positions": dict(result.final_positions),
        "trades_by_product": {k: dict(v) for k, v in trades_by_prod.items()},
        "total_fills": result.total_fills,
        "total_orders": result.total_orders,
    }


def main() -> None:
    print(f"Trader: {TRADER_PATH}")
    print("=" * 78)

    rows = []
    for day in DAYS:
        print(f"\nRunning round={day.round_num} day={day.day_num} …")
        run = run_single_day(day)
        summary = summarize(run["day"], run["result"])
        rows.append(summary)

    print("\n\n" + "=" * 78)
    print("Per-day summary")
    print("=" * 78)
    header = f"{'round':>6} {'day':>4}  {'TOTAL':>10}  {'PEPPER':>10}  {'OSMIUM':>10}  {'end_pos_pep':>11}  {'end_pos_osm':>11}"
    print(header)
    print("-" * len(header))
    total = 0.0
    for s in rows:
        pp = s["per_product_final_pnl"].get("INTARIAN_PEPPER_ROOT", 0.0)
        oo = s["per_product_final_pnl"].get("ASH_COATED_OSMIUM", 0.0)
        ep = s["final_positions"].get("INTARIAN_PEPPER_ROOT", 0)
        eo = s["final_positions"].get("ASH_COATED_OSMIUM", 0)
        print(f"{s['round']:>6} {s['day']:>4}  {s['final_pnl_total']:>10.2f}  {pp:>10.2f}  {oo:>10.2f}  {ep:>11d}  {eo:>11d}")
        total += s["final_pnl_total"]
    print("-" * len(header))
    print(f"{'':>6} {'SUM':>4}  {total:>10.2f}")

    print("\n\nPer-day detail")
    print("=" * 78)
    for s in rows:
        print(f"\n  round={s['round']} day={s['day']}")
        print(f"    total_fills : {s['total_fills']}")
        print(f"    total_orders: {s['total_orders']}")
        print(f"    pnl range PEPPER: {s['per_product_pnl_range'].get('INTARIAN_PEPPER_ROOT')}")
        print(f"    pnl range OSMIUM: {s['per_product_pnl_range'].get('ASH_COATED_OSMIUM')}")
        print(f"    pos range PEPPER: {s['per_product_pos_range'].get('INTARIAN_PEPPER_ROOT')}")
        print(f"    pos range OSMIUM: {s['per_product_pos_range'].get('ASH_COATED_OSMIUM')}")
        print(f"    trades          : {s['trades_by_product']}")


if __name__ == "__main__":
    main()
