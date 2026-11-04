"""Holistic analysis of v7.2 (222492) vs v4 (180495) — diagnose remaining gap."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).resolve().parent


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def parse_acts(data: dict) -> tuple[list[dict], dict]:
    """Return pepper rows and L1 lookup by ts."""
    act = data.get("activitiesLog", "")
    rows = [line.split(";") for line in act.strip().split("\n")]
    header = rows[0]
    idx = {n: i for i, n in enumerate(header)}
    pepper = []
    l1 = {}
    for r in rows[1:]:
        if len(r) < 3 or r[2] != "INTARIAN_PEPPER_ROOT":
            continue
        try:
            ts = int(r[idx["timestamp"]])
            row = {
                "ts": ts,
                "bb": int(r[idx["bid_price_1"]]) if r[idx["bid_price_1"]] else None,
                "ba": int(r[idx["ask_price_1"]]) if r[idx["ask_price_1"]] else None,
                "bb2": int(r[idx["bid_price_2"]]) if r[idx["bid_price_2"]] else None,
                "ba2": int(r[idx["ask_price_2"]]) if r[idx["ask_price_2"]] else None,
                "bv1": int(r[idx["bid_volume_1"]]) if r[idx["bid_volume_1"]] else 0,
                "av1": int(r[idx["ask_volume_1"]]) if r[idx["ask_volume_1"]] else 0,
                "mid": float(r[idx["mid_price"]]) if r[idx["mid_price"]] else 0.0,
                "pnl": float(r[idx["profit_and_loss"]]),
            }
            pepper.append(row)
            l1[ts] = row
        except Exception:
            continue
    return pepper, l1


def parse_lambda(data: dict, l1: dict) -> list[dict]:
    """Parse lambdaLog into per-tick state."""
    import re
    bid_re = re.compile(r"\bb=\[([^\]]*)\]\s+a=\[([^\]]*)\]")
    fav_re = re.compile(r"fav=([+-]?\d+)")
    bspike_re = re.compile(r"bspike=([\d.]+)/([\d.]+)/([\d.]+)")
    adrop_re = re.compile(r"adrop=([\d.]+)/([\d.]+)/([\d.]+)")
    take_re = re.compile(r"(PATH_[A-Z_]+\([^)]*\))")
    state_re = re.compile(r"\b(BIDTRAP|ASKTRAP|CB-IMB|CB-BSPIKE|CB-ADROP)\b")
    L_re = re.compile(r"\bL=([+-]?[\d.]+)")
    pos_re = re.compile(r"\bpos=([+-]?\d+)")
    snaps = []
    for entry in data.get("logs", []):
        ll = entry.get("lambdaLog", "")
        ts = entry.get("timestamp")
        if ts is None or ts not in l1:
            continue
        m = bid_re.search(ll)
        if not m:
            continue
        bid_levels = [int(x) for x in m.group(1).split(",") if x.strip()]
        ask_levels = [int(x) for x in m.group(2).split(",") if x.strip()]
        snaps.append({
            "ts": ts,
            "bid_levels": bid_levels,
            "ask_levels": ask_levels,
            "fav": int(fav_re.search(ll).group(1)) if fav_re.search(ll) else 0,
            "bspike": [float(x) for x in bspike_re.search(ll).groups()] if bspike_re.search(ll) else None,
            "adrop": [float(x) for x in adrop_re.search(ll).groups()] if adrop_re.search(ll) else None,
            "take": take_re.search(ll).group(1) if take_re.search(ll) else "",
            "states": state_re.findall(ll),
            "L": float(L_re.search(ll).group(1)) if L_re.search(ll) else None,
            "pos": int(pos_re.search(ll).group(1)) if pos_re.search(ll) else None,
        })
    return snaps


def classify_trades(data: dict, l1: dict) -> dict:
    """Classify our trades vs L1."""
    trades = data.get("tradeHistory", [])
    own = [t for t in trades
           if t.get("symbol") == "INTARIAN_PEPPER_ROOT"
           and (t.get("buyer") == "SUBMISSION" or t.get("seller") == "SUBMISSION")]

    classes = defaultdict(list)
    for t in own:
        ts = int(t["timestamp"])
        l = l1.get(ts)
        if not l or l["bb"] is None or l["ba"] is None:
            continue
        is_buy = t["buyer"] == "SUBMISSION"
        if is_buy:
            if t["price"] >= l["ba"]:
                # took L1 ask exactly?
                if t["price"] == l["ba"]:
                    classes["agg_buy_L1"].append(t)
                else:
                    classes["agg_buy_deeper"].append(t)  # deeper than L1 ask = bad
            else:
                classes["pass_buy"].append(t)
        else:
            if t["price"] <= l["bb"]:
                if t["price"] == l["bb"]:
                    classes["agg_sell_L1"].append(t)
                else:
                    classes["agg_sell_deeper"].append(t)  # below L1 bid = sold into L2 = bad
            else:
                classes["pass_sell"].append(t)
    return classes


def position_traj(data: dict) -> list[tuple[int, int]]:
    trades = sorted(
        [t for t in data.get("tradeHistory", [])
         if t.get("symbol") == "INTARIAN_PEPPER_ROOT"
         and (t.get("buyer") == "SUBMISSION" or t.get("seller") == "SUBMISSION")],
        key=lambda x: x["timestamp"],
    )
    pos = 0
    traj = []
    for t in trades:
        if t["buyer"] == "SUBMISSION":
            pos += t["quantity"]
        else:
            pos -= t["quantity"]
        traj.append((int(t["timestamp"]), pos))
    return traj


def main() -> None:
    for label, fname, subdir in [
        ("v4 (180495)", "180495.log", "backtestprosperity/180495"),
        ("v7.2 (222492)", "222492.log", "backtestprosperity/222492"),
        ("v8 (227963)", "227963.log", "backtestprosperity/227963"),
    ]:
        d = load(HERE / subdir / fname)
        pepper, l1 = parse_acts(d)
        snaps = parse_lambda(d, l1)
        cls = classify_trades(d, l1)
        traj = position_traj(d)

        print("=" * 78)
        print(f"  {label}")
        print("=" * 78)
        final_pnl = pepper[-1]["pnl"] if pepper else 0
        print(f"  Final PnL: {final_pnl:.2f}")
        print(f"  Final pos: {traj[-1][1] if traj else 0}")
        print()
        print("  TRADE QUALITY (vs L1 at trade ts):")
        for k in ["pass_buy", "agg_buy_L1", "agg_buy_deeper",
                  "pass_sell", "agg_sell_L1", "agg_sell_deeper"]:
            ts_list = cls.get(k, [])
            qty = sum(int(t["quantity"]) for t in ts_list)
            avg_px = sum(t["price"] * t["quantity"] for t in ts_list) / max(1, qty) if ts_list else 0.0
            tag = "⚠" if "deeper" in k and qty > 0 else " "
            print(f"   {tag} {k:25s}  n={len(ts_list):>3d}  qty={qty:>4d}  avg_px={avg_px:>9.2f}")

        # Path B / Path C activity
        path_b_heavy = [s for s in snaps if "PATH_B_HEAVY" in s["take"]]
        path_b_light = [s for s in snaps if "PATH_B_LIGHT" in s["take"]]
        path_c = [s for s in snaps if "PATH_C_DERISK" in s["take"]]
        print()
        print(f"  PATHS FIRED:")
        print(f"    Path B HEAVY (≥3σ ask_drop solo):  {len(path_b_heavy)}")
        print(f"    Path B LIGHT (≥2σ ask_drop+imb):   {len(path_b_light)}")
        print(f"    Path C (derisk on bid_spike):      {len(path_c)}")

        # Missed opportunities: ticks where ask_drop ≥ heavy threshold but no take
        missed = []
        for s in snaps:
            if s["fav"] != 1 or s["adrop"] is None:
                continue
            adrop, light, heavy = s["adrop"]
            if adrop >= heavy and not s["take"]:
                missed.append((s["ts"], adrop, heavy, s.get("pos")))
        print(f"    MISSED heavy ask_drops in fav=+1:  {len(missed)}")
        if missed[:5]:
            for ts, adrop, heavy, pos in missed[:5]:
                print(f"      ts={ts}  adrop={adrop:.1f} (≥{heavy:.1f})  pos={pos}")

        # Aggressive sell quality (Path C)
        agg_deep = cls.get("agg_sell_deeper", [])
        if agg_deep:
            print()
            print(f"  ⚠ AGGRESSIVE SELLS DEEPER THAN L1 BID (sold into L2):")
            for t in agg_deep[:8]:
                ts = int(t["timestamp"])
                l = l1.get(ts)
                slip = l["bb"] - t["price"] if l else 0
                print(f"      ts={ts}  px={t['price']}  L1_bid={l['bb']}  slip=-{slip}  qty={t['quantity']}")
        print()


if __name__ == "__main__":
    main()
