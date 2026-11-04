"""
Independence analysis of PEPPER_ROOT signals.

For each candidate signal, measure:
  - univariate IC (correlation with forward return at k=1 and k=10)
  - pairwise correlation between signals
  - joint multivariate OLS fit (marginal contribution)
  - forward selection R^2 (which signal adds most on top of the rest)
  - semi-partial correlation (unique IC after controlling for everything else)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STAGE1 = "."
PRICE_FILES = {
    -2: f"{STAGE1}/prices_round_1_day_-2.csv",
    -1: f"{STAGE1}/prices_round_1_day_-1.csv",
     0: f"{STAGE1}/prices_round_1_day_0.csv",
}
TRADE_FILES = {
    -2: f"{STAGE1}/trades_round_1_day_-2.csv",
    -1: f"{STAGE1}/trades_round_1_day_-1.csv",
     0: f"{STAGE1}/trades_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"


def load_prices():
    dfs = []
    for day, f in PRICE_FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d = d[d["product"] == PRODUCT].copy()
        d["day_num"] = day
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    ok = df["bid_price_1"].notna() & df["ask_price_1"].notna()
    return df[ok].reset_index(drop=True)


def load_trades():
    dfs = []
    for day, f in TRADE_FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d = d[d["symbol"] == PRODUCT].copy()
        d["day_num"] = day
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def build_features():
    d = load_prices()
    tr = load_trades()

    d["mid"] = (d["bid_price_1"] + d["ask_price_1"]) / 2
    d["spread"] = d["ask_price_1"] - d["bid_price_1"]

    bv1 = d["bid_volume_1"].fillna(0)
    av1 = d["ask_volume_1"].fillna(0)
    d["imb1"] = (bv1 - av1) / (bv1 + av1 + 1e-12)
    d["micro"] = (bv1 * d["ask_price_1"] + av1 * d["bid_price_1"]) / (bv1 + av1 + 1e-12)
    d["micro_dev"] = d["micro"] - d["mid"]

    # Merge trade-sign signal: last Lee-Ready-signed trade price relative to mid, within 30 ticks
    feats = []
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
        dd["dmid_prev"] = dd["mid"].diff().fillna(0.0)

        # Forward returns
        dd["ret_fwd_1"] = dd["mid"].shift(-1) - dd["mid"]
        dd["ret_fwd_10"] = dd["mid"].shift(-10) - dd["mid"]

        # Bid-ask bounce reversal: expected next-move is opposite to previous
        dd["bounce_sig"] = -dd["dmid_prev"]

        # Asymmetric jump recovery: activates strongly on negative jumps
        dd["neg_jump"] = np.where(dd["dmid_prev"] < -4, -dd["dmid_prev"], 0.0)
        dd["pos_jump"] = np.where(dd["dmid_prev"] > 4, -dd["dmid_prev"], 0.0)

        # Trade-sign signal: most recent signed trade within last 30 ticks
        tr_day = tr[tr["day_num"] == day].sort_values("timestamp").copy()
        if not tr_day.empty:
            merged = pd.merge_asof(tr_day, dd[["timestamp", "mid"]], on="timestamp", direction="backward")
            merged["sign"] = np.sign(merged["price"] - merged["mid"])
            merged = merged[["timestamp", "sign"]].rename(columns={"timestamp": "trade_ts"})
            # For each book snapshot, find the latest trade at or before it
            dd_sorted = dd.sort_values("timestamp")
            aligned = pd.merge_asof(
                dd_sorted, merged,
                left_on="timestamp", right_on="trade_ts",
                direction="backward")
            aligned["trade_sign_recent"] = np.where(
                (aligned["timestamp"] - aligned["trade_ts"]) <= 3000, aligned["sign"], 0.0
            )
            dd = aligned.sort_values("timestamp").reset_index(drop=True)
        else:
            dd["trade_sign_recent"] = 0.0

        feats.append(dd)

    full = pd.concat(feats, ignore_index=True)

    # Clean: drop tail rows with NaN targets and early rows with NaN prev
    full = full.dropna(subset=["ret_fwd_1", "ret_fwd_10"]).reset_index(drop=True)
    return full


def ols(X, y):
    Xc = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    pred = Xc @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot
    return beta, r2


def main():
    df = build_features()
    print(f"n = {len(df)}")

    # ── Candidate signals ────────────────────────────────────────────
    signal_cols = [
        "imb1",
        "micro_dev",
        "bounce_sig",
        "neg_jump",
        "pos_jump",
        "trade_sign_recent",
    ]
    targets = {"ret_fwd_1": "1 tick ahead", "ret_fwd_10": "10 ticks ahead"}

    for target, label in targets.items():
        y = df[target].to_numpy()
        print("\n" + "=" * 76)
        print(f"TARGET: {target}  ({label})   n={len(df)}  target std={y.std():.3f}")
        print("=" * 76)

        # Univariate IC
        print("\n[1] Univariate IC (pearson correlation)")
        univ = {}
        for s in signal_cols:
            x = df[s].to_numpy()
            c = float(np.corrcoef(x, y)[0, 1])
            univ[s] = c
            print(f"    {s:22s}  IC = {c:+.4f}   R^2 = {c*c:.4f}")

        # Pairwise correlation matrix of signals
        print("\n[2] Pairwise signal correlation")
        hdr = "                        " + "  ".join(f"{s[:10]:>10s}" for s in signal_cols)
        print(hdr)
        for s1 in signal_cols:
            row = []
            for s2 in signal_cols:
                c = float(np.corrcoef(df[s1], df[s2])[0, 1])
                row.append(f"{c:>+10.3f}")
            print(f"    {s1:22s}" + "  ".join(row))

        # Joint OLS
        X = df[signal_cols].to_numpy()
        beta, r2_full = ols(X, y)
        print("\n[3] Joint OLS all signals")
        print(f"    R^2 = {r2_full:.4f}")
        print("    Coefficients (standardized by signal std):")
        for name, b, col in zip(signal_cols, beta[1:], X.T):
            std_effect = float(b * col.std())
            print(f"       {name:22s}  beta={b:+.4f}  impact(1 std) = {std_effect:+.4f}")

        # Forward selection: add signals one by one by greedy R^2 gain
        print("\n[4] Forward selection (greedy add-one)")
        remaining = list(signal_cols)
        selected = []
        r2_prev = 0.0
        while remaining:
            best = None
            best_r2 = -1
            for c in remaining:
                trial = selected + [c]
                _, r2 = ols(df[trial].to_numpy(), y)
                if r2 > best_r2:
                    best_r2 = r2
                    best = c
            marginal = best_r2 - r2_prev
            print(f"    + {best:22s}  R^2 = {best_r2:.4f}   delta = +{marginal:.4f}")
            selected.append(best)
            remaining.remove(best)
            r2_prev = best_r2

        # Semi-partial correlation: unique IC after controlling for everything else
        print("\n[5] Semi-partial (unique) R^2 of each signal")
        for drop in signal_cols:
            keep = [c for c in signal_cols if c != drop]
            _, r2_without = ols(df[keep].to_numpy(), y)
            unique = r2_full - r2_without
            print(f"    {drop:22s}  R^2 without = {r2_without:.4f}   unique R^2 = {unique:+.4f}")


if __name__ == "__main__":
    main()
