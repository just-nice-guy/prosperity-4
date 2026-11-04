"""
INTARIAN_PEPPER_ROOT trader v3 — IMC Prosperity 4, Round 1.

v3 fixes from v2 (based on official backtest 176985 analysis)
─────────────────────────────────────────────────────────────
A.  IMB_BOOST removed from passive quotes.  The reservation price is now
    r = L − skew  (pure A-S, no imbalance distortion).  Passive bids land
    at L−2..L−5 instead of L+0..L+2.  Real market-maker edge on every fill.

B.  Aggressive market-take on strong aligned imbalance.  When imb is
    strongly positive in fav=+1 regime, we TAKE the ask up to a price
    proportional to the imbalance strength:
        max_take_price = L + round(imb * IMB_BOOST_TAKE)
    This captures the directional opportunity that v2 missed entirely.

C.  Adverse-selection circuit breaker.  When |imb| exceeds an extreme
    threshold (2.5 × sigma_imb), we cut passive bid size by 2/3 to avoid
    getting filled massively at a price that's about to revert.

Everything else (Holt filter, A-S half-spread, 3 phases, asymmetric
regime, dynamic thresholds) is inherited from v2 unchanged.
"""
from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ── Platform constants ─────────────────────────────────────────────────────
PRODUCT = "INTARIAN_PEPPER_ROOT"
POS_LIMIT = 80
T_END_TICKS = 10000


# ── Holt linear filter ─────────────────────────────────────────────────────
ALPHA = 0.15
BETA = 0.01
B_PRIOR = 0.1
SIGMA2_INIT = 1.44
LAM_VOL = 0.97
MIN_SIGMA = 1.0
JUMP_CAP_SIGMA = 5


# ── A-S calibrated anchors ─────────────────────────────────────────────────
A_HAT = 0.0688
K_HAT = 0.5835
GAMMA = 0.03
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)


# ── Market-take on imbalance (NEW in v3) ───────────────────────────────────
# When imb is strong and aligned with drift, take asks up to L + edge.
# The edge scales with imbalance strength.
IMB_BOOST_TAKE = 5.0           # ticks of edge per unit imb for taking


# ── Adverse selection circuit breaker (NEW in v3) ──────────────────────────
# When |imb| is extreme, passive bid size is cut to avoid getting filled
# at transient bad prices.
IMB_EXTREME_Z = 2.5            # z-score threshold for extreme imb


# ── Inventory policy ──────────────────────────────────────────────────────
Q_TARGET_RATIO = 0.75
MIN_ASK_PROFIT = 3


# ── Regime thresholds (dynamic) ───────────────────────────────────────────
DRIFT_THRESHOLD = 0.3 * B_PRIOR
IMB_TAKE_Z = 1.5
SIGMA_IMB_INIT = 0.19
LAM_IMB = 0.995


# ── Robustness ─────────────────────────────────────────────────────────────
NARROW_SPREAD = 5


# ── Sizing and levels ─────────────────────────────────────────────────────
MAX_SIZE_FAV = 30
MAX_SIZE_OFF = 10
MAX_SIZE_NEU = 20
LEVELS = 3


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
            "L": self.L, "B": self.B,
            "s2": self.sigma2, "si2": self.sigma_imb2,
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
    if px is None:
        return None
    lo = best_bid + 1
    hi = best_ask - 1
    if lo > hi:
        return None
    return max(lo, min(hi, px))


