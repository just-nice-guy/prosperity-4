"""
Close-up study around reversal flips — understand microstructure BEFORE the flip.
Also test tighter/longer lead windows + new features:
  F11: run length of innov sign opposite to B (consecutive, ending at i)
  F12: |B|/sigma  (normalized drift strength — small = weak signal)
  F13: linear slope of B over last L (sign(slope) * sign(B_now) — negative = decaying)
  F14: |cum_innov(L)| / sqrt(L)/sigma  (z-score of accumulated pressure)
  F15: slope of B normalized by its own magnitude: dB/dt / |B|  — % decay per tick

Also: double-check the "F6 SNR huge" was denominator weirdness.
"""
from __future__ import annotations

import math
from drift_flip_signal import (
    load_pepper_ticks, run_holt, find_flips,
    REVERSAL_SCENARIOS, TREND_SCENARIOS, SCENARIOS,
)


def closeup(scenario: str, flip_idx: int, window: int = 300):
    ticks = load_pepper_ticks(scenario)
    h = run_holt(ticks)
    lo = max(0, flip_idx - window)
    hi = min(len(h.B), flip_idx + 30)

    print(f"\n=== {scenario} — flip at i={flip_idx} (t={h.t[flip_idx]}) ===")
    print(f"{'idx':>5} {'t':>6} {'B':>8} {'sigma':>6} {'innov':>7} {'micro':>9} {'L':>9} {'spread':>6} {'imb':>6}")
    step = max(1, (hi - lo) // 30)
    for i in range(lo, hi, step):
        print(f"{i:>5} {h.t[i]:>6} {h.B[i]:>+8.4f} {math.sqrt(h.sigma2[i]):>6.2f} "
              f"{h.innov[i]:>+7.2f} {h.micro[i]:>9.2f} {h.L[i]:>9.2f} {h.spread[i]:>6d} {h.imb[i]:>+6.2f}")
    # Always print the flip tick
    i = flip_idx
    print(f"{i:>5} {h.t[i]:>6} {h.B[i]:>+8.4f} {math.sqrt(h.sigma2[i]):>6.2f} "
          f"{h.innov[i]:>+7.2f} {h.micro[i]:>9.2f} {h.L[i]:>9.2f} {h.spread[i]:>6d} {h.imb[i]:>+6.2f}  <<<FLIP")


# Key scenarios
print("### Close-up around flip events ###")
closeup("reversal_middle", 4594, window=400)
closeup("reversal_start", 975, window=400)
closeup("reversal_end", 8210, window=400)


# ── New features ─────────────────────────────────────────────────────
def compute_extra_features(h, L: int = 50):
    n = len(h.B)
    B = h.B
    innov = h.innov
    sigma2 = h.sigma2
    absB = [abs(b) for b in B]

    # F11: current run length of innov sign OPPOSITE to sign(B)
    F11 = [0.0] * n
    run = 0
    for i in range(n):
        if B[i] == 0 or innov[i] == 0:
            run = 0
        elif (B[i] > 0) != (innov[i] > 0):
            run += 1
        else:
            run = 0
        F11[i] = float(run)

    # F12: |B| / sigma  (low = B is weak)
    F12 = [absB[i] / max(1.0, math.sqrt(sigma2[i])) for i in range(n)]
    # We invert it so that a HIGH feature value = "flip risk" (B weak → flip-risk high)
    F12_inv = [1.0 / (1.0 + v) for v in F12]   # maps to (0, 1]

    # F13: slope of B over last L via simple (B[i] - B[i-L])/L, normalized by |B[i]|
    F13 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L)
        slope = (B[i] - B[lo]) / max(1, i - lo)
        # "decay rate": positive if |B| is shrinking i.e. slope * sign(B) < 0
        if absB[i] < 1e-9:
            F13[i] = 0.0
        else:
            decay = -slope * (1.0 if B[i] > 0 else -1.0)
            F13[i] = max(0.0, decay)

    # F14: |cum innov(L)| / (sigma * sqrt(L))  — z-score of accumulated pressure
    F14 = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        cum = sum(innov[lo:i + 1])
        w = i - lo + 1
        F14[i] = abs(cum) / (max(1.0, math.sqrt(sigma2[i])) * math.sqrt(max(1, w)))

    # F14b: SIGNED — positive if cum_innov opposes B
    F14b = [0.0] * n
    for i in range(n):
        lo = max(0, i - L + 1)
        cum = sum(innov[lo:i + 1])
        w = i - lo + 1
        z = cum / (max(1.0, math.sqrt(sigma2[i])) * math.sqrt(max(1, w)))
        if absB[i] < 1e-9:
            F14b[i] = abs(z)
        else:
            F14b[i] = -z * (1.0 if B[i] > 0 else -1.0)

    # F15: instantaneous relative change rate of B
    F15 = [0.0] * n
    for i in range(1, n):
        if absB[i - 1] > 1e-9:
            F15[i] = (B[i] - B[i - 1]) * (-1.0 if B[i - 1] > 0 else 1.0) / absB[i - 1]

    # F16: COMBO — F11 * F14b   (consecutive opposite runs * signed z-score)
    F16 = [F11[i] * max(0.0, F14b[i]) for i in range(n)]

    # F17: COMBO — F11 * (1/(1+|B|/sigma))  (long opposite run AND B weak)
    F17 = [F11[i] * F12_inv[i] for i in range(n)]

    return {
        "F11_opposite_run": F11,
        "F12inv_weakB": F12_inv,
        "F13_B_decay_rate": F13,
        "F14_pressure_mag": F14,
        "F14b_pressure_signed": F14b,
        "F15_B_relchange": F15,
        "F16_run_x_pressure": F16,
        "F17_run_x_weakB": F17,
    }


