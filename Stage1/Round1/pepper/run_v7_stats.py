"""
Run v7 backtest and produce detailed stats:
- L1 placement: how often each of our 3 bid/ask levels is AT/BELOW/ABOVE L1
- Fill counts and types (passive/aggressive)
- Comparison summary

Usage: python Stage1/Round1/pepper/run_v7_stats.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from collections import Counter

# Force UTF-8 stdout to avoid Windows cp1252 errors with arrows etc.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backtester" / "backend" / "src"))

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import DayRequest, EngineConfig, run_engine

TRADER_PATH = str(REPO / "Stage1" / "Round1" / "pepper" / "trader.py")
POS_LIMIT = 80


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

    print("=" * 72)
    print(f"v7 backtest — 3 days, matching=prosperity, limit={POS_LIMIT}")
    print("=" * 72)
    print(f"PnL:           {result.final_pnl:.2f}")
    print(f"final pos (engine sums across days): {result.final_positions}")
    print(f"orders:        {result.total_orders}")
    print(f"fills:         {result.total_fills}")
    print(f"ticks:         {result.total_ticks}")

    # Per-day position extremes (the actual within-day cap check)
    by_day_max: dict[int, int] = {}
    by_day_min: dict[int, int] = {}
    for a in result.activity_rows:
        if a.get("product") != "INTARIAN_PEPPER_ROOT":
            continue
        try:
            day = int(a.get("day", 0))
            p = int(a.get("position", 0))
        except Exception:
            continue
        by_day_max[day] = max(by_day_max.get(day, p), p)
        by_day_min[day] = min(by_day_min.get(day, p), p)
    print(f"\nPer-day position extremes (must stay in [-{POS_LIMIT}, +{POS_LIMIT}]):")
    for day in sorted(by_day_max.keys()):
        print(f"  day {day}: min={by_day_min[day]:+4d}  max={by_day_max[day]:+4d}")

    # Build L1 lookup by timestamp from activities
    l1_at: dict[tuple[int, int], tuple[int | None, int | None]] = {}
    for a in result.activity_rows:
        if a.get("product") != "INTARIAN_PEPPER_ROOT":
            continue
        try:
            ts = int(a["timestamp"])
            day = int(a.get("day", 0))
        except Exception:
            continue
        bb = a.get("bid_price_1")
        ba = a.get("ask_price_1")
        bb_i = int(bb) if bb not in (None, "", "None") else None
        ba_i = int(ba) if ba not in (None, "", "None") else None
        l1_at[(day, ts)] = (bb_i, ba_i)

    # Parse our bid/ask levels per tick from sandbox log
    # Format: "t=<ts> ... b=[1, 2, 3] a=[4, 5, 6] ..."
    import re
    bid_re = re.compile(r"t=(\d+).*?\bb=\[([^\]]*)\]\s+a=\[([^\]]*)\]")

    bid_vs_l1: Counter[str] = Counter()  # per-level position string
    ask_vs_l1: Counter[str] = Counter()
    bid_deep_vs_l1: Counter[str] = Counter()
    ask_deep_vs_l1: Counter[str] = Counter()
    bid_tight_dist_from_mid: Counter[int] = Counter()  # tight bid: mid - px
    ask_tight_dist_from_mid: Counter[int] = Counter()  # tight ask: px - mid

    n_ticks_quoted = 0
    n_ticks_no_l1 = 0

    log_lines = result.sandbox_log.splitlines()
    cur_day = -2  # not perfect but ok for aggregate
    # We need to align timestamps to days. The sandbox log only shows ts %day,
    # which restarts each day. Track via sequence: when ts decreases, day++.
    last_ts = -1
    days_seen = 0
    for line in log_lines:
        m = bid_re.search(line)
        if not m:
            continue
        ts = int(m.group(1))
        if ts < last_ts:
            days_seen += 1
        last_ts = ts
        day = -2 + days_seen
        bids_s = m.group(2).strip()
        asks_s = m.group(3).strip()
        bid_levels = [int(x) for x in bids_s.split(",") if x.strip()]
        ask_levels = [int(x) for x in asks_s.split(",") if x.strip()]

        l1 = l1_at.get((day, ts))
        if l1 is None:
            n_ticks_no_l1 += 1
            continue
        bb, ba = l1
        if bb is None or ba is None:
            n_ticks_no_l1 += 1
            continue
        n_ticks_quoted += 1

        # Classify each bid level vs market best_bid
        for px in bid_levels:
            if px > bb:
                bid_vs_l1["INSIDE (px > best_bid)"] += 1
            elif px == bb:
                bid_vs_l1["AT_L1 (px = best_bid)"] += 1
            else:
                bid_vs_l1["BEHIND (px < best_bid)"] += 1
        # Deep is the lowest bid we placed (deepest from mid)
        if bid_levels:
            deep_bid = min(bid_levels)
            if deep_bid > bb:
                bid_deep_vs_l1["INSIDE"] += 1
            elif deep_bid == bb:
                bid_deep_vs_l1["AT_L1"] += 1
            else:
                bid_deep_vs_l1["BEHIND"] += 1

        # Tight bid is the highest of bid_levels (closest to mid)
        if bid_levels:
            tight_bid = max(bid_levels)
            mid = (bb + ba) / 2
            d = int(round(mid - tight_bid))
            bid_tight_dist_from_mid[d] += 1

        for px in ask_levels:
            if px < ba:
                ask_vs_l1["INSIDE (px < best_ask)"] += 1
            elif px == ba:
                ask_vs_l1["AT_L1 (px = best_ask)"] += 1
            else:
                ask_vs_l1["BEHIND (px > best_ask)"] += 1
        if ask_levels:
            deep_ask = max(ask_levels)
            if deep_ask < ba:
                ask_deep_vs_l1["INSIDE"] += 1
            elif deep_ask == ba:
                ask_deep_vs_l1["AT_L1"] += 1
            else:
                ask_deep_vs_l1["BEHIND"] += 1
            tight_ask = min(ask_levels)
            mid = (bb + ba) / 2
            d = int(round(tight_ask - mid))
            ask_tight_dist_from_mid[d] += 1

    print()
    print("─" * 72)
    print(f"Quote-vs-L1 stats (over {n_ticks_quoted} ticks, {n_ticks_no_l1} skipped)")
    print("─" * 72)

    def pct(c: Counter, total: int) -> str:
        out = []
        for k, v in sorted(c.items(), key=lambda x: -x[1]):
            out.append(f"  {k:35s} {v:6d}  ({100.0*v/max(1,total):5.1f}%)")
        return "\n".join(out)

    total_b = sum(bid_vs_l1.values())
    total_a = sum(ask_vs_l1.values())
    print("\nALL BID LEVELS (3 per tick):")
    print(pct(bid_vs_l1, total_b))
    print("\nALL ASK LEVELS (3 per tick):")
    print(pct(ask_vs_l1, total_a))
    print(f"\nDEEPEST BID (closest to/behind L1):")
    print(pct(bid_deep_vs_l1, sum(bid_deep_vs_l1.values())))
    print(f"\nDEEPEST ASK:")
    print(pct(ask_deep_vs_l1, sum(ask_deep_vs_l1.values())))

    def hist(c: Counter[int], total: int) -> str:
        out = []
        for k in sorted(c.keys()):
            v = c[k]
            out.append(f"  {k:+3d} ticks from mid:  {v:6d}  ({100.0*v/max(1,total):5.1f}%)")
        return "\n".join(out)

    print(f"\nTIGHT BID distance from mid (positive = below mid):")
    print(hist(bid_tight_dist_from_mid, sum(bid_tight_dist_from_mid.values())))
    print(f"\nTIGHT ASK distance from mid (positive = above mid):")
    print(hist(ask_tight_dist_from_mid, sum(ask_tight_dist_from_mid.values())))

    # Fill stats
    print()
    print("─" * 72)
    print("Own-trade stats")
    print("─" * 72)
    own = result.own_trade_rows
    print(f"  total fills:   {len(own)}")
    if own:
        passive_buys = 0
        aggressive_buys = 0
        passive_sells = 0
        aggressive_sells = 0
        for t in own:
            try:
                ts = int(t.get("timestamp", 0))
                day = int(t.get("day", 0))
                px = float(t.get("price", 0))
                qty = int(t.get("quantity", 0))
            except Exception:
                continue
            l1 = l1_at.get((day, ts))
            if l1 is None or l1[0] is None or l1[1] is None:
                continue
            bb, ba = l1
            if qty > 0:  # buy
                if px >= ba:
                    aggressive_buys += qty
                else:
                    passive_buys += qty
            else:
                if px <= bb:
                    aggressive_sells += -qty
                else:
                    passive_sells += -qty
        print(f"  passive buys:    {passive_buys}")
        print(f"  aggressive buys: {aggressive_buys}")
        print(f"  passive sells:   {passive_sells}")
        print(f"  aggressive sells:{aggressive_sells}")


if __name__ == "__main__":
    main()
