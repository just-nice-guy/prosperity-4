"""
INTARIAN_PEPPER_ROOT trader v2 — IMC Prosperity 4, Round 1.

Design principles (applied from official backtest lessons)
──────────────────────────────────────────────────────────
1.  EVERY risk/signal parameter is derived from LIVE state whenever possible.
    Only structural constants (POS_LIMIT, level count, session length) and
    offline-calibrated anchors (A_hat, k_hat, B_prior) are fixed.

2.  Aggressive taking is ASYMMETRIC by regime:
      - fav = +1 (drift up):  buy-take ONLY, never sell-take
      - fav = -1 (drift down): sell-take ONLY, never buy-take
      - fav =  0 (deadzone):  no taking, pure passive MM

3.  Derisk inventory target: Q_TARGET = 0.75 × POS_LIMIT × fav = ±60, not ±80.
    Going to the hard limit maximises drift capture but also exposes us
    fully to a drift reversal. Targeting 60 leaves 20 units of buffer and
    lets the A-S skew naturally unwind a portion of inventory on the way,
    capturing additional spread profit along the way.

4.  Forward horizons H_BID / H_ASK are REMOVED. The A-S skew + clamping
    already produce the right asymmetric behaviour on a drifting market.

5.  Buy-take relaxed: in fav=+1 we take any ask priced below a dynamic
    threshold L - TAKE_EDGE, irrespective of the imbalance value. The
    imbalance still boosts the PASSIVE quote center via IMB_BOOST so we
    get more aggressive on the bid when imb is strong.

6.  Level emission order is cheapest-first: lowest bid emitted first, so
    market trades hit our cheapest level first and fill there instead of
    wasting the trade on our most aggressive level.

Dynamic parameters
──────────────────
    TAKE_EDGE        = max(1, round(sigma))                 # scales with vol
    IMB_TAKE_BIAS    = 1.5 · sigma_imb  (tracked via EWMA)  # z-score
    q_target         = fav · POS_LIMIT · 0.75                # derisked
    fav              = sign(B) with deadzone 0.3 · B_PRIOR
    delta_star       = DELTA_STAR_FLOW + 0.5·γ·σ²·(T-t)/T
    IMB_BOOST        = 5.0 (from eps_mid = -5.14·imb regression, rounded)

Calibration inputs (from stage1/pepper/calibrate_Ak.py):
    A_hat = 0.0688     lambda(delta) = A·exp(-k·delta)
    k_hat = 0.5835
    Order-flow half-spread ≈ 1.70 ticks (derived).
"""
from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ── Platform constants (truly fixed) ───────────────────────────────────────
PRODUCT = "INTARIAN_PEPPER_ROOT"
POS_LIMIT = 80              # Round 1 per-side position limit
T_END_TICKS = 10000         # Full-round session length (run() calls)


# ── Holt linear filter (offline tuned, stable choice) ────────────────────
ALPHA = 0.15                # level smoothing (half-life ~4 ticks)
BETA = 0.01                 # slope smoothing (half-life ~70 ticks)
B_PRIOR = 0.1               # historical drift per run() call
SIGMA2_INIT = 1.44          # initial variance (residual std ~1.2)
LAM_VOL = 0.97              # EWMA vol decay (half-life ~23 ticks)
MIN_SIGMA = 1.0
JUMP_CAP_SIGMA = 5          # innovation winsor threshold (5σ)


# ── A-S calibrated anchors (offline on 3 historical days) ────────────────
A_HAT = 0.0688
K_HAT = 0.5835
GAMMA = 0.03
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)  # ≈ 1.679


# ── Imbalance boost: from EDA regression  eps_mid = -5.14 · imb_L1 ───────
IMB_BOOST = 5.0


# ── Inventory de-risking: cap target at 75% of hard limit ────────────────
Q_TARGET_RATIO = 0.75       # q_target = ±60 when |fav|=1


# ── Signal thresholds (partially dynamic) ────────────────────────────────
DRIFT_THRESHOLD = 0.3 * B_PRIOR   # 30% of prior drift => deadzone |B|<0.03
IMB_TAKE_Z = 1.5                  # z-score threshold on rolling sigma_imb
SIGMA_IMB_INIT = 0.19             # empirical std(imb) on 3 historical days
LAM_IMB = 0.995                   # EWMA for sigma_imb²  (half-life ~140 ticks)


