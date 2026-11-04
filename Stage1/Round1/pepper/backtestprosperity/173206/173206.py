"""
INTARIAN_PEPPER_ROOT trader v1 — IMC Prosperity 4, Round 1.
(Internal iteration: v7 of our design iterations, committed as v1 for submission.)

Principled A-S with drift/imbalance-driven directional sizing.

Core logic
──────────
At every tick we observe two dynamic signals:

  B_t  = filtered drift (from Holt local-linear-trend on micro_price)
  imb_t = instantaneous L1 imbalance = (bv1 - av1) / (bv1 + av1)

These two signals jointly define the FAVORABLE SIDE:

  drift_sign = sign(B_t)  with dead-zone |B_t| < DRIFT_THRESHOLD  (= 0)
  fav        = +1 if drift_sign > 0
              -1 if drift_sign < 0
               0 otherwise

When fav = +1 we want to ACCUMULATE LONG toward POS_LIMIT:
  - Quote a LARGE passive bid (max execution on the favorable side)
  - Quote a SMALL passive ask (defensive valve, only near POS_LIMIT)
  - Aggressive taking triggers ONLY when imb is strongly positive (|imb| > IMB_TAKE)

When fav = -1 the symmetric mirror applies.

When fav = 0 (drift in the dead-zone) we quote symmetric A-S.

Fair value model (unchanged from v5/v6)
  - micro_price absorbs 89% of the contemporaneous imbalance signal
  - Holt EWMA smoothing gives L_t (level) and B_t (drift)
  - fv_bid = L  (no anticipation — buy low, hold to close)
  - fv_ask = L + H_ASK · B_t  (forward-anticipated sell price)

Quoting: A-S with calibrated δ* = (1/γ)·ln(1 + γ/k)  and  q_target = fav·POS_LIMIT.
Inventory skew pulls the reservation price toward q_target on both sides.

Calibration (from stage1/pepper/calibrate_Ak.py):
  A_hat = 0.0688,  k_hat = 0.5835,  δ*_flow ≈ 1.70
"""
from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ── Product ────────────────────────────────────────────────────────────────
PRODUCT = "INTARIAN_PEPPER_ROOT"
POS_LIMIT = 80          # Confirmed: Round 1 per-side limit is 80


# ── Holt linear fair-value filter ─────────────────────────────────────────
ALPHA = 0.15
BETA = 0.01
B_PRIOR = 0.1           # drift prior per run() call (+1000 per day historical)
SIGMA2_INIT = 1.44
LAM_VOL = 0.97
MIN_SIGMA = 1.0
JUMP_CAP_SIGMA = 5


# ── Avellaneda-Stoikov calibrated ──────────────────────────────────────────
A_HAT = 0.0688
K_HAT = 0.5835
GAMMA = 0.03
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)  # ≈ 1.679


# ── Asymmetric forecast horizons ───────────────────────────────────────────
H_BID = 0               # buy-side: no anticipation (buy low, hold)
H_ASK = 40              # sell-side: forward anticipation


# ── Drift / imbalance regime ───────────────────────────────────────────────
DRIFT_THRESHOLD = 0.03  # |B_t| < this → drift too weak, fall back to neutral
IMB_TAKE = 0.25         # |imb_t| >= this → take aggressively
IMB_BOOST = 2.0         # extra ticks of aggression per unit imb (fav side)


# ── Robustness ─────────────────────────────────────────────────────────────
NARROW_SPREAD = 5
TAKE_EDGE = 2


# ── Sizing — decided by the favorable side ───────────────────────────────
# On the favorable side we push max execution. On the unfavorable side we
# SKIP the quote entirely as long as we are not near POS_LIMIT, because
# calibration proved each unfavorable fill has net-negative marginal rate
# (A < B·e·k on a positive-drift product).
#
# We are executed LAST at any given price level in the matching engine, so
# we must be STRICTLY the best quote to get filled. The _clamp_inside()
# helper already forces our quotes into (best_bid+1, best_ask-1).
#
# Three stacked levels spread our size across nearby price points and catch
# more market trades in a single tick; total emitted per side ≤ POS_LIMIT.
MAX_SIZE_FAV = 40        # per level on the favorable side (~2 levels fill to 80)
MAX_SIZE_NEU = 30
LEVELS = 3               # 3 stacked passive quote levels per side
LEVEL_GAP = 1

