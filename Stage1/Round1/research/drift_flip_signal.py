"""
Research: can we predict a drift sign-flip before it happens?

Approach (holistic signal research):

STEP 1 — Reconstruct B(t) from CSV data using v8's exact Holt params.
         No reliance on trader logs; purely a function of observed micro.

STEP 2 — Define "flip event": B(t) changes sign and stays on the new side
         for ≥ WINDOW ticks with |B| ≥ DRIFT_THRESHOLD. That's a true
         regime change, not a crossing noise.

STEP 3 — Compute candidate features per tick (lookback features only):
            F1. Abs change |B - B_lag| over L ticks
            F2. Rolling std of ΔB (matches v9 sigma_B_fast)
            F3. Sign-flip frequency of ΔB in last L ticks ("chop")
            F4. Ratio |B| / rolling max(|B|)    — "drift is decaying"
            F5. Price innov sign ≠ sign(B)     — "price fighting B"
            F6. Innov cumul over last L ticks vs B            (dispersion)
            F7. Spread widening vs trailing mean
            F8. Imbalance sign flip ratio
            F9. d|B|/dt < 0 AND |B| below half its recent peak (decay)
            F10. |B|/max_|B|_100 combined with flip-freq F3

STEP 4 — For each feature, measure precision/recall at predicting flip
         with various lead times (tick-ahead horizon 10, 30, 50).
         A good predictor:
            - Fires BEFORE flip (positive lead time distribution).
            - High precision in reversal scenarios.
            - LOW firing rate in trend scenarios (must not misfire on
              clean trends).

STEP 5 — Report best features with ROC-style comparison.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from dataclasses import dataclass, field

# v8 constants (must match traderv8.py)
ALPHA = 0.15
BETA = 0.01
B_PRIOR = 0.1
SIGMA2_INIT = 1.44
LAM_VOL = 0.97
MIN_SIGMA = 1.0
JUMP_CAP_SIGMA = 5
NARROW_SPREAD = 5
DRIFT_THRESHOLD = 0.3 * B_PRIOR   # 0.03

PRODUCT = "INTARIAN_PEPPER_ROOT"

DATA_DIR = Path(__file__).parent.parent / "synthetic_datasets" / "data"
SCENARIOS = [
    "flat",
    "random_seed_1", "random_seed_2", "random_seed_3", "random_seed_4", "random_seed_5",
    "reversal_end", "reversal_middle", "reversal_start",
    "trend_down", "trend_up", "zigzag_long",
]
REVERSAL_SCENARIOS = {"reversal_end", "reversal_middle", "reversal_start"}
TREND_SCENARIOS = {"trend_up", "trend_down"}


@dataclass
class Tick:
    timestamp: int
    best_bid: int
    best_ask: int
    bv: int
    av: int


def load_pepper_ticks(scenario: str) -> list[Tick]:
    path = DATA_DIR / f"prices_round_99_day_0__{scenario}.csv"
    ticks: list[Tick] = []
    with path.open() as f:
        rdr = csv.DictReader(f, delimiter=";")
        for row in rdr:
            if row["product"] != PRODUCT:
                continue
            bp = row["bid_price_1"]
            ap = row["ask_price_1"]
            if not bp or not ap:
                continue
            try:
                best_bid = int(bp)
                best_ask = int(ap)
                bv = int(row["bid_volume_1"] or 0)
                av = int(row["ask_volume_1"] or 0)
            except ValueError:
                continue
            ticks.append(Tick(int(row["timestamp"]), best_bid, best_ask, bv, av))
    return ticks


@dataclass
class HoltOut:
    t: list[int] = field(default_factory=list)
    L: list[float] = field(default_factory=list)
    B: list[float] = field(default_factory=list)
    sigma2: list[float] = field(default_factory=list)
    innov: list[float] = field(default_factory=list)        # capped
    innov_raw: list[float] = field(default_factory=list)    # uncapped
    micro: list[float] = field(default_factory=list)
    spread: list[int] = field(default_factory=list)
    imb: list[float] = field(default_factory=list)
    dB: list[float] = field(default_factory=list)


def run_holt(ticks: list[Tick]) -> HoltOut:
    """Replicate v8's Holt update exactly (incl. narrow-spread skip)."""
    o = HoltOut()
    L: float | None = None
    B = B_PRIOR
    sigma2 = SIGMA2_INIT
    B_prev_for_dB = B_PRIOR
    for tk in ticks:
        spread = tk.best_ask - tk.best_bid
        tot = tk.bv + tk.av
        if tot <= 0:
            micro = (tk.best_bid + tk.best_ask) / 2.0
            imb = 0.0
        else:
            micro = (tk.bv * tk.best_ask + tk.av * tk.best_bid) / tot
            imb = (tk.bv - tk.av) / tot

        if L is None:
            L = micro

        if spread <= NARROW_SPREAD:
            # v8 skips update on narrow spread but still extrapolates
            L = L + B
            # Keep state flat and record as no-innov tick so time series aligns
            o.t.append(tk.timestamp)
            o.L.append(L)
            o.B.append(B)
            o.sigma2.append(sigma2)
            o.innov.append(0.0)
            o.innov_raw.append(0.0)
            o.micro.append(micro)
            o.spread.append(spread)
            o.imb.append(imb)
            o.dB.append(B - B_prev_for_dB)
            B_prev_for_dB = B
            continue

        pred = L + B
        sigma = max(MIN_SIGMA, math.sqrt(sigma2))
        cap = JUMP_CAP_SIGMA * sigma
        innov_raw = micro - pred
        micro_capped = micro
        if innov_raw > cap:
            micro_capped = pred + cap
        elif innov_raw < -cap:
            micro_capped = pred - cap

        L_prev = L
        L = ALPHA * micro_capped + (1.0 - ALPHA) * (L_prev + B)
        B_new = BETA * (L - L_prev) + (1.0 - BETA) * B
        innov = micro_capped - pred
        sigma2 = LAM_VOL * sigma2 + (1.0 - LAM_VOL) * innov * innov
        if sigma2 < 0.25:
            sigma2 = 0.25

        o.t.append(tk.timestamp)
        o.L.append(L)
        o.B.append(B_new)
        o.sigma2.append(sigma2)
        o.innov.append(innov)
        o.innov_raw.append(innov_raw)
        o.micro.append(micro_capped)
        o.spread.append(spread)
        o.imb.append(imb)
        o.dB.append(B_new - B_prev_for_dB)

        B_prev_for_dB = B_new
        B = B_new

    return o


