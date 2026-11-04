"""Compare v4 (180495) vs v7 (196083) official Prosperity runs."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).resolve().parent


def stats(log_path: Path, label: str) -> dict:
    data = json.loads(log_path.read_text(encoding="utf-8"))

    # Activities — last tick's PnL, max/min position
    act = data.get("activitiesLog", "")
    rows = [line.split(";") for line in act.strip().split("\n")]
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    pepper_rows = [r for r in rows[1:] if len(r) >= 3 and r[2] == "INTARIAN_PEPPER_ROOT"]
    final_pnl = float(pepper_rows[-1][idx["profit_and_loss"]]) if pepper_rows else 0.0
    n_ticks = len(pepper_rows)

    # Trades — count own vs bot, buy/sell, passive vs aggressive
    trades = data.get("tradeHistory", [])
    own_buys = [t for t in trades if t.get("buyer") == "SUBMISSION" and t.get("symbol") == "INTARIAN_PEPPER_ROOT"]
    own_sells = [t for t in trades if t.get("seller") == "SUBMISSION" and t.get("symbol") == "INTARIAN_PEPPER_ROOT"]
    bot_trades = [t for t in trades
                  if t.get("symbol") == "INTARIAN_PEPPER_ROOT"
                  and t.get("buyer") != "SUBMISSION"
                  and t.get("seller") != "SUBMISSION"]

    # Build L1 lookup per timestamp
    l1 = {}
    for r in pepper_rows:
        try:
            ts = int(r[idx["timestamp"]])
            bb = int(r[idx["bid_price_1"]]) if r[idx["bid_price_1"]] else None
            ba = int(r[idx["ask_price_1"]]) if r[idx["ask_price_1"]] else None
            l1[ts] = (bb, ba)
        except Exception:
            pass

    # Classify own trades passive vs aggressive
    pass_buy_u = agg_buy_u = pass_sell_u = agg_sell_u = 0
    for t in own_buys:
        ts = int(t["timestamp"])
        bb_ba = l1.get(ts)
        if not bb_ba or bb_ba[1] is None:
            continue
        if t["price"] >= bb_ba[1]:
            agg_buy_u += t["quantity"]
        else:
            pass_buy_u += t["quantity"]
    for t in own_sells:
        ts = int(t["timestamp"])
        bb_ba = l1.get(ts)
        if not bb_ba or bb_ba[0] is None:
            continue
        if t["price"] <= bb_ba[0]:
            agg_sell_u += t["quantity"]
        else:
            pass_sell_u += t["quantity"]

    # Position trajectory (position field not directly in activities → compute from trades)
    pos = 0
    pos_max, pos_min = 0, 0
    trades_sorted = sorted(
        [t for t in trades if t.get("symbol") == "INTARIAN_PEPPER_ROOT"
         and (t.get("buyer") == "SUBMISSION" or t.get("seller") == "SUBMISSION")],
        key=lambda x: x["timestamp"],
    )
    for t in trades_sorted:
        if t["buyer"] == "SUBMISSION":
            pos += t["quantity"]
        else:
            pos -= t["quantity"]
        pos_max = max(pos_max, pos)
        pos_min = min(pos_min, pos)

    # Quote placement (lambdaLog) — count levels AT L1 vs INSIDE vs BEHIND
    logs = data.get("logs", [])
    import re
    bid_re = re.compile(r"\bb=\[([^\]]*)\]\s+a=\[([^\]]*)\]")
    n_at_l1_bid = n_inside_bid = n_behind_bid = 0
    n_at_l1_ask = n_inside_ask = n_behind_ask = 0
    tight_bid_at_mid = 0
    tight_ask_at_mid = 0
    n_ticks_quoted = 0
    for entry in logs:
        ll = entry.get("lambdaLog", "")
        ts = entry.get("timestamp")
        m = bid_re.search(ll)
        if not m or ts not in l1:
            continue
        bb, ba = l1[ts]
        if bb is None or ba is None:
            continue
        mid = (bb + ba) / 2
        bid_levels = [int(x) for x in m.group(1).split(",") if x.strip()]
        ask_levels = [int(x) for x in m.group(2).split(",") if x.strip()]
        if not bid_levels or not ask_levels:
            continue
        n_ticks_quoted += 1
        for px in bid_levels:
            if px > bb: n_inside_bid += 1
            elif px == bb: n_at_l1_bid += 1
            else: n_behind_bid += 1
        for px in ask_levels:
            if px < ba: n_inside_ask += 1
            elif px == ba: n_at_l1_ask += 1
            else: n_behind_ask += 1
        # Tight = highest bid / lowest ask
        if abs(max(bid_levels) - mid) <= 0.5:
            tight_bid_at_mid += 1
        if abs(min(ask_levels) - mid) <= 0.5:
            tight_ask_at_mid += 1

    return {
        "label": label,
        "final_pnl": final_pnl,
        "n_ticks": n_ticks,
        "n_own_buys": len(own_buys),
        "n_own_sells": len(own_sells),
        "n_bot_trades": len(bot_trades),
        "pass_buy_u": pass_buy_u,
        "agg_buy_u": agg_buy_u,
        "pass_sell_u": pass_sell_u,
        "agg_sell_u": agg_sell_u,
        "pos_max": pos_max,
        "pos_min": pos_min,
        "pos_final": pos,
        "n_ticks_quoted": n_ticks_quoted,
        "n_at_l1_bid": n_at_l1_bid,
        "n_inside_bid": n_inside_bid,
        "n_behind_bid": n_behind_bid,
        "n_at_l1_ask": n_at_l1_ask,
        "n_inside_ask": n_inside_ask,
        "n_behind_ask": n_behind_ask,
        "tight_bid_at_mid": tight_bid_at_mid,
        "tight_ask_at_mid": tight_ask_at_mid,
    }


def fmt_row(v4: dict, v7: dict, key: str, label: str, fmt: str = "d") -> None:
    a = v4[key]
    b = v7[key]
    try:
        delta = b - a
        delta_s = f"{delta:+.0f}" if fmt == "d" else f"{delta:+.2f}"
    except Exception:
        delta_s = ""
    if fmt == "d":
        print(f"  {label:30s}  v4={a:>8d}  v7={b:>8d}   Δ={delta_s}")
    else:
        print(f"  {label:30s}  v4={a:>8.2f}  v7={b:>8.2f}   Δ={delta_s}")


def fmt_row3(v4: dict, v7: dict, v72: dict, key: str, label: str, fmt: str = "d") -> None:
    a, b, c = v4[key], v7[key], v72[key]
    if fmt == "d":
        print(f"  {label:30s}  v4={a:>7d}  v7={b:>7d}  v7.2={c:>7d}")
    else:
        print(f"  {label:30s}  v4={a:>7.2f}  v7={b:>7.2f}  v7.2={c:>7.2f}")


def main() -> None:
    v4 = stats(HERE / "backtestprosperity" / "180495" / "180495.log", "v4 (180495)")
    v7 = stats(HERE / "backtestprosperity" / "196083" / "196083.log", "v7 (196083)")
    v72 = stats(HERE / "backtestprosperity" / "222492" / "222492.log", "v7.2 (222492)")

    print("=" * 78)
    print("Official Prosperity — v4 (180495) | v7 (196083) | v7.2 (222492)")
    print("=" * 78)
    fmt_row3(v4, v7, v72, "final_pnl", "final PnL", "f")
    fmt_row3(v4, v7, v72, "n_ticks", "activity ticks")
    print()
    print("── Trades ─────────────────────────────────────────────────────────")
    fmt_row3(v4, v7, v72, "n_own_buys", "own BUY orders (count)")
    fmt_row3(v4, v7, v72, "n_own_sells", "own SELL orders (count)")
    fmt_row3(v4, v7, v72, "n_bot_trades", "bot-to-bot trades")
    fmt_row3(v4, v7, v72, "pass_buy_u", "passive buy units")
    fmt_row3(v4, v7, v72, "agg_buy_u", "aggressive buy units")
    fmt_row3(v4, v7, v72, "pass_sell_u", "passive sell units")
    fmt_row3(v4, v7, v72, "agg_sell_u", "aggressive sell units")
    print()
    print("── Position ───────────────────────────────────────────────────────")
    fmt_row3(v4, v7, v72, "pos_max", "max pos reached")
    fmt_row3(v4, v7, v72, "pos_min", "min pos reached")
    fmt_row3(v4, v7, v72, "pos_final", "final position")
    print()
    print("── Quote placement ───────────────────────────────────────────────")
    fmt_row3(v4, v7, v72, "n_ticks_quoted", "ticks with quotes")
    fmt_row3(v4, v7, v72, "n_at_l1_bid", "bid levels AT L1")
    fmt_row3(v4, v7, v72, "n_inside_bid", "bid levels INSIDE spread")
    fmt_row3(v4, v7, v72, "n_behind_bid", "bid levels BEHIND L1")
    fmt_row3(v4, v7, v72, "n_at_l1_ask", "ask levels AT L1")
    fmt_row3(v4, v7, v72, "n_inside_ask", "ask levels INSIDE spread")
    fmt_row3(v4, v7, v72, "n_behind_ask", "ask levels BEHIND L1")
    fmt_row3(v4, v7, v72, "tight_bid_at_mid", "ticks with tight bid ≈ mid")
    fmt_row3(v4, v7, v72, "tight_ask_at_mid", "ticks with tight ask ≈ mid")


if __name__ == "__main__":
    main()