# Position thresholds for unlocking the unfavorable side
OFF_GATE_RATIO = 0.90    # |pos| >= 0.9·POS_LIMIT → unlock unfavorable quotes


T_END_TICKS = 10000


# ──────────────────────────────────────────────────────────────────────────
class State:
    __slots__ = ("L", "B", "sigma2")

    def __init__(
        self,
        L: float | None = None,
        B: float = B_PRIOR,
        sigma2: float = SIGMA2_INIT,
    ) -> None:
        self.L = L
        self.B = B
        self.sigma2 = sigma2

    def to_json(self) -> str:
        return json.dumps({"L": self.L, "B": self.B, "s2": self.sigma2})

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            L_val = d.get("L")
            return cls(
                L=float(L_val) if L_val is not None else None,
                B=float(d.get("B", B_PRIOR)),
                sigma2=float(d.get("s2", SIGMA2_INIT)),
            )
        except Exception:
            return cls()


def _to_tick(x: float) -> int:
    return int(round(x))


def _clamp_inside(px: int, best_bid: int, best_ask: int) -> int | None:
    lo = best_bid + 1
    hi = best_ask - 1
    if lo > hi:
        return None
    if px < lo:
        return lo
    if px > hi:
        return hi
    return px


class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:
        # ── 0. Restore persistent state ───────────────────────────────────
        st = State.from_json(state.traderData) if state.traderData else State()
        pos = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if depth is None:
            return {PRODUCT: orders}, 0, st.to_json()

        bids = depth.buy_orders or {}
        asks = depth.sell_orders or {}
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None

        # ── 1. Book guard: one-sided book → predict-only ─────────────────
        if best_bid is None or best_ask is None:
            if st.L is not None:
                st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        spread = best_ask - best_bid
        bv = abs(bids[best_bid])
        av = abs(asks[best_ask])

        # ── 2. Micro-price (imbalance-corrected mid) + raw imbalance ─────
        tot = bv + av
        if tot <= 0:
            micro = (best_bid + best_ask) / 2.0
            imb = 0.0
        else:
            micro = (bv * best_ask + av * best_bid) / tot
            imb = (bv - av) / tot

        if st.L is None:
            st.L = micro

        # ── 3. Narrow-spread regime: mid biased, predict-only ────────────
        if spread <= NARROW_SPREAD:
            st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        # ── 4. Winsorize innovation ──────────────────────────────────────
        pred = st.L + st.B
        sigma = max(MIN_SIGMA, math.sqrt(st.sigma2))
        cap = JUMP_CAP_SIGMA * sigma
        innov_raw = micro - pred
        if innov_raw > cap:
            micro = pred + cap
        elif innov_raw < -cap:
            micro = pred - cap

        # ── 5. Holt update (L, B) ────────────────────────────────────────
        L_prev = st.L
        st.L = ALPHA * micro + (1.0 - ALPHA) * (L_prev + st.B)
        st.B = BETA * (st.L - L_prev) + (1.0 - BETA) * st.B

        # ── 6. EWMA volatility ───────────────────────────────────────────
        innov = micro - pred
        st.sigma2 = LAM_VOL * st.sigma2 + (1.0 - LAM_VOL) * innov * innov
        if st.sigma2 < 0.25:
            st.sigma2 = 0.25
        sigma = math.sqrt(st.sigma2)
        sigma2 = st.sigma2

        # ── 7. DIRECTIONAL REGIME FROM DRIFT ──────────────────────────────
        if st.B > DRIFT_THRESHOLD:
            fav = +1                # long bias
            q_target = POS_LIMIT
        elif st.B < -DRIFT_THRESHOLD:
            fav = -1                # short bias
            q_target = -POS_LIMIT
        else:
            fav = 0                 # neutral
            q_target = 0

        # ── 8. A-S FORWARD ANCHORS ────────────────────────────────────────
        # Favorable side buys low (no anticipation); opposite side anticipates
        # drift so its quote sits further out of reach.
        fv_bid = st.L + (H_BID if fav >= 0 else H_ASK) * st.B
        fv_ask = st.L + (H_ASK if fav >= 0 else H_BID) * st.B

        # ── 9. A-S HALF-SPREAD (calibrated) ───────────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left

        # ── 10. A-S RESERVATION with pro-target skew ─────────────────────
        skew = (pos - q_target) * GAMMA * sigma2
        r_bid = fv_bid - skew
        r_ask = fv_ask - skew

        # ── 11. Imbalance boost on the favorable side ────────────────────
        # Strong imbalance in the fav direction tightens that side's quote.
        if fav == +1 and imb > 0:
            r_bid += IMB_BOOST * imb
        elif fav == -1 and imb < 0:
            r_ask += IMB_BOOST * imb  # imb negative → r_ask shifts down → ask tighter

        # ── 12. Determine quote sizes from favorable side ────────────────
        # Favorable side: always MAX_SIZE_FAV
        # Unfavorable side: SKIPPED unless pos is near the hard limit, in
        # which case we unlock it to manage the breach risk.
        off_gate = int(POS_LIMIT * OFF_GATE_RATIO)

        if fav == +1:
            size_bid = MAX_SIZE_FAV
            size_ask = MAX_SIZE_FAV if pos >= off_gate else 0
        elif fav == -1:
            size_bid = MAX_SIZE_FAV if pos <= -off_gate else 0
            size_ask = MAX_SIZE_FAV
        else:
            size_bid = MAX_SIZE_NEU
            size_ask = MAX_SIZE_NEU

        # Worst-case-fully-filled trackers
        wl = pos
        ws = pos

        # ── 13. AGGRESSIVE TAKING — GATED ON STRONG IMBALANCE ────────────
        # Only fire when imb is strongly pointing in a direction. This is
        # where we "enter aggressively on a big signal".
        fv_now = st.L
        if imb >= IMB_TAKE:
            # Strong bullish pressure: take cheap asks
            for ask_px in sorted(asks):
                if ask_px >= fv_now - TAKE_EDGE:
                    break
                vol = abs(asks[ask_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty
        elif imb <= -IMB_TAKE:
            # Strong bearish pressure: take expensive bids
            for bid_px in sorted(bids, reverse=True):
                if bid_px <= fv_now + TAKE_EDGE:
                    break
                vol = abs(bids[bid_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty

        # ── 14. PASSIVE QUOTES — A-S around forward fvs ──────────────────
        bid_0 = _clamp_inside(_to_tick(r_bid - delta_star), best_bid, best_ask)
        ask_0 = _clamp_inside(_to_tick(r_ask + delta_star), best_bid, best_ask)

        for lvl in range(LEVELS):
            if lvl == 0:
                bid_px = bid_0
                ask_px = ask_0
            else:
                bid_px = (
                    _clamp_inside(bid_0 - lvl * LEVEL_GAP, best_bid, best_ask)
                    if bid_0 is not None else None
                )
                ask_px = (
                    _clamp_inside(ask_0 + lvl * LEVEL_GAP, best_bid, best_ask)
                    if ask_0 is not None else None
                )

            # Emit bid (only if sizing says so)
            if bid_px is not None and size_bid > 0:
                qty_b = min(size_bid, POS_LIMIT - wl)
                if qty_b > 0:
                    orders.append(Order(PRODUCT, bid_px, qty_b))
                    wl += qty_b

            # Emit ask (only if sizing says so)
            if ask_px is not None and size_ask > 0:
                qty_a = min(size_ask, ws + POS_LIMIT)
                if qty_a > 0:
                    orders.append(Order(PRODUCT, ask_px, -qty_a))
                    ws -= qty_a

        # ── 15. Debug log ─────────────────────────────────────────────────
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} B={st.B:+.4f} "
            f"imb={imb:+.2f} L={st.L:.1f} r_b={r_bid:.1f} r_a={r_ask:.1f} "
            f"size_b={size_bid} size_a={size_ask} n={len(orders)}"
        )

        return {PRODUCT: orders}, 0, st.to_json()