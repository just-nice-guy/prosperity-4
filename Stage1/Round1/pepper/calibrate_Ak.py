"""
Offline calibration of the A-S order-flow parameters (A, k) for PEPPER_ROOT.

Model:  lambda(delta) = A * exp(-k * delta)
        where delta is the distance in ticks between our quote and the mid,
        and lambda is the per-tick probability that such a quote would be
        eligible AND filled by a market trade under Prosperity matching.

Method:
    For each historical tick t:
      - observe best_bid, best_ask, mid, and the list of market trades at t
      - for each candidate distance delta in {1..10}:
          - simulate a passive bid at price (mid - delta) and an ask at (mid + delta)
          - the quote is ELIGIBLE only if it is strictly better than the
            prevailing market quote on its side (Prosperity rule)
          - among eligible quotes, count how many get FILLED by market trades
            that cross their price
      - aggregate fill counts across all ticks

    Then fit  log(lambda(delta)) = log(A) - k * delta
    by least squares on the deltas where we had non-zero fills.

Outputs:  prints A, k, delta_star (optimal half-spread for the order-flow term),
          and the closed-form A-S inventory risk term for a range of (sigma, (T-t)).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


STAGE1 = Path(__file__).resolve().parent.parent
PRICE_FILES = {
    -2: STAGE1 / "prices_round_1_day_-2.csv",
    -1: STAGE1 / "prices_round_1_day_-1.csv",
     0: STAGE1 / "prices_round_1_day_0.csv",
}
TRADE_FILES = {
    -2: STAGE1 / "trades_round_1_day_-2.csv",
    -1: STAGE1 / "trades_round_1_day_-1.csv",
     0: STAGE1 / "trades_round_1_day_0.csv",
}
PRODUCT = "INTARIAN_PEPPER_ROOT"
DELTAS = list(range(1, 12))


def load_prices() -> pd.DataFrame:
    dfs = []
    for day, f in PRICE_FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d = d[d["product"] == PRODUCT].copy()
        d["day_num"] = day
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    return df


def load_trades() -> pd.DataFrame:
    dfs = []
    for day, f in TRADE_FILES.items():
        d = pd.read_csv(f, delimiter=";")
        d = d[d["symbol"] == PRODUCT].copy()
        d["day_num"] = day
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def calibrate():
    prices = load_prices()
    trades = load_trades()

    ok = prices["bid_price_1"].notna() & prices["ask_price_1"].notna()
    prices = prices[ok].copy()
    prices["mid"] = (prices["bid_price_1"] + prices["ask_price_1"]) / 2

    # Group trades by (day, timestamp) for O(1) lookup
    trades_by_key: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for row in trades.itertuples(index=False):
        key = (row.day_num, int(row.timestamp))
        trades_by_key.setdefault(key, []).append((int(row.price), int(row.quantity)))

    # For each tick, for each delta, determine eligibility and count fills
    n_ticks = len(prices)
    bid_fills = {d: 0 for d in DELTAS}
    ask_fills = {d: 0 for d in DELTAS}
    bid_eligible = {d: 0 for d in DELTAS}
    ask_eligible = {d: 0 for d in DELTAS}

    for row in prices.itertuples(index=False):
        mid = row.mid
        best_bid = int(row.bid_price_1)
        best_ask = int(row.ask_price_1)
        key = (row.day_num, int(row.timestamp))
        tick_trades = trades_by_key.get(key, [])

        for delta in DELTAS:
            our_bid = int(round(mid - delta))
            our_ask = int(round(mid + delta))

            # Prosperity eligibility: strictly better than market best
            bid_is_eligible = our_bid > best_bid and our_bid < best_ask
            ask_is_eligible = our_ask < best_ask and our_ask > best_bid

            if bid_is_eligible:
                bid_eligible[delta] += 1
                # Market sells at price <= our_bid → we fill
                if any(tp <= our_bid for tp, _ in tick_trades):
                    bid_fills[delta] += 1

            if ask_is_eligible:
                ask_eligible[delta] += 1
                # Market buys at price >= our_ask → we fill
                if any(tp >= our_ask for tp, _ in tick_trades):
                    ask_fills[delta] += 1

    # Report per-delta stats
    print(f"\n── Per-tick fill rates over {n_ticks} ticks ──")
    print(f"{'delta':>5}  {'bid_elig':>9}  {'bid_fill':>9}  {'lam_bid':>9}  "
          f"{'ask_elig':>9}  {'ask_fill':>9}  {'lam_ask':>9}")
    lam_bid: list[tuple[int, float]] = []
    lam_ask: list[tuple[int, float]] = []
    for d in DELTAS:
        lb = bid_fills[d] / n_ticks if n_ticks else 0.0
        la = ask_fills[d] / n_ticks if n_ticks else 0.0
        print(f"{d:>5}  {bid_eligible[d]:>9}  {bid_fills[d]:>9}  {lb:>9.5f}  "
              f"{ask_eligible[d]:>9}  {ask_fills[d]:>9}  {la:>9.5f}")
        if lb > 0:
            lam_bid.append((d, lb))
        if la > 0:
            lam_ask.append((d, la))

    # Pool bid+ask for a symmetric fit (makes sense since the data is symmetric)
    combined: dict[int, float] = {}
    for d in DELTAS:
        lb = bid_fills[d] / n_ticks if n_ticks else 0.0
        la = ask_fills[d] / n_ticks if n_ticks else 0.0
        pooled = (lb + la) / 2.0
        if pooled > 0:
            combined[d] = pooled

    if len(combined) < 3:
        print("\nNot enough non-zero points to fit A, k")
        return

    xs = np.array(list(combined.keys()), dtype=float)
    ys = np.array([math.log(v) for v in combined.values()])
    # log(lambda) = log(A) - k*delta → linear fit
    slope, intercept = np.polyfit(xs, ys, 1)
    k_hat = -slope
    A_hat = math.exp(intercept)

    print(f"\n── Exponential fit lambda(delta) = A * exp(-k * delta) ──")
    print(f"  A_hat = {A_hat:.5f}")
    print(f"  k_hat = {k_hat:.5f}")

    # Quality check: residuals
    pred = A_hat * np.exp(-k_hat * xs)
    residuals = np.array(list(combined.values())) - pred
    print(f"  fit residuals: max={np.abs(residuals).max():.5f}")

    # Closed-form A-S components
    gamma_values = [0.005, 0.01, 0.02, 0.03, 0.05]
    sigma_values = [0.5, 1.0, 1.5, 2.0]

    print(f"\n── A-S order-flow half-spread = (1/gamma) * ln(1 + gamma/k) ──")
    print(f"  (this term is INDEPENDENT of sigma and (T-t))")
    for g in gamma_values:
        order_flow = (1.0 / g) * math.log(1.0 + g / k_hat)
        print(f"  gamma={g:.3f}:  order-flow term = {order_flow:.3f}")

    print(f"\n── A-S inventory-risk half-spread = 0.5 * gamma * sigma^2 * (T - t) ──")
    print(f"  (assumes T-t normalized to fraction of session; use (ticks_remaining / 10000))")
    for g in gamma_values:
        print(f"\n  gamma={g}:")
        for s in sigma_values:
            print(f"    sigma={s}:")
            for tt in [1.0, 0.5, 0.1]:
                inv = 0.5 * g * s * s * tt
                order_flow = (1.0 / g) * math.log(1.0 + g / k_hat)
                total = inv + order_flow
                print(f"      (T-t)={tt:.2f}:  inventory={inv:.3f}  order_flow={order_flow:.3f}  total_half_spread={total:.3f}")

    # Optimal inventory target for a few configurations, given B=0.1
    B = 0.1
    print(f"\n── Optimal inventory target  q* = B / (gamma * sigma^2) ──")
    print(f"  using B_hat = 0.1")
    for g in gamma_values:
        for s in sigma_values:
            q_star = B / (g * s * s)
            print(f"  gamma={g:.3f}, sigma={s}:  q* = {q_star:>6.1f}")

    # Sanity: expected fill time at delta = order_flow_term
    print(f"\n── Expected fill time tau = 1 / lambda(delta_star) ──")
    for g in gamma_values:
        ds = (1.0 / g) * math.log(1.0 + g / k_hat)
        lam_ds = A_hat * math.exp(-k_hat * ds)
        tau = 1.0 / lam_ds if lam_ds > 1e-9 else float("inf")
        print(f"  gamma={g:.3f}: delta*={ds:.2f}  lambda(delta*)={lam_ds:.5f}  tau={tau:.1f} ticks")


if __name__ == "__main__":
    calibrate()
