"""
Explore additional micro-effects on PEPPER_ROOT beyond drift + L1 imbalance.
Targets: L2 imbalance, weighted mid, multi-level pressure, short-term
momentum, trade-sign signal, jump clustering, spread-conditioned imbalance,
intraday temporal structure, and cross-product correlation with OSMIUM.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STAGE1 = "."
FILES = {
    -2: f"{STAGE1}/prices_round_1_day_-2.csv",
    -1: f"{STAGE1}/prices_round_1_day_-1.csv",
     0: f"{STAGE1}/prices_round_1_day_0.csv",
}
TRADES = {
    -2: f"{STAGE1}/trades_round_1_day_-2.csv",
    -1: f"{STAGE1}/trades_round_1_day_-1.csv",
     0: f"{STAGE1}/trades_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"


def section(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def load_both():
    dfs = []
    for day, f in FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d["day_num"] = day
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def load_trades():
    dfs = []
    for day, f in TRADES.items():
        d = pd.read_csv(f, delimiter=";")
        d["day_num"] = day
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def build_pepper(df):
    d = df[df["product"] == PRODUCT].copy()
    ok = d["bid_price_1"].notna() & d["ask_price_1"].notna()
    d = d[ok].reset_index(drop=True)
    d["mid"] = (d["bid_price_1"] + d["ask_price_1"]) / 2
    d["spread"] = d["ask_price_1"] - d["bid_price_1"]

    # Day-wise fit
    fits = {}
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day]
        b, a = np.polyfit(dd["timestamp"], dd["mid"], 1)
        fits[day] = (a, b)
    d["a"] = d["day_num"].map(lambda k: fits[k][0])
    d["b"] = d["day_num"].map(lambda k: fits[k][1])
    d["fv"] = d["a"] + d["b"] * d["timestamp"]
    d["eps"] = d["mid"] - d["fv"]

    # Imbalances at L1, L2, cumulative L1+L2
    bv1, av1 = d["bid_volume_1"].fillna(0), d["ask_volume_1"].fillna(0)
    bv2, av2 = d["bid_volume_2"].fillna(0), d["ask_volume_2"].fillna(0)
    d["imb1"] = (bv1 - av1) / (bv1 + av1 + 1e-12)
    d["imb2"] = (bv2 - av2) / (bv2 + av2 + 1e-12)
    d["imb12"] = (bv1 + bv2 - av1 - av2) / (bv1 + bv2 + av1 + av2 + 1e-12)

    # Weighted mid: volume-weighted across best-of-book
    d["wmid"] = (d["bid_price_1"] * av1 + d["ask_price_1"] * bv1) / (bv1 + av1 + 1e-12)
    d["eps_wmid"] = d["wmid"] - d["fv"]

    # Micro price (Cartea-Jaimungal): (bv * ap + av * bp) / (bv + av)
    d["micro"] = (bv1 * d["ask_price_1"] + av1 * d["bid_price_1"]) / (bv1 + av1 + 1e-12)
    d["eps_micro"] = d["micro"] - d["fv"]

    return d, fits


def ts_lag_corr(imb, mid, k):
    dmk = mid[k:] - mid[:-k]
    return float(np.corrcoef(imb[:-k], dmk)[0, 1])


def main():
    raw = load_both()
    d, fits = build_pepper(raw)

    section("[A] Multi-level imbalances vs residual eps_mid (contemporaneous R^2)")
    for col in ("imb1", "imb2", "imb12"):
        b, a = np.polyfit(d[col], d["eps"], 1)
        r2 = float(np.corrcoef(d[col], d["eps"])[0, 1] ** 2)
        print(f"  eps ~ {col}:  slope={b:+.3f}  intercept={a:+.3f}  R^2={r2:.4f}")

    # Joint OLS eps ~ imb1 + imb2
    X = np.column_stack([np.ones(len(d)), d["imb1"], d["imb2"]])
    y = d["eps"].to_numpy()
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coefs
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2_joint = 1 - ss_res / ss_tot
    print(f"  joint eps ~ const + imb1 + imb2:  intercept={coefs[0]:+.3f}  "
          f"beta1={coefs[1]:+.3f}  beta2={coefs[2]:+.3f}  R^2={r2_joint:.4f}")

    section("[B] Weighted mid and micro price as FV proxies")
    for col in ("mid", "wmid", "micro"):
        res = d[col] - d["fv"]
        print(f"  {col:6s} - fv:  mean={res.mean():+.4f}  std={res.std():.4f}  "
              f"|R^2 vs imb1|={np.corrcoef(d['imb1'], res)[0,1]**2:.4f}")

    section("[C] Short-term momentum: autocorrelation of raw dmid")
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp")
        m = dd["mid"].to_numpy()
        dm = np.diff(m)
        dm0 = dm - dm.mean()
        den = (dm0 * dm0).sum()
        ac = [round(float((dm0[:-lag] * dm0[lag:]).sum() / den), 3)
              for lag in [1, 2, 5, 10, 20, 50]]
        print(f"  day={day}  ac(dmid)[1,2,5,10,20,50] = {ac}")

    section("[D] Autocorrelation of imb1 itself (signal persistence)")
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp")
        s = dd["imb1"].to_numpy()
        s0 = s - s.mean()
        den = (s0 * s0).sum()
        ac = [round(float((s0[:-lag] * s0[lag:]).sum() / den), 3)
              for lag in [1, 2, 5, 10, 20, 50]]
        print(f"  day={day}  ac(imb1)[1,2,5,10,20,50] = {ac}")

    section("[E] Predictive imbalance effectiveness: imb1 vs imb12 on dmid(t+k)")
    for k in [1, 5, 10, 20]:
        rows = []
        for day in sorted(d["day_num"].unique()):
            dd = d[d["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
            m = dd["mid"].to_numpy()
            c1 = ts_lag_corr(dd["imb1"].to_numpy(), m, k)
            c12 = ts_lag_corr(dd["imb12"].to_numpy(), m, k)
            rows.append((day, c1, c12))
        print(f"  k={k:3d}  " + "  ".join(f"day{d_}: imb1={c1_:+.3f} imb12={c12_:+.3f}"
                                          for d_, c1_, c12_ in rows))

    section("[F] Jump events and clustering (|dmid| > 4)")
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
        m = dd["mid"].to_numpy()
        dm = np.diff(m)
        big = np.abs(dm) > 4
        n_big = int(big.sum())
        if n_big == 0:
            print(f"  day={day}  no jumps > 4")
            continue
        idx = np.where(big)[0]
        gaps = np.diff(idx) if len(idx) > 1 else []
        print(f"  day={day}  n_jumps={n_big}  mean|dmid_jump|={np.abs(dm[big]).mean():.2f}  "
              f"median_gap_ticks_between={int(np.median(gaps)) if len(gaps) else 'NA'}  "
              f"min_gap={int(gaps.min()) if len(gaps) else 'NA'}")

    section("[G] Post-jump mean reversion: dmid 1..10 ticks after a big move")
    # Average signed dmid after a positive jump and after a negative jump
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
        m = dd["mid"].to_numpy()
        dm = np.diff(m)
        big_pos = np.where(dm > 4)[0]
        big_neg = np.where(dm < -4)[0]
        rets_pos = []
        rets_neg = []
        for i in big_pos:
            if i + 10 < len(m):
                rets_pos.append(m[i + 10] - m[i + 1])
        for i in big_neg:
            if i + 10 < len(m):
                rets_neg.append(m[i + 10] - m[i + 1])
        print(f"  day={day}  after +jump: n={len(big_pos)} mean dmid(1->10)={np.mean(rets_pos) if rets_pos else 0:+.2f}   "
              f"after -jump: n={len(big_neg)} mean dmid(1->10)={np.mean(rets_neg) if rets_neg else 0:+.2f}")

    section("[H] Trade-sign signal: did last trade direction predict next dmid?")
    trades = load_trades()
    trades = trades[trades["symbol"] == PRODUCT].copy()
    # Match trades to prevailing book and sign them (Lee-Ready)
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day][["timestamp", "mid"]].sort_values("timestamp")
        tr = trades[trades["day_num"] == day].sort_values("timestamp")
        if tr.empty:
            continue
        mg = pd.merge_asof(tr, dd, on="timestamp", direction="backward").dropna(subset=["mid"])
        mg["sign"] = np.sign(mg["price"] - mg["mid"])
        # For each trade, look up the mid AT the next book snapshot (step +100) and compute dmid
        mg2 = pd.merge_asof(
            mg.assign(ts_next=mg["timestamp"] + 100),
            dd.rename(columns={"timestamp": "ts_next", "mid": "mid_next"}),
            on="ts_next", direction="forward")
        mg2["dmid_next"] = mg2["mid_next"] - mg2["mid"]
        mg2 = mg2.dropna(subset=["dmid_next"])
        if len(mg2) > 10:
            c = float(np.corrcoef(mg2["sign"], mg2["dmid_next"])[0, 1])
            mean_pos = mg2[mg2["sign"] > 0]["dmid_next"].mean()
            mean_neg = mg2[mg2["sign"] < 0]["dmid_next"].mean()
            print(f"  day={day}  n={len(mg2)}  corr(sign, dmid_next)={c:+.3f}  "
                  f"mean_after_buy={mean_pos:+.2f}  mean_after_sell={mean_neg:+.2f}")

    section("[I] Intraday temporal structure: eps std vs time-of-day (4 buckets)")
    for day in sorted(d["day_num"].unique()):
        dd = d[d["day_num"] == day].copy()
        dd["bucket"] = pd.cut(dd["timestamp"], bins=4, labels=[0, 1, 2, 3])
        g = dd.groupby("bucket", observed=True)["eps"].agg(["count", "std"])
        print(f"  day={day}")
        for b, row in g.iterrows():
            print(f"    bucket={b}  n={int(row['count'])}  std(eps)={row['std']:.3f}")

    section("[J] Cross-product correlation with ASH_COATED_OSMIUM")
    osm = raw[raw["product"] == "ASH_COATED_OSMIUM"].copy()
    ok = osm["bid_price_1"].notna() & osm["ask_price_1"].notna()
    osm = osm[ok]
    osm["mid"] = (osm["bid_price_1"] + osm["ask_price_1"]) / 2
    for day in sorted(d["day_num"].unique()):
        dp = d[d["day_num"] == day][["timestamp", "mid", "eps"]].rename(columns={"mid": "pep_mid", "eps": "pep_eps"})
        do = osm[osm["day_num"] == day][["timestamp", "mid"]].rename(columns={"mid": "osm_mid"})
        m = pd.merge(dp, do, on="timestamp")
        if m.empty:
            continue
        dpep = np.diff(m["pep_mid"].to_numpy())
        dosm = np.diff(m["osm_mid"].to_numpy())
        c_level = float(np.corrcoef(m["pep_eps"], m["osm_mid"] - m["osm_mid"].mean())[0, 1])
        c_ret = float(np.corrcoef(dpep, dosm)[0, 1])
        c_eps_osm_dev = float(np.corrcoef(m["pep_eps"], m["osm_mid"] - 10000)[0, 1])
        print(f"  day={day}  n={len(m)}  corr(pep_dmid, osm_dmid)={c_ret:+.3f}   "
              f"corr(pep_eps, osm_mid-10000)={c_eps_osm_dev:+.3f}")

    section("[K] Spread-conditioned imbalance signal (is imb stronger when spread is narrow?)")
    d["spread_bucket"] = pd.cut(d["spread"], bins=[-1, 5, 10, 13, 20, 99],
                                labels=["tight<=5", "6-10", "11-13 normal", "14-20 wide", ">20"])
    for bucket in ["tight<=5", "6-10", "11-13 normal", "14-20 wide"]:
        sub = d[d["spread_bucket"] == bucket]
        if len(sub) < 100:
            continue
        # Use all-day data, lag 1
        sub = sub.sort_values(["day_num", "timestamp"]).reset_index(drop=True)
        # Compute dmid(t+1) per row — must stay within the same day
        dm = []
        imb = []
        for day in sub["day_num"].unique():
            ss = sub[sub["day_num"] == day].sort_values("timestamp").reset_index(drop=True)
            m = ss["mid"].to_numpy()
            if len(m) < 2: continue
            dm.extend(np.diff(m).tolist())
            imb.extend(ss["imb1"].to_numpy()[:-1].tolist())
        if len(dm) > 50:
            c = float(np.corrcoef(imb, dm)[0, 1])
            print(f"  {bucket:15s}  n={len(dm):6d}  corr(imb_t, dmid_t+1)={c:+.3f}")


if __name__ == "__main__":
    main()