# ── Flip event detection ──────────────────────────────────────────────
def find_flips(B: list[float], min_hold: int = 100, min_mag: float = DRIFT_THRESHOLD) -> list[int]:
    """
    A flip at index i means:
      - B[i-1] and B[i] have opposite signs (regime change crosses 0)
      - AND for the next `min_hold` ticks the NEW sign persists with |B|>min_mag
        at least once within the hold window
      - AND before the flip, the OLD sign was established (|B|>min_mag at least once in last min_hold ticks)
    Returns indices where a genuine regime flip occurs.
    """
    flips: list[int] = []
    n = len(B)
    for i in range(1, n):
        if B[i - 1] == 0 or B[i] == 0:
            continue
        if (B[i - 1] > 0) == (B[i] > 0):
            continue
        # Check old regime was established
        lo = max(0, i - min_hold)
        old_sign = 1.0 if B[i - 1] > 0 else -1.0
        old_ok = any((old_sign * B[j] > min_mag) for j in range(lo, i))
        if not old_ok:
            continue
        # Check new regime sustained
        hi = min(n, i + min_hold)
        new_sign = 1.0 if B[i] > 0 else -1.0
        new_ok = any((new_sign * B[j] > min_mag) for j in range(i, hi))
        if not new_ok:
            continue
        flips.append(i)
    # Deduplicate flips within 50 ticks of each other (keep first)
    dedup: list[int] = []
    for f in flips:
        if not dedup or f - dedup[-1] > 50:
            dedup.append(f)
    return dedup


# ── Features (all lookback-only) ─────────────────────────────────────
def rolling(values: list[float], window: int, func) -> list[float]:
    out = [0.0] * len(values)
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        out[i] = func(values[lo:i + 1])
    return out