def _dedup(levels: list[int | None]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for lvl in levels:
        if lvl is not None and lvl not in seen:
            seen.add(lvl)
            out.append(lvl)
    return out


class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:
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

        if best_bid is None or best_ask is None:
            if st.L is not None:
                st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        spread = best_ask - best_bid
        bv = abs(bids[best_bid])
        av = abs(asks[best_ask])

        tot = bv + av
        if tot <= 0:
            micro = (best_bid + best_ask) / 2.0
            imb = 0.0
        else:
            micro = (bv * best_ask + av * best_bid) / tot
            imb = (bv - av) / tot

        if st.L is None:
            st.L = micro

        if spread <= NARROW_SPREAD:
            st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        # ── Winsorize + Holt update ──────────────────────────────────────
        pred = st.L + st.B
        sigma = max(MIN_SIGMA, math.sqrt(st.sigma2))
        cap = JUMP_CAP_SIGMA * sigma
        innov_raw = micro - pred
        if innov_raw > cap:
            micro = pred + cap
        elif innov_raw < -cap:
            micro = pred - cap

        L_prev = st.L
        st.L = ALPHA * micro + (1.0 - ALPHA) * (L_prev + st.B)
        st.B = BETA * (st.L - L_prev) + (1.0 - BETA) * st.B

        innov = micro - pred
        st.sigma2 = LAM_VOL * st.sigma2 + (1.0 - LAM_VOL) * innov * innov
        if st.sigma2 < 0.25:
            st.sigma2 = 0.25
        sigma = math.sqrt(st.sigma2)
        sigma2 = st.sigma2

        st.sigma_imb2 = LAM_IMB * st.sigma_imb2 + (1.0 - LAM_IMB) * imb * imb
        if st.sigma_imb2 < 0.0025:
            st.sigma_imb2 = 0.0025
        sigma_imb = math.sqrt(st.sigma_imb2)

        # ── Dynamic parameters ───────────────────────────────────────────
        take_edge = max(1, int(round(sigma)))
        imb_take = IMB_TAKE_Z * sigma_imb
        imb_extreme = IMB_EXTREME_Z * sigma_imb

        # ── Regime ───────────────────────────────────────────────────────
        if st.B > DRIFT_THRESHOLD:
            fav = +1
            q_target = int(POS_LIMIT * Q_TARGET_RATIO)
        elif st.B < -DRIFT_THRESHOLD:
            fav = -1
            q_target = -int(POS_LIMIT * Q_TARGET_RATIO)
        else:
            fav = 0
            q_target = 0

        # ── A-S reservation price — NO IMB BOOST on passives (v3 fix) ───
        skew = (pos - q_target) * GAMMA * sigma2
        r = st.L - skew

        # ── Half-spread ──────────────────────────────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left

        wl = pos
        ws = pos
        fv_now = st.L

        # ── AGGRESSIVE TAKING (v3: two paths) ───────────────────────────
        #
        # Path 1 — PRICE-BASED: same as v2, take mispriced levels.
        #          In fav=+1: buy asks below L − take_edge  (rarely fires)
        #
        # Path 2 — IMBALANCE-BASED (NEW): when imb is strong AND aligned
        #          with drift, take asks up to L + dynamic_edge.
        #          This is where most real takes will fire.
        #
        if fav == +1:
            # Path 1: cheap asks (rarely fires)
            for ask_px in sorted(asks):
                if ask_px >= fv_now - take_edge:
                    break
                vol = abs(asks[ask_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty

            # Path 2: imbalance-driven market buy (NEW in v3)
            if imb >= imb_take:
                max_take_px = _to_tick(fv_now + imb * IMB_BOOST_TAKE)
                for ask_px in sorted(asks):
                    if ask_px > max_take_px:
                        break
                    vol = abs(asks[ask_px])
                    qty = min(vol, MAX_SIZE_FAV, POS_LIMIT - wl)
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

            if imb <= -imb_take:
                min_take_px = _to_tick(fv_now + imb * IMB_BOOST_TAKE)
                for bid_px in sorted(bids, reverse=True):
                    if bid_px < min_take_px:
                        break
                    vol = abs(bids[bid_px])
                    qty = min(vol, MAX_SIZE_FAV, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty

        # ── PASSIVE QUOTE LEVELS (3 depths, no imb boost) ───────────────
        bid_tight_raw = _to_tick(r - delta_star)
        ask_tight_raw = _to_tick(r + delta_star)

        bid_tight = _clamp_inside(bid_tight_raw, best_bid, best_ask)
        bid_deep = _clamp_inside(best_bid + 1, best_bid, best_ask)
        ask_tight = _clamp_inside(ask_tight_raw, best_bid, best_ask)
        ask_deep = _clamp_inside(best_ask - 1, best_bid, best_ask)

        bid_mid = None
        if bid_tight is not None and bid_deep is not None:
            bid_mid = _clamp_inside((bid_tight + bid_deep) // 2, best_bid, best_ask)
        ask_mid = None
        if ask_tight is not None and ask_deep is not None:
            ask_mid = _clamp_inside((ask_tight + ask_deep) // 2, best_bid, best_ask)

        bid_levels = _dedup([bid_tight, bid_mid, bid_deep])
        ask_levels = _dedup([ask_tight, ask_mid, ask_deep])

        # ── Phase detection ──────────────────────────────────────────────
        if fav == +1:
            phase = "ACCUM" if pos < q_target else ("HYBRID" if pos < POS_LIMIT else "REDUCE")
        elif fav == -1:
            phase = "ACCUM" if pos > q_target else ("HYBRID" if pos > -POS_LIMIT else "REDUCE")
        else:
            phase = "NEUTRAL"

        # ── Adverse selection circuit breaker (v3) ───────────────────────
        # When imbalance is extreme, reduce passive bid size to avoid
        # getting filled massively on transient spikes.
        is_extreme = abs(imb) > imb_extreme
        cb_label = ""

        # ── Sizing ───────────────────────────────────────────────────────
        if fav == +1:
            size_bid = MAX_SIZE_FAV
            if is_extreme and imb > 0:
                size_bid = max(5, size_bid // 3)
                cb_label = " CB"
            if phase == "ACCUM":
                size_ask = 0
            elif phase == "HYBRID":
                size_ask = MAX_SIZE_OFF
            else:
                size_ask = MAX_SIZE_FAV
        elif fav == -1:
            size_ask = MAX_SIZE_FAV
            if is_extreme and imb < 0:
                size_ask = max(5, size_ask // 3)
                cb_label = " CB"
            if phase == "ACCUM":
                size_bid = 0
            elif phase == "HYBRID":
                size_bid = MAX_SIZE_OFF
            else:
                size_bid = MAX_SIZE_FAV
        else:
            size_bid = MAX_SIZE_NEU
            size_ask = MAX_SIZE_NEU

        # ── Emit BIDs ────────────────────────────────────────────────────
        bid_cap = q_target if fav == +1 and phase == "ACCUM" else POS_LIMIT
        for bid_px in bid_levels:
            if fav == -1 and phase == "HYBRID" and bid_px != bid_deep:
                continue
            if fav == -1 and phase == "HYBRID" and bid_px is not None and bid_px >= int(st.L) - MIN_ASK_PROFIT:
                continue
            qty_b = min(size_bid, bid_cap - wl)
            if qty_b > 0:
                orders.append(Order(PRODUCT, bid_px, qty_b))
                wl += qty_b

        # ── Emit ASKs ───────────────────────────────────────────────────
        should_emit_ask = True
        if fav == +1 and pos < q_target:
            should_emit_ask = False
        elif fav == -1 and pos > q_target:
            should_emit_ask = False

        if should_emit_ask:
            for ask_px in ask_levels:
                if fav == +1 and phase == "HYBRID" and ask_px != ask_deep:
                    continue
                if fav == +1 and phase == "HYBRID" and ask_px is not None and ask_px <= int(st.L) + MIN_ASK_PROFIT:
                    continue
                qty_a = min(size_ask, ws + POS_LIMIT)
                if qty_a > 0:
                    orders.append(Order(PRODUCT, ask_px, -qty_a))
                    ws -= qty_a

        # ── Log ──────────────────────────────────────────────────────────
        took = "TAKE" if any(
            (o.quantity > 0 and o.price >= fv_now) or
            (o.quantity < 0 and o.price <= fv_now)
            for o in orders
        ) else ""
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} {phase}{cb_label} "
            f"B={st.B:+.4f} imb={imb:+.2f} L={st.L:.1f} r={r:.1f} "
            f"te={take_edge} it={imb_take:.2f} ie={imb_extreme:.2f} "
            f"b={bid_levels} a={ask_levels} n={len(orders)} {took}"
        )

        return {PRODUCT: orders}, 0, st.to_json()
