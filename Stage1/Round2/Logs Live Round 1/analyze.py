"""
Deep holistic analysis of official Round 1 eval-day live log 272279.

Parses activitiesLog (per-product book+PnL time series), sandboxLog
(trader stdout per tick), and graphLog (total PnL curve) to characterize:
  - per-product PnL progression (decile view, gain rate)
  - regime transitions (drift, spread, vol)
  - trader path firings (from sandboxLog prints by traderv10 / moyen2)
  - own trade aggregates (from tick-level trades reported in sandboxLog)
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, stdev

LOG = Path(__file__).parent / "272279.json"


def parse_activities(al: str) -> dict:
    lines = al.split("\n")
    header = lines[0].split(";")
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        parts = ln.split(";")
        if len(parts) < 17:
            continue
        rows.append(dict(zip(header, parts)))

    def _opt_int(x):
        return int(x) if x else None

    def _opt_float(x):
        return float(x) if x else None

    per_prod: dict[str, list[dict]] = {}
    for r in rows:
        r["ts"] = int(r["timestamp"])
        r["mid"] = _opt_float(r["mid_price"])
        r["pnl"] = float(r["profit_and_loss"]) if r["profit_and_loss"] else 0.0
        r["bp1"] = _opt_int(r["bid_price_1"])
        r["ap1"] = _opt_int(r["ask_price_1"])
        r["bv1"] = _opt_int(r["bid_volume_1"])
        r["av1"] = _opt_int(r["ask_volume_1"])
        r["spread"] = (r["ap1"] - r["bp1"]) if r["bp1"] and r["ap1"] else None
        per_prod.setdefault(r["product"], []).append(r)
    for p in per_prod:
        per_prod[p].sort(key=lambda x: x["ts"])
    return per_prod


def summarize(series: list[dict], name: str) -> None:
    print(f"\n=== {name} ===")
    mids = [r["mid"] for r in series if r["mid"] is not None]
    spreads = [r["spread"] for r in series if r["spread"] is not None]
    pnls = [r["pnl"] for r in series]
    start_mid = series[0]["mid"]
    end_mid = series[-1]["mid"]
    print(f"  ticks     : {len(series)}")
    print(f"  mid       : start={start_mid:.1f} end={end_mid:.1f} delta={end_mid - start_mid:+.1f}")
    print(f"  mid range : min={min(mids):.1f} max={max(mids):.1f} mean={mean(mids):.1f} std={stdev(mids):.2f}")
    print(f"  spread    : min={min(spreads)} max={max(spreads)} mean={mean(spreads):.2f}")
    print(f"  pnl       : min={min(pnls):.1f} max={max(pnls):.1f} final={pnls[-1]:.1f}")

    # Decile progression
    print("  decile progression:")
    print(f"    {'pct':>5} {'ts':>8} {'mid':>9} {'pnl':>10} {'gain':>9} {'spd':>4}")
    n = len(series)
    prev = 0.0
    for i in range(10):
        idx = (i + 1) * n // 10 - 1
        r = series[idx]
        gain = r["pnl"] - prev
        spd = r["spread"] if r["spread"] is not None else "-"
        print(f"    {i*10+10:>4}% {r['ts']:>8} {r['mid']:>9.1f} {r['pnl']:>10.1f} {gain:>+9.1f} {spd:>4}")
        prev = r["pnl"]

    # Rolling stats: drift per 1000 ticks, vol per 1000 ticks
    print("  per-kt drift / vol (window=1000 ticks):")
    print(f"    {'kt':>4} {'ts_end':>8} {'dmid':>8} {'std_dmid':>9} {'mean_spd':>9}")
    for b in range(10):
        lo = b * 1000
        hi = (b + 1) * 1000
        chunk = series[lo:hi]
        if not chunk:
            continue
        ms = [r["mid"] for r in chunk if r["mid"] is not None]
        ss = [r["spread"] for r in chunk if r["spread"] is not None]
        dmid = ms[-1] - ms[0]
        diffs = [ms[i + 1] - ms[i] for i in range(len(ms) - 1)]
        vol = stdev(diffs) if len(diffs) > 1 else 0.0
        print(
            f"    {b+1:>4} {chunk[-1]['ts']:>8} {dmid:>+8.1f} {vol:>9.3f} {mean(ss):>9.2f}"
        )


def parse_sandbox(raw: str) -> list[dict]:
    """
    sandboxLog format: JSON-lines, each with sandboxLog / lambdaLog / timestamp.
    lambdaLog is the trader's stdout (from logger.flush in traderv10).
    """
    entries = []
    # Each entry is concatenated JSON objects
    depth = 0
    buf = []
    for ch in raw:
        buf.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                txt = "".join(buf).strip()
                buf = []
                try:
                    entries.append(json.loads(txt))
                except Exception:
                    pass
    return entries


def main() -> None:
    data = json.loads(LOG.read_text(encoding="utf-8"))

    print(f"round       : {data['round']}")
    print(f"status      : {data['status']}")
    print(f"profit      : {data['profit']}")
    print(f"positions   : {data['positions']}")

    per_prod = parse_activities(data["activitiesLog"])
    for name, series in per_prod.items():
        summarize(series, name)

    # graphLog = total PnL per timestamp
    gl = data.get("graphLog", "")
    gl_lines = [ln for ln in gl.split("\n") if ";" in ln and not ln.startswith("timestamp")]
    gl_pts = []
    for ln in gl_lines:
        ts, v = ln.split(";")
        try:
            gl_pts.append((int(ts), float(v)))
        except Exception:
            pass
    if gl_pts:
        print("\n=== TOTAL (from graphLog) ===")
        print(f"  points    : {len(gl_pts)}")
        print(f"  start/end : {gl_pts[0][1]:.1f} -> {gl_pts[-1][1]:.1f}")
        # Decile
        n = len(gl_pts)
        print("  decile:")
        print(f"    {'pct':>5} {'ts':>8} {'pnl':>12} {'gain':>10}")
        prev = 0.0
        for i in range(10):
            idx = (i + 1) * n // 10 - 1
            ts, v = gl_pts[idx]
            print(f"    {i*10+10:>4}% {ts:>8} {v:>12.2f} {v - prev:>+10.2f}")
            prev = v


if __name__ == "__main__":
    main()