def compute_features(h: HoltOut, L: int = 50) -> dict[str, list[float]]:
    n = len(h.B)
    B = h.B
    dB = h.dB
    innov = h.innov
    sigma2 = h.sigma2

    # F1: |B - B[t-L]|
    F1 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L)
        F1[i] = abs(B[i] - B[lo])

    # F2: rolling std of dB over L
    def _std(xs):
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        v = sum((x - m) ** 2 for x in xs) / len(xs)
        return math.sqrt(v)
    F2 = rolling(dB, L, _std)

    # F3: sign-flip frequency of dB in last L ticks (0-1)
    F3 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        flips = 0
        total = 0
        prev_sign = 0
        for j in range(lo, i + 1):
            s = 1 if dB[j] > 0 else (-1 if dB[j] < 0 else 0)
            if s != 0:
                if prev_sign != 0 and s != prev_sign:
                    flips += 1
                prev_sign = s
                total += 1
        F3[i] = flips / max(1, total - 1)

    # F4: |B| / rolling max |B| over L   (close to 1 = peak, near 0 = decayed)
    absB = [abs(b) for b in B]
    F4 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        mx = max(absB[lo:i + 1])
        F4[i] = absB[i] / mx if mx > 0 else 0.0

    # F5: fraction of innov with OPPOSITE sign to B in last L ticks
    F5 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        opposite = 0
        total = 0
        for j in range(lo, i + 1):
            if B[j] == 0 or innov[j] == 0:
                continue
            total += 1
            if (B[j] > 0) != (innov[j] > 0):
                opposite += 1
        F5[i] = opposite / max(1, total)

    # F6: cumsum innov last L vs B. If cum_innov sign opposite to B, pressure building.
    F6 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        cum = sum(innov[lo:i + 1])
        # Pressure signal: negative if cum_innov opposes B
        if abs(B[i]) < 1e-9:
            F6[i] = abs(cum)
        else:
            F6[i] = -cum * (1.0 if B[i] > 0 else -1.0)
    # Normalize F6 by sqrt(sigma2) to make it roughly a z-score
    F6 = [F6[i] / max(1.0, math.sqrt(sigma2[i])) for i in range(n)]

    # F7: spread widening — spread[i] / mean spread over L
    F7 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        ms = sum(h.spread[lo:i + 1]) / max(1, i - lo + 1)
        F7[i] = h.spread[i] / max(1, ms)

    # F8: imbalance sign flip frequency over L
    F8 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        flips = 0
        total = 0
        prev_sign = 0
        for j in range(lo, i + 1):
            s = 1 if h.imb[j] > 0.05 else (-1 if h.imb[j] < -0.05 else 0)
            if s != 0:
                if prev_sign != 0 and s != prev_sign:
                    flips += 1
                prev_sign = s
                total += 1
        F8[i] = flips / max(1, total - 1)

    # F9: d|B|/dt < 0 for several ticks in a row AND |B| < 0.5 * rolling max
    # Simpler: fraction of last L ticks where d|B|/dt negative
    F9 = [0.0] * n
    for i in range(n):
        lo = max(1, i - L + 1)
        neg = 0
        for j in range(lo, i + 1):
            if absB[j] < absB[j - 1]:
                neg += 1
        F9[i] = neg / max(1, i - lo + 1)

    # F10: combo — F3 * (1 - F4)  (chop high + drift decayed)
    F10 = [F3[i] * (1.0 - F4[i]) for i in range(n)]

    return {
        "F1_dB_change": F1,
        "F2_dB_std": F2,
        "F3_dB_signflip": F3,
        "F4_B_over_peak": F4,
        "F5_innov_vs_B": F5,
        "F6_cum_innov_opp": F6,
        "F7_spread_widen": F7,
        "F8_imb_signflip": F8,
        "F9_decay_frac": F9,
        "F10_chop_x_decay": F10,
    }


# ── Scoring ──────────────────────────────────────────────────────────
def evaluate_feature(
    feature: list[float],
    flips: list[int],
    n_ticks: int,
    lead_window: tuple[int, int] = (5, 100),
    threshold_quantile: float = 0.90,
) -> dict:
    """
    Mark a tick as POSITIVE if a flip occurs within (lead_min, lead_max] ticks
    ahead. Compute precision/recall at a threshold = quantile(feature).
    Higher feature values should correlate with upcoming flips.
    """
    lead_min, lead_max = lead_window
    positive = [False] * n_ticks
    for f in flips:
        lo = max(0, f - lead_max)
        hi = max(0, f - lead_min)
        for j in range(lo, hi):
            positive[j] = True

    # Sort feature values to pick threshold
    sorted_vals = sorted(feature)
    idx = int(threshold_quantile * (len(sorted_vals) - 1))
    thr = sorted_vals[idx]

    tp = fp = fn = tn = 0
    for i in range(n_ticks):
        fire = feature[i] >= thr
        pos = positive[i]
        if fire and pos:
            tp += 1
        elif fire and not pos:
            fp += 1
        elif not fire and pos:
            fn += 1
        else:
            tn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "threshold": thr,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "fire_rate": (tp + fp) / n_ticks,
    }


