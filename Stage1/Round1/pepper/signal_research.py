"""
Signal research — IMBALANCE vs SPIKE/BOUNCE for INTARIAN_PEPPER_ROOT.

Methodology: empirical distribution + IC at multiple horizons + interaction
matrix + failure-mode characterisation. Pure observation on the 3 historical
days, no overfitting.
"""
from __future__ import annotations

import math
import statistics as st
from collections import Counter

import numpy as np
import pandas as pd

PRICE_FILES = {
    -2: "prices_round_1_day_-2.csv",
    -1: "prices_round_1_day_-1.csv",
     0: "prices_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"
LAM_EMA = 0.9    # EWMA lambda for ask/bid price tracking
HORIZONS = [1, 5, 20, 50]


def load_data() -> pd.DataFrame:
    dfs = []
    for d, f in PRICE_FILES.items():
        df = pd.read_csv(f, delimiter=";")
        df = df[df["product"] == PRODUCT].copy()
        df["day_num"] = d
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    ok = df["bid_price_1"].notna() & df["ask_price_1"].notna()
    df = df[ok].reset_index(drop=True)
    df["mid"] = (df["bid_price_1"] + df["ask_price_1"]) / 2
    df["spread"] = df["ask_price_1"] - df["bid_price_1"]
    return df


def build_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute imbalance and ask_drop / bid_spike per row."""
    out = df.copy()

    # Per-day computation (no leakage across days)
    sub_dfs = []
    for day_num, sub in out.groupby("day_num"):
        sub = sub.sort_values("timestamp").reset_index(drop=True)

        # Signal 1: imbalance
        bv = sub["bid_volume_1"].fillna(0)
        av = sub["ask_volume_1"].fillna(0)
        sub["imb"] = (bv - av) / (bv + av + 1e-12)

        # Signal 2: ask drop / bid spike via EWMA
        ask_ema = sub["ask_price_1"].ewm(alpha=1 - LAM_EMA, adjust=False).mean().shift(1)
        bid_ema = sub["bid_price_1"].ewm(alpha=1 - LAM_EMA, adjust=False).mean().shift(1)
        sub["ask_ema"] = ask_ema
        sub["bid_ema"] = bid_ema
        sub["ask_drop"] = (ask_ema - sub["ask_price_1"]).clip(lower=0)
        sub["bid_spike"] = (sub["bid_price_1"] - bid_ema).clip(lower=0)
        sub["ask_pop"] = (sub["ask_price_1"] - ask_ema).clip(lower=0)  # ask going up
        sub["bid_drop"] = (bid_ema - sub["bid_price_1"]).clip(lower=0)  # bid going down

        sub_dfs.append(sub)

    out = pd.concat(sub_dfs, ignore_index=True)

    # Forward returns
    out_dfs = []
    for day_num, sub in out.groupby("day_num"):
        sub = sub.sort_values("timestamp").reset_index(drop=True)
        for h in HORIZONS:
            sub[f"ret_{h}"] = sub["mid"].shift(-h) - sub["mid"]
        out_dfs.append(sub)
    out = pd.concat(out_dfs, ignore_index=True)
    drop_cols = [f"ret_{HORIZONS[-1]}", "ask_ema", "bid_ema",
                 "ask_drop", "bid_spike", "ask_pop", "bid_drop"]
    return out.dropna(subset=drop_cols).reset_index(drop=True)


def section(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def quantiles(s, qs=(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)) -> str:
    arr = np.asarray(s)
    return "[" + ", ".join(f"{np.quantile(arr, q):.3f}" for q in qs) + "]"


def main():
    df = load_data()
    df = build_signals(df)
    print(f"Loaded {len(df)} usable ticks across 3 days")

    # ─────────────────────────────────────────────────────────────────────
    section("[1] Distribution of each signal")
    # ─────────────────────────────────────────────────────────────────────
    for sig in ["imb", "ask_drop", "bid_spike", "ask_pop", "bid_drop"]:
        s = df[sig]
        nz = (s != 0).sum()
        nz_pct = 100 * nz / len(s)
        max_abs = s.abs().max()
        mean = s.mean()
        std = s.std()
        print(f"\n  {sig:12s}  mean={mean:+.4f}  std={std:.4f}  "
              f"max|x|={max_abs:.2f}  nonzero={nz_pct:.1f}%")
        print(f"               quantiles 1/5/25/50/75/95/99: {quantiles(s)}")

    # ─────────────────────────────────────────────────────────────────────
    section("[2] IC = corr(signal_t, dmid_{t+k}) — predictive power")
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{'signal':>12s}  {'k=1':>8s}  {'k=5':>8s}  {'k=20':>8s}  {'k=50':>8s}")
    for sig in ["imb", "ask_drop", "bid_spike", "ask_pop", "bid_drop"]:
        ics = []
        for h in HORIZONS:
            x = df[sig].to_numpy()
            y = df[f"ret_{h}"].to_numpy()
            ic = float(np.corrcoef(x, y)[0, 1])
            ics.append(ic)
        print(f"{sig:>12s}  " + "  ".join(f"{ic:+.4f}" for ic in ics))

    # ─────────────────────────────────────────────────────────────────────
    section("[3] IC of SIGNED variants (drop on ask = bullish, spike on bid = bullish)")
    # ─────────────────────────────────────────────────────────────────────
    # ask_drop_signed = +ask_drop (positive drop -> we expect price up)
    # ask_pop_signed = -ask_pop (positive pop -> ask going up = sell pressure -> down? actually)
    # bid_spike_signed: bid rising can be either bullish (real demand) or fake (spoof)
    print(f"\n{'signed signal':>20s}  {'k=1':>8s}  {'k=5':>8s}  {'k=20':>8s}  {'k=50':>8s}")
    signed = {
        "ask_drop (bullish)": df["ask_drop"],          # high when ask falls
        "ask_pop (bearish)": -df["ask_pop"],            # negative when ask rises
        "bid_spike (bullish)": df["bid_spike"],         # high when bid rises
        "bid_drop (bearish)": -df["bid_drop"],          # negative when bid falls
        "imb (bullish if >0)": df["imb"],
    }
    for name, s in signed.items():
        ics = []
        for h in HORIZONS:
            x = s.to_numpy()
            y = df[f"ret_{h}"].to_numpy()
            ic = float(np.corrcoef(x, y)[0, 1])
            ics.append(ic)
        print(f"{name:>20s}  " + "  ".join(f"{ic:+.4f}" for ic in ics))

    # ─────────────────────────────────────────────────────────────────────
    section("[4] Pairwise correlation between signals")
    # ─────────────────────────────────────────────────────────────────────
    sigs = ["imb", "ask_drop", "bid_spike", "ask_pop", "bid_drop"]
    print(f"\n{'':12s}" + "".join(f"  {s:>10s}" for s in sigs))
    for s1 in sigs:
        row = [f"{s1:12s}"]
        for s2 in sigs:
            c = float(np.corrcoef(df[s1], df[s2])[0, 1])
            row.append(f"  {c:+10.3f}")
        print("".join(row))

    # ─────────────────────────────────────────────────────────────────────
    section("[5] Conditional analysis — when does each signal FAIL?")
    # ─────────────────────────────────────────────────────────────────────

    # Failure mode A: high imb but mid REVERTS (= adverse selection)
    print("\n[5A] IMBALANCE failure: imb>0.3 but next-tick dmid is NEGATIVE")
    for thresh in [0.20, 0.30, 0.40]:
        mask = df["imb"] > thresh
        if mask.sum() < 10:
            continue
        next_dmid = df.loc[mask, "ret_1"]
        n = len(next_dmid)
        n_neg = (next_dmid < 0).sum()
        mean_dmid = next_dmid.mean()
        print(f"  imb > {thresh}:  n={n:>5}  mean dmid={mean_dmid:+.3f}  "
              f"% negative={100*n_neg/n:.1f}%")

    # Failure mode B: ask_drop fires but mid keeps falling (bounce wasn't a bounce)
    print("\n[5B] ASK PLUNGE failure: ask_drop>=3 but next-20 dmid is NEGATIVE")
    for thresh in [2, 3, 5]:
        mask = df["ask_drop"] >= thresh
        if mask.sum() < 10:
            continue
        next_ret = df.loc[mask, "ret_20"]
        n = len(next_ret)
        n_neg = (next_ret < 0).sum()
        mean_ret = next_ret.mean()
        print(f"  ask_drop >= {thresh}:  n={n:>5}  mean ret(20)={mean_ret:+.3f}  "
              f"% negative={100*n_neg/n:.1f}%")

    # Failure mode C: bid_spike (often spoof?)
    print("\n[5C] BID SPIKE behavior: when bid spikes, what does mid do next?")
    for thresh in [2, 3, 5]:
        mask = df["bid_spike"] >= thresh
        if mask.sum() < 10:
            continue
        next_ret_1 = df.loc[mask, "ret_1"]
        next_ret_20 = df.loc[mask, "ret_20"]
        print(f"  bid_spike >= {thresh}:  n={mask.sum():>5}  "
              f"mean ret(1)={next_ret_1.mean():+.3f}  "
              f"mean ret(20)={next_ret_20.mean():+.3f}  "
              f"% next ret(1)<0={(next_ret_1<0).mean()*100:.1f}%")

    # ─────────────────────────────────────────────────────────────────────
    section("[6] INTERACTION — combined signals")
    # ─────────────────────────────────────────────────────────────────────

    # Strongest bullish: imb high AND ask drops
    print("\n[6A] When imb>0.25 AND ask_drop>=2 (combined bullish)")
    mask = (df["imb"] > 0.25) & (df["ask_drop"] >= 2)
    if mask.sum() > 0:
        for h in HORIZONS:
            mean = df.loc[mask, f"ret_{h}"].mean()
            n = mask.sum()
            print(f"  n={n:>5}  ret(k={h:>3}) mean={mean:+.3f}")

    # imb without ask drop (pure imbalance)
    print("\n[6B] When imb>0.25 AND ask_drop==0 (imb only, no plunge)")
    mask = (df["imb"] > 0.25) & (df["ask_drop"] == 0)
    if mask.sum() > 0:
        for h in HORIZONS:
            mean = df.loc[mask, f"ret_{h}"].mean()
            n = mask.sum()
            print(f"  n={n:>5}  ret(k={h:>3}) mean={mean:+.3f}")

    # imb high AND bid spiked (suspect: spoof)
    print("\n[6C] When imb>0.25 AND bid_spike>=2 (suspect spoof)")
    mask = (df["imb"] > 0.25) & (df["bid_spike"] >= 2)
    if mask.sum() > 0:
        for h in HORIZONS:
            mean = df.loc[mask, f"ret_{h}"].mean()
            n = mask.sum()
            print(f"  n={n:>5}  ret(k={h:>3}) mean={mean:+.3f}")

    # imb high AND bid stable (real signal, not spoof)
    print("\n[6D] When imb>0.25 AND bid_spike==0 (clean bullish signal)")
    mask = (df["imb"] > 0.25) & (df["bid_spike"] == 0)
    if mask.sum() > 0:
        for h in HORIZONS:
            mean = df.loc[mask, f"ret_{h}"].mean()
            n = mask.sum()
            print(f"  n={n:>5}  ret(k={h:>3}) mean={mean:+.3f}")

    # ─────────────────────────────────────────────────────────────────────
    section("[7] Multivariate regression — which signal contributes uniquely?")
    # ─────────────────────────────────────────────────────────────────────
    from numpy.linalg import lstsq
    print("\n  Regressing ret_5 on combinations of signals (R² and unique R²)")

    candidates = ["imb", "ask_drop", "bid_spike", "ask_pop", "bid_drop"]
    y = df["ret_5"].to_numpy()

    def r2(X, y):
        Xc = np.column_stack([np.ones(len(X)), X])
        beta, *_ = lstsq(Xc, y, rcond=None)
        pred = Xc @ beta
        ss_res = ((y - pred) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        return 1 - ss_res / ss_tot

    # Univariate
    print("\n  Univariate R²:")
    for s in candidates:
        x = df[s].to_numpy().reshape(-1, 1)
        print(f"    {s:12s}  R² = {r2(x, y):.4f}")

    # Joint
    X_all = df[candidates].to_numpy()
    r2_all = r2(X_all, y)
    print(f"\n  Joint R² (all 5 signals): {r2_all:.4f}")

    # Unique R² of each (semi-partial)
    print("\n  Unique R² (drop one):")
    for drop in candidates:
        keep = [c for c in candidates if c != drop]
        r2_w = r2(df[keep].to_numpy(), y)
        print(f"    drop {drop:12s}  R² without = {r2_w:.4f}   unique = {r2_all - r2_w:+.4f}")

    # ─────────────────────────────────────────────────────────────────────
    section("[8] Frequency of each event")
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{'event':35s}  {'frequency':>12s}  {'%':>8s}")
    events = [
        ("imb > 0.20",                   (df["imb"] > 0.20).sum()),
        ("imb > 0.30",                   (df["imb"] > 0.30).sum()),
        ("imb > 0.40",                   (df["imb"] > 0.40).sum()),
        ("ask_drop >= 2",                (df["ask_drop"] >= 2).sum()),
        ("ask_drop >= 3",                (df["ask_drop"] >= 3).sum()),
        ("ask_drop >= 5",                (df["ask_drop"] >= 5).sum()),
        ("bid_spike >= 2",               (df["bid_spike"] >= 2).sum()),
        ("bid_spike >= 3",               (df["bid_spike"] >= 3).sum()),
        ("imb > 0.25 AND bid_spike >= 2",((df["imb"] > 0.25) & (df["bid_spike"] >= 2)).sum()),
        ("imb > 0.25 AND ask_drop >= 2", ((df["imb"] > 0.25) & (df["ask_drop"] >= 2)).sum()),
    ]
    n = len(df)
    for name, freq in events:
        print(f"  {name:35s}  {freq:>12d}  {100*freq/n:>7.2f}%")


if __name__ == "__main__":
    main()