# ── Full evaluation with extra features + tighter lead window ────────
def evaluate_all_tighter():
    scenario_data = {}
    for s in SCENARIOS:
        ticks = load_pepper_ticks(s)
        h = run_holt(ticks)
        flips = find_flips(h.B)
        feats = compute_extra_features(h)
        scenario_data[s] = {"h": h, "flips": flips, "feats": feats}

    # Evaluate with lead_window = (5, 50) — tighter
    LEAD = (5, 50)

    feat_names = list(next(iter(scenario_data.values()))["feats"].keys())
    print()
    print("=" * 100)
    print(f"NEW FEATURES — lead window {LEAD}")
    print("=" * 100)
    print(f"{'feature':<25} {'pre-flip':>10} {'other':>10} {'trend':>10} {'flat':>10} {'SNR':>6} {'recall':>7} {'trendFP':>8} {'flatFP':>7}")

    results = []
    for fname in feat_names:
        pre_flip_vals = []
        other_rev_vals = []
        trend_vals = []
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

        if not pre_flip_vals or not other_rev_vals:
            continue

        mean_pre = sum(pre_flip_vals) / len(pre_flip_vals)
        mean_other = sum(other_rev_vals) / len(other_rev_vals)
        mean_trend = sum(trend_vals) / max(1, len(trend_vals))
        mean_flat = sum(flat_vals) / max(1, len(flat_vals))
        snr = mean_pre / max(1e-9, abs(mean_other)) if mean_other != 0 else float('inf')

        # Threshold at 90th pct of reversal-only values
        combined = pre_flip_vals + other_rev_vals
        combined.sort()
        thr = combined[int(0.90 * (len(combined) - 1))]
        recall = sum(1 for v in pre_flip_vals if v >= thr) / len(pre_flip_vals)
        trend_fp = sum(1 for v in trend_vals if v >= thr) / max(1, len(trend_vals))
        flat_fp = sum(1 for v in flat_vals if v >= thr) / max(1, len(flat_vals))

        results.append((fname, mean_pre, mean_other, mean_trend, mean_flat, snr, recall, trend_fp, flat_fp, thr))

    # Sort by recall * (1 - trend_fp) * (1 - flat_fp)
    results.sort(key=lambda r: -(r[6] * (1 - r[7]) * (1 - r[8])))
    for r in results:
        print(f"{r[0]:<25} {r[1]:>10.3f} {r[2]:>10.3f} {r[3]:>10.3f} {r[4]:>10.3f} {r[5]:>6.2f} {r[6]:>7.2%} {r[7]:>8.2%} {r[8]:>7.2%}")

    return scenario_data, results


print()
print("=" * 100)
evaluate_all_tighter()