# ── Pool-level evaluation ────────────────────────────────────────────
def evaluate_all():
    """
    Combine reversal + trend scenarios. Compute feature value at:
      - "pre-flip windows" in reversal scenarios (target = FIRE)
      - all non-pre-flip ticks in reversal scenarios  (target = SILENT)
      - all ticks in trend scenarios                  (target = SILENT, MUST be silent)

    Rank features by:
      - Pre-flip mean / all-other mean  (signal-to-noise ratio)
      - % trend ticks above the 90th pct of combined feature  (false positive rate)
    """
    scenario_data = {}
    for s in SCENARIOS:
        ticks = load_pepper_ticks(s)
        h = run_holt(ticks)
        flips = find_flips(h.B)
        feats = compute_features(h)
        scenario_data[s] = {"h": h, "flips": flips, "feats": feats}
        sign_max = max(h.B)
        sign_min = min(h.B)
        print(f"{s:<20} n={len(h.B):>5d}  flips={flips}  B range=[{sign_min:+.4f}, {sign_max:+.4f}]")

    print()
    print("=" * 100)
    print("Per-feature analysis: SNR = mean(feat | pre-flip window) / mean(feat | other)")
    print("Lead window = ticks BEFORE flip where we want to fire.")
    print("Trend false-fire = fraction of trend-scenario ticks exceeding the reversal 90th pct.")
    print("=" * 100)

    LEAD = (5, 100)   # fire at most 100 ticks before flip, at least 5 before
    feat_names = list(next(iter(scenario_data.values()))["feats"].keys())

    rows = []
    for fname in feat_names:
        # Pool pre-flip values from reversal scenarios
        pre_flip_vals = []
        other_rev_vals = []
        trend_vals = []
        random_vals = []
        flat_vals = []

        for s, d in scenario_data.items():
            vals = d["feats"][fname]
            flips = d["flips"]
            n = len(vals)

            positive = [False] * n
            for f in flips:
                lo = max(0, f - LEAD[1])
                hi = max(0, f - LEAD[0])
                for j in range(lo, hi):
                    positive[j] = True

            if s in REVERSAL_SCENARIOS:
                for i in range(n):
                    (pre_flip_vals if positive[i] else other_rev_vals).append(vals[i])
            elif s in TREND_SCENARIOS:
                trend_vals.extend(vals)
            elif s == "flat":
                flat_vals.extend(vals)
            else:
                random_vals.extend(vals)

        if not pre_flip_vals:
            rows.append((fname, 0, 0, 0, 0, 0, 0))
            continue

        mean_pre = sum(pre_flip_vals) / len(pre_flip_vals)
        mean_other = sum(other_rev_vals) / max(1, len(other_rev_vals))
        mean_trend = sum(trend_vals) / max(1, len(trend_vals))
        mean_flat = sum(flat_vals) / max(1, len(flat_vals))

        # SNR: pre-flip vs other reversal ticks (ignoring the "target" window)
        snr = mean_pre / max(1e-9, mean_other)

        # 90th percentile of combined reversal values as a threshold
        combined_rev = pre_flip_vals + other_rev_vals
        combined_rev.sort()
        thr90 = combined_rev[int(0.90 * (len(combined_rev) - 1))]

        # What fraction of TREND ticks fire above this threshold?
        trend_fire = sum(1 for v in trend_vals if v >= thr90) / max(1, len(trend_vals))
        # Pre-flip recall at thr90
        pre_recall = sum(1 for v in pre_flip_vals if v >= thr90) / max(1, len(pre_flip_vals))
        # Precision within reversal scenarios
        rev_fire_total = sum(1 for v in combined_rev if v >= thr90)
        pre_fire = sum(1 for v in pre_flip_vals if v >= thr90)
        rev_precision = pre_fire / max(1, rev_fire_total)

        rows.append((fname, mean_pre, mean_other, mean_trend, snr, pre_recall, trend_fire, rev_precision, thr90, mean_flat))

    # Print ranked by (recall * (1 - trend_fire))
    print()
    print(f"{'feature':<22} {'pre-flip':>10} {'other':>10} {'trend':>10} {'SNR':>6} {'recall':>7} {'trend_FP':>9} {'precR':>7} {'thr90':>10}")
    rows.sort(key=lambda r: -(r[5] * (1 - r[6])))
    for r in rows:
        fname, mean_pre, mean_other, mean_trend, snr, recall, trend_fp, prec, thr, mean_flat = r
        print(f"{fname:<22} {mean_pre:>10.3f} {mean_other:>10.3f} {mean_trend:>10.3f} {snr:>6.2f} {recall:>7.2%} {trend_fp:>9.2%} {prec:>7.2%} {thr:>10.4f}")

    return scenario_data, rows


if __name__ == "__main__":
    evaluate_all()
