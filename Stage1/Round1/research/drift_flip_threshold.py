"""
For each top feature, sweep thresholds and find operating points where:
  - trend-scenario fire rate < 1% (must not misfire on clean trends)
  - AND pre-flip recall is as high as possible (fire BEFORE flip)

Also check: how many ticks BEFORE the flip does the feature actually cross?
(Lead-time distribution is what matters for actionable derisking.)
"""
from __future__ import annotations

import math
from drift_flip_signal import (
    load_pepper_ticks, run_holt, find_flips,
    REVERSAL_SCENARIOS, TREND_SCENARIOS, SCENARIOS,
)
from drift_flip_closeup import compute_extra_features


FEATURE_SUBSET = ["F13_B_decay_rate", "F14b_pressure_signed", "F16_run_x_pressure", "F15_B_relchange"]


def collect(scenario_data, target_feat, lead_max=100):
    """Return (pre_flip_vals, pool_other_rev, trend_vals, flat_vals, pre_flip_lead_time_by_tick)"""
    pre_flip_vals = []
    pre_flip_leads = []  # tick distance before flip — measured for each pre-flip tick
    other_rev_vals = []
    trend_vals = []
    flat_vals = []
    random_vals = []

    for s, d in scenario_data.items():
        vals = d["feats"][target_feat]
        flips = d["flips"]
        n = len(vals)

        # For each tick, find the nearest upcoming flip within lead_max
        next_flip = [None] * n
        for i in range(n):
            best = None
            for f in flips:
                if f > i and (f - i) <= lead_max:
                    if best is None or f < best:
                        best = f
            next_flip[i] = best

        if s in REVERSAL_SCENARIOS:
            for i in range(n):
                if next_flip[i] is not None and next_flip[i] - i >= 3:
                    pre_flip_vals.append(vals[i])
                    pre_flip_leads.append(next_flip[i] - i)
                else:
                    other_rev_vals.append(vals[i])
        elif s in TREND_SCENARIOS:
            trend_vals.extend(vals)
        elif s == "flat":
            flat_vals.extend(vals)
        else:
            random_vals.extend(vals)

    return pre_flip_vals, pre_flip_leads, other_rev_vals, trend_vals, flat_vals, random_vals


def threshold_sweep(scenario_data, target_feat):
    pre_vals, pre_leads, other, trend, flat, random_ = collect(scenario_data, target_feat)
    print(f"\n=== Feature: {target_feat} ===")
    print(f"  samples: pre_flip={len(pre_vals)}  other_rev={len(other)}  trend={len(trend)}  flat={len(flat)}  random={len(random_)}")

    # Compute percentiles for threshold candidates
    all_sorted = sorted(pre_vals + other + trend + flat + random_)
    candidates_pct = [50, 75, 85, 90, 95, 98, 99, 99.5, 99.8, 99.9]
    print(f"{'thr_pct':>8} {'thr':>10} {'preFlip_rec':>12} {'other_fr':>10} {'trend_fr':>10} {'flat_fr':>10} {'rand_fr':>10} {'avg_lead':>10}")
    for pct in candidates_pct:
        idx = int(pct / 100 * (len(all_sorted) - 1))
        thr = all_sorted[idx]
        pre_rec = sum(1 for v in pre_vals if v >= thr) / max(1, len(pre_vals))
        other_fr = sum(1 for v in other if v >= thr) / max(1, len(other))
        trend_fr = sum(1 for v in trend if v >= thr) / max(1, len(trend))
        flat_fr = sum(1 for v in flat if v >= thr) / max(1, len(flat))
        rand_fr = sum(1 for v in random_ if v >= thr) / max(1, len(random_))
        # average lead time among fired pre-flip ticks
        fired_leads = [pre_leads[i] for i in range(len(pre_vals)) if pre_vals[i] >= thr]
        avg_lead = sum(fired_leads) / len(fired_leads) if fired_leads else 0.0
        print(f"{pct:>8.1f} {thr:>10.4f} {pre_rec:>12.2%} {other_fr:>10.2%} {trend_fr:>10.2%} {flat_fr:>10.2%} {rand_fr:>10.2%} {avg_lead:>10.1f}")

    # Find best op point: trend_fr < 1%, max recall
    best = None
    for pct in range(500, 1000, 1):
        pctf = pct / 10.0
        idx = int(pctf / 100 * (len(all_sorted) - 1))
        thr = all_sorted[idx]
        pre_rec = sum(1 for v in pre_vals if v >= thr) / max(1, len(pre_vals))
        trend_fr = sum(1 for v in trend if v >= thr) / max(1, len(trend))
        if trend_fr <= 0.01 and (best is None or pre_rec > best[1]):
            best = (pctf, pre_rec, trend_fr, thr)
    if best:
        print(f"\n  BEST op (trend_fr <= 1%): pct={best[0]:.1f}  recall={best[1]:.2%}  thr={best[3]:.4f}  trend_fr={best[2]:.3%}")
    else:
        print(f"\n  NO op point with trend_fr <= 1% — feature always has trend overlap")


def first_fire_lead_time(scenario_data, target_feat, thr):
    """
    For each flip, when does the feature FIRST exceed threshold in the 200 ticks before?
    Report distribution of lead times.
    """
    print(f"\n  First-fire lead time per flip (threshold={thr:.4f}):")
    for s, d in scenario_data.items():
        if s not in REVERSAL_SCENARIOS:
            continue
        vals = d["feats"][target_feat]
        for f in d["flips"]:
            first_fire = None
            for i in range(max(0, f - 200), f):
                if vals[i] >= thr:
                    first_fire = i
                    break
            if first_fire is not None:
                print(f"    {s:<20} flip@{f}  first_fire@{first_fire}  lead={f - first_fire} ticks  val={vals[first_fire]:.4f}")
            else:
                print(f"    {s:<20} flip@{f}  NEVER fired (within 200 ticks)")


# Main
scenario_data = {}
for s in SCENARIOS:
    ticks = load_pepper_ticks(s)
    h = run_holt(ticks)
    flips = find_flips(h.B)
    feats = compute_extra_features(h)
    scenario_data[s] = {"h": h, "flips": flips, "feats": feats}

for feat in FEATURE_SUBSET:
    threshold_sweep(scenario_data, feat)

print()
print("=" * 100)
print("First-fire lead time (using pct=99 threshold)")
print("=" * 100)
for feat in FEATURE_SUBSET:
    # Pick 99th pct threshold for first-fire analysis
    all_vals = []
    for s, d in scenario_data.items():
        all_vals.extend(d["feats"][feat])
    all_vals.sort()
    thr99 = all_vals[int(0.99 * (len(all_vals) - 1))]
    print(f"\n=== {feat} ===")
    first_fire_lead_time(scenario_data, feat, thr99)
