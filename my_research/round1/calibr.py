import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm

# ── Paramètres modifiables ─────────────────────────────────────────────────────
N_LEVELS  = 1      # profondeur micro-price (utilisé dans compute_fv)
BETA_VOL  = 30     # fenêtre rolling sigma (utilisé dans calibrate_sigma)

# ── helpers ────────────────────────────────────────────────────────────────────



prices_2=pd.read_csv('../../Stage1/Round1/prices_round_1_day_-2.csv',delimiter=";")
trades_2=pd.read_csv('../../Stage1/Round1/trades_round_1_day_-2.csv',delimiter=";")

prices_1=pd.read_csv('../../Stage1/Round1/prices_round_1_day_-1.csv',delimiter=";")
trades_1=pd.read_csv('../../Stage1/Round1/trades_round_1_day_-1.csv',delimiter=";")
prices_1['timestamp']+=prices_2['timestamp'].max()+100
trades_1['timestamp']+=prices_2['timestamp'].max()+100

prices_0=pd.read_csv('../../Stage1/Round1/prices_round_1_day_0.csv',delimiter=";")
trades_0=pd.read_csv('../../Stage1/Round1/trades_round_1_day_0.csv',delimiter=";")
prices_0['timestamp']+=prices_1['timestamp'].max()+100
trades_0['timestamp']+=prices_1['timestamp'].max()+100


prices=pd.concat([prices_2, prices_1, prices_0])
trades=pd.concat([trades_2, trades_1, trades_0])

prices[prices['mid_price']==0.0]=np.nan

prices=prices[prices['product']=="ASH_COATED_OSMIUM"]
trades=trades[trades['symbol']=="ASH_COATED_OSMIUM"]

merged = pd.merge(prices, trades, on="timestamp", how="outer")

remove = ['buyer','seller','symbol','currency','product','profit_and_loss','day','mid_price']
for i in remove:
    del merged[i]


def compute_fv(row, w_decay, n=N_LEVELS):
    num = den = imb_b = imb_a = 0.0
    for i in range(1, n + 1):
        bp = row.get(f"bid_price_{i}"); bq = row.get(f"bid_volume_{i}")
        ap = row.get(f"ask_price_{i}"); aq = row.get(f"ask_volume_{i}")
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [bp, bq, ap, aq]):
            break
        w     = np.exp(-w_decay * (i - 1))
        bq, aq = abs(bq), abs(aq)
        num  += w * (aq * bp + bq * ap)
        den  += w * (bq + aq)
        imb_b += w * bq
        imb_a += w * aq
    fv  = num / den if den > 0 else np.nan
    imb = (imb_b - imb_a) / (imb_b + imb_a) if (imb_b + imb_a) > 0 else np.nan
    return fv, imb

def build_series(df, w_decay):
    fvs, imbs = [], []
    for _, row in df.iterrows():
        fv, imb = compute_fv(row, w_decay)
        fvs.append(fv); imbs.append(imb)
    df = df.copy()
    df["fv"]  = fvs
    df["imb"] = imbs
    return df

# ── 1. W_DECAY ─────────────────────────────────────────────────────────────────

def neg_log_lik_wdecay(w_decay, df):
    tmp   = build_series(df, w_decay).dropna(subset=["fv"])
    fv    = tmp["fv"].values
    mid   = ((tmp["bid_price_1"] + tmp["ask_price_1"]) / 2).values
    resid = mid[1:] - fv[:-1]
    resid = resid[~np.isnan(resid)]
    if len(resid) < 10:
        return 1e9
    s2 = resid.var()
    return len(resid) * np.log(s2 + 1e-12)

def calibrate_wdecay(df):
    res = minimize_scalar(neg_log_lik_wdecay, bounds=(0.01, 3.0),
                          method="bounded", args=(df,))
    return res.x

# ── 2. SIGMA ───────────────────────────────────────────────────────────────────
# BETA_VOL utilisé ici : on estime sigma sur une fenêtre glissante
# et on prend la médiane comme sigma fixe de référence

def calibrate_sigma(df, w_decay, beta_vol=BETA_VOL):
    tmp  = build_series(df, w_decay).dropna(subset=["fv"])
    fv   = tmp["fv"].values
    # sigma MLE sur fenêtres glissantes de taille beta_vol
    sigmas = [
        fv[t - beta_vol:t].std()
        for t in range(beta_vol, len(fv))
        if not np.isnan(fv[t - beta_vol:t]).any()
    ]
    return float(np.median(sigmas))

# ── 3. ALPHA ───────────────────────────────────────────────────────────────────

def calibrate_alpha(df, w_decay):
    tmp  = build_series(df, w_decay).dropna(subset=["fv", "imb"])
    fv   = tmp["fv"].values
    imb  = tmp["imb"].values
    dfv  = np.diff(fv)
    x    = imb[:-1]
    mask = ~(np.isnan(dfv) | np.isnan(x))
    x, y = x[mask], dfv[mask]
    alpha = (x @ y) / (x @ x)
    return alpha

# ── 4. KAPPA ───────────────────────────────────────────────────────────────────

def calibrate_kappa(df, w_decay):
    tmp    = build_series(df, w_decay).dropna(subset=["fv"])
    bid1   = tmp["bid_price_1"].values
    ask1   = tmp["ask_price_1"].values
    spread = ask1 - bid1
    traded = (~tmp["price"].isna()).astype(float).values
    mask   = ~np.isnan(spread)
    s, y   = spread[mask], traded[mask]

    def neg_ll(kappa):
        p = 1 / (1 + np.exp(kappa * s))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -(y @ np.log(p) + (1 - y) @ np.log(1 - p))

    res = minimize_scalar(neg_ll, bounds=(0.001, 10.0), method="bounded")
    return res.x

# ── main ───────────────────────────────────────────────────────────────────────

def calibrate_all(df, n_levels=N_LEVELS, beta_vol=BETA_VOL):
    df = df.copy()
    for c in df.columns:
        if c != "timestamp":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    print(f"Config : N_LEVELS={n_levels}  BETA_VOL={beta_vol}\n")

    print("Calibration W_DECAY  ...", end=" ", flush=True)
    w_decay  = calibrate_wdecay(df)
    print(f"{w_decay:.4f}")

    print("Calibration SIGMA    ...", end=" ", flush=True)
    sigma    = calibrate_sigma(df, w_decay, beta_vol)
    print(f"{sigma:.4f}")

    print("Calibration ALPHA    ...", end=" ", flush=True)
    alpha    = calibrate_alpha(df, w_decay)
    print(f"{alpha:.4f}")

    print("Calibration KAPPA    ...", end=" ", flush=True)
    kappa    = calibrate_kappa(df, w_decay)
    print(f"{kappa:.4f}")

    print("\n── Paramètres calibrés ──────────────────")
    print(f"  N_LEVELS = {n_levels}   (fixé)")
    print(f"  BETA_VOL = {beta_vol}    (fixé)")
    print(f"  W_DECAY  = {w_decay:.4f}")
    print(f"  SIGMA    = {sigma:.4f}")
    print(f"  ALPHA    = {alpha:.4f}")
    print(f"  KAPPA    = {kappa:.4f}")

    return {
        "N_LEVELS": n_levels,
        "BETA_VOL": beta_vol,
        "W_DECAY" : w_decay,
        "SIGMA"   : sigma,
        "ALPHA"   : alpha,
        "KAPPA"   : kappa,
    }

params = calibrate_all(merged, n_levels=N_LEVELS, beta_vol=BETA_VOL)
