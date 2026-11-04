"""
Holistic statistical EDA for INTARIAN_PEPPER_ROOT (Round 1).
Run from Stage1/Round1/:
    python pepper/eda_pepper.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FILES = {
    -2: "prices_round_1_day_-2.csv",
    -1: "prices_round_1_day_-1.csv",
     0: "prices_round_1_day_0.csv",
}
TRADES = {
    -2: "trades_round_1_day_-2.csv",
    -1: "trades_round_1_day_-1.csv",
     0: "trades_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"


def load_prices():
    dfs = []
    for day, f in FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d = d[d["product"] == PRODUCT].copy()
        d["day_num"] = day
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def qs(arr, probs=(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)):
    q = np.quantile(arr, probs)
    return [round(float(v), 3) for v in q]


def skewkurt(x):
    x = np.asarray(x, dtype=float)
    m = x.mean()
    s = x.std()
    if s == 0:
        return 0.0, 0.0
    sk = ((x - m) ** 3).mean() / s ** 3
    ku = ((x - m) ** 4).mean() / s ** 4 - 3
    return sk, ku


def main():
    df = load_prices()
    ok = df["bid_price_1"].notna() & df["ask_price_1"].notna()
    dd = df[ok].copy()
    dd["mid"] = (dd["bid_price_1"] + dd["ask_price_1"]) / 2
    dd["spread"] = dd["ask_price_1"] - dd["bid_price_1"]

    print(f"Total rows: {len(df)}   usable (both sides present): {len(dd)}   "
          f"({len(dd)/len(df)*100:.1f}%)")

    # ── 1. Linear fit per day ─────────────────────────────────────────
    section("[1] Linear fit mid ~ a + b*timestamp per day")
    fits = {}
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day]
        x = d["timestamp"].to_numpy()
        y = d["mid"].to_numpy()
        b, a = np.polyfit(x, y, 1)
        resid = y - (a + b * x)
        fits[day] = (a, b)
        print(f"  day={day}  a={a:12.4f}  b={b:.8f}  resid std={resid.std():.4f}  n={len(d)}")

    dd["a"] = dd["day_num"].map(lambda k: fits[k][0])
    dd["b"] = dd["day_num"].map(lambda k: fits[k][1])
    dd["fv"] = dd["a"] + dd["b"] * dd["timestamp"]
    dd["eps_mid"] = dd["mid"] - dd["fv"]
    dd["eps_bid"] = dd["bid_price_1"] - dd["fv"]
    dd["eps_ask"] = dd["ask_price_1"] - dd["fv"]

    # ── 2. Mid residual distribution ──────────────────────────────────
    section("[2] Residuals of mid vs day-wise linear trend")
    for day in list(sorted(dd["day_num"].unique())) + ["ALL"]:
        d = dd if day == "ALL" else dd[dd["day_num"] == day]
        r = d["eps_mid"].to_numpy()
        sk, ku = skewkurt(r)
        print(f"  day={str(day):>3}  mean={r.mean():+.4f}  std={r.std():.4f}  "
              f"skew={sk:+.3f}  xs-kurt={ku:+.3f}  q[1,5,25,50,75,95,99]={qs(r)}")

    # ── 3. Bid and Ask positioning relative to fv ─────────────────────
    section("[3] Bid and Ask positioning relative to fv  (ALL days)")
    for col, label in [("eps_bid", "bid-fv"), ("eps_ask", "ask-fv"), ("spread", "spread")]:
        r = dd[col].to_numpy()
        print(f"  {label:8s}  mean={r.mean():+.3f}  std={r.std():.3f}  median={np.median(r):+.2f}  q[1,5,25,50,75,95,99]={qs(r)}")

    # ── 4. Residual autocorrelation ───────────────────────────────────
    section("[4] Autocorrelation of eps_mid (mispricing persistence)")
    lags = [1, 2, 5, 10, 20, 50, 100, 200, 500]
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day].sort_values("timestamp")
        r = d["eps_mid"].to_numpy()
        r = r - r.mean()
        den = (r ** 2).sum()
        ac = [round((r[:-lag] * r[lag:]).sum() / den, 3) for lag in lags]
        print(f"  day={day}  lags={lags}")
        print(f"          ac   ={ac}")

    # ── 5. Tick-to-tick return distribution ───────────────────────────
    section("[5] Tick-to-tick mid returns (dmid)")
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day].sort_values("timestamp")
        m = d["mid"].to_numpy()
        dm = np.diff(m)
        sk, ku = skewkurt(dm)
        zeros = int((dm == 0).sum())
        print(f"  day={day}  mean={dm.mean():+.4f}  std={dm.std():.4f}  "
              f"skew={sk:+.3f}  kurt={ku:+.3f}  zeros={zeros}/{len(dm)} ({zeros/len(dm)*100:.1f}%)  max|d|={np.abs(dm).max():.1f}")

    # ── 6. Spread regime ──────────────────────────────────────────────
    section("[6] Spread histogram per day (top 10 values)")
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day]
        h = d["spread"].value_counts().sort_index().head(15)
        print(f"  day={day}  " + "  ".join(f"s={int(s)}:{int(n)}" for s, n in h.items()))

    # ── 7. Level fill rates and L1/L2/L3 depth ────────────────────────
    section("[7] Level fill rates and depth")
    for lvl in [1, 2, 3]:
        bp = dd[f"bid_price_{lvl}"]
        ap = dd[f"ask_price_{lvl}"]
        bv = dd[f"bid_volume_{lvl}"]
        av = dd[f"ask_volume_{lvl}"]
        print(f"  L{lvl}: bid filled={bp.notna().mean()*100:5.1f}%  "
              f"mean vol={bv.dropna().mean():5.2f}  |  "
              f"ask filled={ap.notna().mean()*100:5.1f}%  "
              f"mean vol={av.dropna().mean():5.2f}")

    # ── 8. Inter-level gaps ───────────────────────────────────────────
    section("[8] Price gap between adjacent levels")
    for side in ["bid", "ask"]:
        for lvl in [1, 2]:
            a = dd[f"{side}_price_{lvl}"]
            b = dd[f"{side}_price_{lvl+1}"]
            mask = a.notna() & b.notna()
            if mask.sum() == 0:
                continue
            gaps = (a[mask] - b[mask]).abs()
            print(f"  {side} L{lvl}->L{lvl+1}  n={mask.sum():5d}  "
                  f"mean={gaps.mean():5.2f}  median={np.median(gaps)}  "
                  f"q[5,50,95]={qs(gaps.values, (0.05,0.5,0.95))}")

    # ── 9. L1 volume imbalance ────────────────────────────────────────
    section("[9] L1 volume imbalance (bv1 - av1) / (bv1 + av1)")
    bv = dd["bid_volume_1"].to_numpy()
    av = dd["ask_volume_1"].to_numpy()
    imb = (bv - av) / (bv + av + 1e-12)
    sk, ku = skewkurt(imb)
    print(f"  mean={imb.mean():+.3f}  std={imb.std():.3f}  median={np.median(imb):+.3f}  "
          f"skew={sk:+.3f}  kurt={ku:+.3f}  q={qs(imb)}")

    # ── 10. Predictive power of imbalance ─────────────────────────────
    section("[10] Correlation of L1 imbalance(t) with dmid(t+k)")
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
        bv = d["bid_volume_1"].to_numpy()
        av = d["ask_volume_1"].to_numpy()
        imb = (bv - av) / (bv + av + 1e-12)
        m = d["mid"].to_numpy()
        corrs = []
        for k in [1, 2, 5, 10, 20]:
            if len(m) > k + 1:
                dmk = m[k:] - m[:-k]
                c = np.corrcoef(imb[:-k], dmk)[0, 1]
                corrs.append((k, round(float(c), 4)))
        print(f"  day={day}  {corrs}")

    # ── 11. Heteroscedasticity: |eps_mid| by spread bucket ────────────
    section("[11] |eps_mid| conditional on spread")
    dd["abs_eps"] = dd["eps_mid"].abs()
    g = dd.groupby("spread")["abs_eps"].agg(["count", "mean", "std"])
    for s, row in g.iterrows():
        if row["count"] > 50:
            print(f"  spread={int(s):2d}  n={int(row['count']):5d}  mean|eps|={row['mean']:.3f}  std={row['std']:.3f}")

    # ── 12. Trade flow analysis ───────────────────────────────────────
    section("[12] Trade flow (aggressor inferred via Lee-Ready vs prevailing mid)")
    for day, tf in TRADES.items():
        tr = pd.read_csv(tf, delimiter=";")
        tr = tr[tr["symbol"] == PRODUCT]
        if tr.empty:
            continue
        px = dd[dd["day_num"] == day][["timestamp", "mid", "bid_price_1", "ask_price_1"]].sort_values("timestamp")
        tr = tr.sort_values("timestamp")
        merged = pd.merge_asof(tr, px, on="timestamp", direction="backward")
        merged = merged.dropna(subset=["mid"])
        buy = (merged["price"] > merged["mid"]).sum()
        sell = (merged["price"] < merged["mid"]).sum()
        mid = (merged["price"] == merged["mid"]).sum()
        total = len(merged)
        print(f"  day={day}  n={total}  buyer-init={buy} ({buy/total*100:.1f}%)  "
              f"seller-init={sell} ({sell/total*100:.1f}%)  mid={mid}  "
              f"mean qty={merged['quantity'].mean():.2f}")
        rel = merged["price"] - merged["mid"]
        print(f"           trade price - mid: mean={rel.mean():+.3f}  std={rel.std():.3f}  "
              f"q[5,50,95]={qs(rel.values, (0.05,0.5,0.95))}")

    # ── 13. Spread autocorrelation (persistence of wide/tight regime) ──
    section("[13] Spread autocorrelation and persistence")
    for day in sorted(dd["day_num"].unique()):
        d = dd[dd["day_num"] == day].sort_values("timestamp")
        s = d["spread"].to_numpy().astype(float)
        s = s - s.mean()
        den = (s * s).sum()
        ac = [round((s[:-lag] * s[lag:]).sum() / den, 3) for lag in [1, 5, 20, 100]]
        print(f"  day={day}  spread ac[1,5,20,100] = {ac}")

    # ── 14. Residual vs volume imbalance (can we shrink residual?) ────
    section("[14] eps_mid regressed on L1 imbalance")
    imb_full = (dd["bid_volume_1"] - dd["ask_volume_1"]) / (dd["bid_volume_1"] + dd["ask_volume_1"] + 1e-12)
    beta, intercept = np.polyfit(imb_full.to_numpy(), dd["eps_mid"].to_numpy(), 1)
    r2 = np.corrcoef(imb_full, dd["eps_mid"])[0, 1] ** 2
    print(f"  eps_mid = {intercept:+.3f} + {beta:+.3f} * imb_L1   r2={r2:.4f}")

    # ── 15. What is the INTEGRITY of the trend: can slope drift? ──────
    section("[15] Rolling slope of mid (window=500 ticks) on day 0")
    d0 = dd[dd["day_num"] == 0].sort_values("timestamp").reset_index(drop=True)
    x = d0["timestamp"].to_numpy()
    y = d0["mid"].to_numpy()
    W = 500
    slopes = []
    for i in range(0, len(x) - W, W):
        xs = x[i:i + W]
        ys = y[i:i + W]
        b, _ = np.polyfit(xs, ys, 1)
        slopes.append(b)
    slopes = np.array(slopes)
    print(f"  n={len(slopes)} windows  mean={slopes.mean():.7f}  std={slopes.std():.7f}  "
          f"min={slopes.min():.7f}  max={slopes.max():.7f}")
    print(f"  quantiles[5,25,50,75,95] = {qs(slopes, (0.05,0.25,0.5,0.75,0.95))}")


if __name__ == "__main__":
    main()