# ── Robustness ────────────────────────────────────────────────────────────
NARROW_SPREAD = 5           # spread ≤ 5: micro biased by one-sided aggression


# ── Sizing and levels ────────────────────────────────────────────────────
MAX_SIZE_FAV = 40           # favorable-side level size (worst-case trimmed)
MAX_SIZE_NEU = 30
LEVELS = 3
LEVEL_GAP = 1


# ──────────────────────────────────────────────────────────────────────────
class State:
    __slots__ = ("L", "B", "sigma2", "sigma_imb2")

    def __init__(
        self,
        L: float | None = None,
        B: float = B_PRIOR,
        sigma2: float = SIGMA2_INIT,
        sigma_imb2: float = SIGMA_IMB_INIT ** 2,
    ) -> None:
        self.L = L
        self.B = B
        self.sigma2 = sigma2
        self.sigma_imb2 = sigma_imb2

    def to_json(self) -> str:
        return json.dumps({
            "L": self.L,
            "B": self.B,
            "s2": self.sigma2,
            "si2": self.sigma_imb2,
        })

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            L_val = d.get("L")
            return cls(
                L=float(L_val) if L_val is not None else None,
                B=float(d.get("B", B_PRIOR)),
                sigma2=float(d.get("s2", SIGMA2_INIT)),
                sigma_imb2=float(d.get("si2", SIGMA_IMB_INIT ** 2)),
            )
        except Exception:
            return cls()


def _to_tick(x: float) -> int:
    return int(round(x))


