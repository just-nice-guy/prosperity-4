"""
Independent-signal strength across horizons for PEPPER_ROOT.
Outputs: univariate IC and unique (semi-partial) R^2 at k in {1,5,10,20,50,100,200}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_FILES = {
    -2: "prices_round_1_day_-2.csv",
    -1: "prices_round_1_day_-1.csv",
     0: "prices_round_1_day_0.csv",
}
TRADE_FILES = {
    -2: "trades_round_1_day_-2.csv",
    -1: "trades_round_1_day_-1.csv",
     0: "trades_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"
HORIZONS = [1, 5, 10, 20, 50, 100, 200]


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

    feats = []
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
        dd["dmid_prev"] = dd["mid"].diff().fillna(0.0)
        for k in HORIZONS:
            dd[f"ret_{k}"] = dd["mid"].shift(-k) - dd["mid"]
        dd["bounce_sig"] = -dd["dmid_prev"]
        dd["neg_jump"] = np.where(dd["dmid_prev"] < -4, -dd["dmid_prev"], 0.0)
        dd["pos_jump"] = np.where(dd["dmid_prev"] > 4, -dd["dmid_prev"], 0.0)

        tr_day = tr[tr["day_num"] == day].sort_values("timestamp")
        if not tr_day.empty:
            merged = pd.merge_asof(tr_day, dd[["timestamp", "mid"]], on="timestamp", direction="backward")
            merged["sign"] = np.sign(merged["price"] - merged["mid"])
            merged = merged[["timestamp", "sign"]].rename(columns={"timestamp": "trade_ts"})
            aligned = pd.merge_asof(dd.sort_values("timestamp"), merged,
                                    left_on="timestamp", right_on="trade_ts", direction="backward")
            aligned["trade_sign_recent"] = np.where(
                (aligned["timestamp"] - aligned["trade_ts"]) <= 3000, aligned["sign"], 0.0)
            dd = aligned.sort_values("timestamp").reset_index(drop=True)
        else:
            dd["trade_sign_recent"] = 0.0
        feats.append(dd)
    return pd.concat(feats, ignore_index=True)


def ols_r2(X, y):
    Xc = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    pred = Xc @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1 - ss_res / ss_tot


def main():
    df = build_features().dropna(subset=[f"ret_{max(HORIZONS)}"]).reset_index(drop=True)
    signals = ["imb1", "micro_dev", "bounce_sig", "neg_jump", "pos_jump", "trade_sign_recent"]

    # Univariate IC
    print("\n=== Univariate IC: correlation(signal, ret_fwd_k) ===")
    hdr = f"{'signal':22s} | " + " | ".join(f"k={k:>3d}" for k in HORIZONS)
    print(hdr)
    print("-" * len(hdr))
    for s in signals:
        row = [f"{s:22s}"]
        for k in HORIZONS:
            c = float(np.corrcoef(df[s], df[f"ret_{k}"])[0, 1])
            row.append(f"{c:+.3f}")
        print(" | ".join(row))

    # Joint R^2
    X = df[signals].to_numpy()
    print("\n=== Joint OLS R^2 per horizon (all 6 signals) ===")
    for k in HORIZONS:
        y = df[f"ret_{k}"].to_numpy()
        r2 = ols_r2(X, y)
        print(f"  k={k:>3d}  R^2 = {r2:.4f}")

    # Semi-partial (unique) R^2 per signal per horizon
    print("\n=== Unique R^2 of each signal per horizon (semi-partial) ===")
    hdr = f"{'signal':22s} | " + " | ".join(f"k={k:>3d}" for k in HORIZONS)
    print(hdr)
    print("-" * len(hdr))
    for s in signals:
        keep = [c for c in signals if c != s]
        row = [f"{s:22s}"]
        for k in HORIZONS:
            y = df[f"ret_{k}"].to_numpy()
            r2_full = ols_r2(X, y)
            r2_without = ols_r2(df[keep].to_numpy(), y)
            row.append(f"+{(r2_full - r2_without):.4f}")
        print(" | ".join(row))

    # Minimal 2-feature model: imb1 + micro_dev
    print("\n=== Minimal model: [imb1, micro_dev] only ===")
    Xm = df[["imb1", "micro_dev"]].to_numpy()
    for k in HORIZONS:
        y = df[f"ret_{k}"].to_numpy()
        r2 = ols_r2(Xm, y)
        print(f"  k={k:>3d}  R^2 = {r2:.4f}")


if __name__ == "__main__":
    main()