def _clamp_inside(px: int | None, best_bid: int, best_ask: int) -> int | None:
    """Clamp a quote price to [best_bid+1, best_ask-1] (strictly inside)."""
    if px is None:
        return None
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

        # ── 2. Micro-price and raw imbalance ─────────────────────────────
        tot = bv + av
        if tot <= 0:
            micro = (best_bid + best_ask) / 2.0
            imb = 0.0
        else:
            micro = (bv * best_ask + av * best_bid) / tot
            imb = (bv - av) / tot

        if st.L is None:
            st.L = micro

        # ── 3. Narrow-spread regime: predict-only, no orders ─────────────
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

        # ── 6. EWMA updates: vol and imb distribution ────────────────────
        innov = micro - pred
        st.sigma2 = LAM_VOL * st.sigma2 + (1.0 - LAM_VOL) * innov * innov
        if st.sigma2 < 0.25:
            st.sigma2 = 0.25
        sigma = math.sqrt(st.sigma2)
        sigma2 = st.sigma2

        st.sigma_imb2 = LAM_IMB * st.sigma_imb2 + (1.0 - LAM_IMB) * imb * imb
        if st.sigma_imb2 < 0.0025:  # floor at std 0.05
            st.sigma_imb2 = 0.0025
        sigma_imb = math.sqrt(st.sigma_imb2)

        # ── 7. Dynamic parameters from state ─────────────────────────────
        take_edge = max(1, int(round(sigma)))        # scales with vol
        imb_take = IMB_TAKE_Z * sigma_imb             # z-score threshold

        # ── 8. Regime detection ─────────────────────────────────────────
        if st.B > DRIFT_THRESHOLD:
            fav = +1
            q_target = int(POS_LIMIT * Q_TARGET_RATIO)       # +60
        elif st.B < -DRIFT_THRESHOLD:
            fav = -1
            q_target = -int(POS_LIMIT * Q_TARGET_RATIO)      # -60
        else:
            fav = 0
            q_target = 0

        # ── 9. A-S reservation price (no forward horizon — L is the anchor)
        skew = (pos - q_target) * GAMMA * sigma2
        r = st.L - skew

        # Imbalance boost on the favorable-direction side
        if fav == +1 and imb > 0:
            r += IMB_BOOST * imb
        elif fav == -1 and imb < 0:
            r += IMB_BOOST * imb  # imb<0 → r shifts down

        # ── 10. A-S half-spread ──────────────────────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left

        # Worst-case-fully-filled trackers
        wl = pos
        ws = pos
        fv_now = st.L

        # ── 11. AGGRESSIVE TAKING — ASYMMETRIC BY REGIME ─────────────────
        # fav = +1: only BUY-take (no sell-take) — selling hurts drift MTM
        # fav = -1: only SELL-take (no buy-take) — mirror image
        # fav =  0: no taking
        if fav == +1:
            # Take any ask below fv_now - take_edge. Do NOT gate on imb
            # (drift makes any cheap ask profitable in this regime).
            for ask_px in sorted(asks):
                if ask_px >= fv_now - take_edge:
                    break
                vol = abs(asks[ask_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty

        elif fav == -1:
            for bid_px in sorted(bids, reverse=True):
                if bid_px <= fv_now + take_edge:
                    break
                vol = abs(bids[bid_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty

        # ── 12. PASSIVE QUOTES — A-S around r, 3 levels, cheapest first ──
        # Compute level-0 targets from the reservation price, then fan out.
        bid_0_raw = _to_tick(r - delta_star)
        ask_0_raw = _to_tick(r + delta_star)

        # Size depends on regime: favorable side gets MAX, neutral gets NEU.
        size_bid = MAX_SIZE_FAV if fav == +1 else MAX_SIZE_NEU
        size_ask = MAX_SIZE_FAV if fav == -1 else MAX_SIZE_NEU

        # DERISK: bids are capped at q_target in favorable regime (not at
        # POS_LIMIT). This keeps the inventory tight around the target and
        # lets the A-S skew naturally cycle with the asks.
        # In fav=-1 symmetric (short-accumulate to q_target).
        # In fav=0 use the full POS_LIMIT as the cap.
        if fav == +1:
            bid_cap = q_target                 # stop buying once at target
        elif fav == -1:
            bid_cap = POS_LIMIT                # in short regime, bids are hedge
        else:
            bid_cap = POS_LIMIT

        # Emit bids: CHEAPEST (most conservative) FIRST so the match engine
        # fills our lowest-priced bid before the more aggressive ones.
        for lvl in reversed(range(LEVELS)):
            bid_px = _clamp_inside(bid_0_raw - lvl * LEVEL_GAP, best_bid, best_ask)
            if bid_px is None:
                continue
            qty_b = min(size_bid, bid_cap - wl)
            if qty_b > 0:
                orders.append(Order(PRODUCT, bid_px, qty_b))
                wl += qty_b

        # DERISK ASK EMISSION: symmetric to bid cap.
        # fav=+1 short side capped at -q_target (don't hedge to big short).
        # fav=-1 asks are the main accumulation side, full cap.
        if fav == +1:
            ask_cap = -q_target                # don't go short past -60 while bullish
        elif fav == -1:
            ask_cap = q_target                 # short q_target units (q_target is negative here)
        else:
            ask_cap = -POS_LIMIT

        # Only emit asks once the position is at or above q_target on the
        # favorable side. Below target we accumulate; at target we cycle.
        should_emit_ask = True
        if fav == +1 and pos < q_target:
            should_emit_ask = False
        elif fav == -1 and pos > q_target:
            should_emit_ask = False

        if should_emit_ask:
            # ws + POS_LIMIT is the max we can sell (worst-case short).
            # We further clip by (pos - ask_cap): can only sell down to ask_cap.
            for lvl in reversed(range(LEVELS)):
                ask_px = _clamp_inside(ask_0_raw + lvl * LEVEL_GAP, best_bid, best_ask)
                if ask_px is None:
                    continue
                qty_a = min(size_ask, ws - ask_cap)
                if qty_a > 0:
                    orders.append(Order(PRODUCT, ask_px, -qty_a))
                    ws -= qty_a

        # ── 13. Debug log ────────────────────────────────────────────────
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} B={st.B:+.4f} "
            f"imb={imb:+.2f} L={st.L:.1f} r={r:.1f} "
            f"d*={delta_star:.2f} te={take_edge} it={imb_take:.2f} "
            f"qT={q_target:+d} n={len(orders)}"
        )

        return {PRODUCT: orders}, 0, st.to_json()
