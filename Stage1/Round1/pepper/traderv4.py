"""
INTARIAN_PEPPER_ROOT trader v4 — IMC Prosperity 4, Round 1.

v4 = drift-symmetric signal architecture
─────────────────────────────────────────
Two complementary signals are tracked and used differently depending on
the drift direction:

  Signal P (PRICE event):
    delta_ask = ask_price_1 − ask_ema       — signed change of the ask
    delta_bid = bid_price_1 − bid_ema       — signed change of the bid

    ask_drop  = max(0, −delta_ask)          — bullish reversion event
    bid_spike = max(0, +delta_bid)          — bearish reversion event
    (and symmetric ask_pop, bid_drop)

    Dynamic thresholds:
      thresh_ask = Z · sigma(delta_ask)     — z-score on EWMA variance
      thresh_bid = Z · sigma(delta_bid)
    Updated every tick from the empirical distribution.

  Signal V (VOLUME imbalance):  imb = (bv − av) / (bv + av)
    Continuous bullish-when-positive signal with stable IC ≈ 0.56.

Drift-symmetric application:

  fav = +1 (bullish drift):
    - Market BUY when ask_drop ≥ thresh_ask     (Path B, take ask plunge)
    - Suppress IMB_BOOST on passive BID when bid_spike ≥ thresh_bid
      (the spike is a trap, IC −0.44, do not chase it)
    - Bid SIZE reduced when bid_spike extreme (circuit breaker)

  fav = -1 (bearish drift):
    - Market SELL when bid_spike ≥ thresh_bid    (mirror Path B)
    - Suppress IMB_BOOST on passive ASK when ask_drop ≥ thresh_ask
      (symmetric trap)
    - Ask SIZE reduced when ask_drop extreme

  fav = 0:  no directional signal use; pure A-S.

Inherited from v3:  Holt filter, A-S half-spread, 3-phase inventory,
asymmetric regime takes, dynamic take_edge from sigma.

Calibration anchors: A_HAT=0.0688, K_HAT=0.5835, B_PRIOR=0.1, ALPHA=0.15,
BETA=0.01.  Signal thresholds are FULLY dynamic (no hardcoded numbers
on imb_take, ask drop magnitude, bid spike magnitude).
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


# ── Signal V (imbalance) — passive boost ──────────────────────────────────
IMB_BOOST_PASSIVE = 3.0          # restored, gated by trap detection
IMB_EXTREME_Z = 2.5              # z-score for circuit breaker (extreme imb)
SIGMA_IMB_INIT = 0.19
LAM_IMB = 0.995


# ── Signal P (price events) — EWMA price tracking + variance ──────────────
LAM_PRICE_EMA = 0.9              # half-life ~7 ticks on price EMA
LAM_PRICE_VAR = 0.99             # half-life ~70 ticks on price variance
SIGMA_PRICE_INIT = 1.5           # initial std of price changes
Z_PRICE_EVENT = 2.0              # 2-sigma threshold for "drop" / "spike" events


# ── Inventory policy ──────────────────────────────────────────────────────
Q_TARGET_RATIO = 0.75
MIN_ASK_PROFIT = 3


# ── Regime thresholds ─────────────────────────────────────────────────────
DRIFT_THRESHOLD = 0.3 * B_PRIOR


# ── Robustness ─────────────────────────────────────────────────────────────
NARROW_SPREAD = 5


# ── Sizing and levels ─────────────────────────────────────────────────────
MAX_SIZE_FAV = 30
MAX_SIZE_OFF = 10
MAX_SIZE_NEU = 20
LEVELS = 3


# ──────────────────────────────────────────────────────────────────────────
class State:
    __slots__ = (
        "L", "B", "sigma2",
        "sigma_imb2",
        "ask_ema", "bid_ema",
        "sigma_ask2", "sigma_bid2",
    )

    def __init__(
        self,
        L: float | None = None,
        B: float = B_PRIOR,
        sigma2: float = SIGMA2_INIT,
        sigma_imb2: float = SIGMA_IMB_INIT ** 2,
        ask_ema: float | None = None,
        bid_ema: float | None = None,
        sigma_ask2: float = SIGMA_PRICE_INIT ** 2,
        sigma_bid2: float = SIGMA_PRICE_INIT ** 2,
    ) -> None:
        self.L = L
        self.B = B
        self.sigma2 = sigma2
        self.sigma_imb2 = sigma_imb2
        self.ask_ema = ask_ema
        self.bid_ema = bid_ema
        self.sigma_ask2 = sigma_ask2
        self.sigma_bid2 = sigma_bid2

    def to_json(self) -> str:
        return json.dumps({
            "L": self.L, "B": self.B,
            "s2": self.sigma2, "si2": self.sigma_imb2,
            "ae": self.ask_ema, "be": self.bid_ema,
            "sa2": self.sigma_ask2, "sb2": self.sigma_bid2,
        })

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            L_val = d.get("L")
            ae = d.get("ae")
            be = d.get("be")
            return cls(
                L=float(L_val) if L_val is not None else None,
                B=float(d.get("B", B_PRIOR)),
                sigma2=float(d.get("s2", SIGMA2_INIT)),
                sigma_imb2=float(d.get("si2", SIGMA_IMB_INIT ** 2)),
                ask_ema=float(ae) if ae is not None else None,
                bid_ema=float(be) if be is not None else None,
                sigma_ask2=float(d.get("sa2", SIGMA_PRICE_INIT ** 2)),
                sigma_bid2=float(d.get("sb2", SIGMA_PRICE_INIT ** 2)),
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

        # ── Holt update ──────────────────────────────────────────────────
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

        # ── Imbalance variance EWMA ──────────────────────────────────────
        st.sigma_imb2 = LAM_IMB * st.sigma_imb2 + (1.0 - LAM_IMB) * imb * imb
        if st.sigma_imb2 < 0.0025:
            st.sigma_imb2 = 0.0025
        sigma_imb = math.sqrt(st.sigma_imb2)

        # ── PRICE EVENT TRACKERS (NEW in v4) ─────────────────────────────
        # Compute deltas BEFORE updating EMAs (use previous EMA as baseline)
        if st.ask_ema is None:
            st.ask_ema = float(best_ask)
        if st.bid_ema is None:
            st.bid_ema = float(best_bid)

        delta_ask = best_ask - st.ask_ema
        delta_bid = best_bid - st.bid_ema

        # Update price variance EWMAs
        st.sigma_ask2 = LAM_PRICE_VAR * st.sigma_ask2 + (1 - LAM_PRICE_VAR) * delta_ask * delta_ask
        st.sigma_bid2 = LAM_PRICE_VAR * st.sigma_bid2 + (1 - LAM_PRICE_VAR) * delta_bid * delta_bid
        sigma_ask = max(0.5, math.sqrt(st.sigma_ask2))
        sigma_bid = max(0.5, math.sqrt(st.sigma_bid2))

        # Now update price EMAs
        st.ask_ema = LAM_PRICE_EMA * st.ask_ema + (1 - LAM_PRICE_EMA) * best_ask
        st.bid_ema = LAM_PRICE_EMA * st.bid_ema + (1 - LAM_PRICE_EMA) * best_bid

        # Event values
        ask_drop = max(0.0, -delta_ask)
        ask_pop = max(0.0, delta_ask)
        bid_spike = max(0.0, delta_bid)
        bid_drop = max(0.0, -delta_bid)

        # Dynamic z-score thresholds
        thresh_ask = Z_PRICE_EVENT * sigma_ask
        thresh_bid = Z_PRICE_EVENT * sigma_bid
        imb_extreme = IMB_EXTREME_Z * sigma_imb

        # ── Dynamic A-S parameters ───────────────────────────────────────
        take_edge = max(1, int(round(sigma)))

        # ── Regime detection ─────────────────────────────────────────────
        if st.B > DRIFT_THRESHOLD:
            fav = +1
            q_target = int(POS_LIMIT * Q_TARGET_RATIO)
        elif st.B < -DRIFT_THRESHOLD:
            fav = -1
            q_target = -int(POS_LIMIT * Q_TARGET_RATIO)
        else:
            fav = 0
            q_target = 0

        # ── Half-spread ──────────────────────────────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left

        # ── A-S reservation prices — DRIFT-SYMMETRIC IMB GATE ────────────
        skew = (pos - q_target) * GAMMA * sigma2
        r_bid_base = st.L - skew
        r_ask_base = st.L - skew

        # Gate IMB_BOOST per side based on the trap signal in the relevant regime
        bid_trap = (fav == +1) and (bid_spike >= thresh_bid)
        ask_trap = (fav == -1) and (ask_drop >= thresh_ask)

        # In bullish regime: boost the bid only if no bid_spike trap
        # In bearish regime: boost the ask only if no ask_drop trap
        if fav == +1 and not bid_trap:
            r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
            r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb
        elif fav == -1 and not ask_trap:
            r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
            r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb
        elif fav == 0:
            r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
            r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb
        else:
            # Trap detected — apply boost only to the SAFE side
            if bid_trap:
                r_bid = r_bid_base                            # bid stays at base (no chase)
                r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb
            else:  # ask_trap
                r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
                r_ask = r_ask_base

        # Worst-case-fully-filled trackers
        wl = pos
        ws = pos
        fv_now = st.L

        # ── AGGRESSIVE TAKING — DRIFT-SYMMETRIC PRICE-EVENT TRIGGER ──────
        take_event = ""
        if fav == +1 and ask_drop >= thresh_ask:
            # Path B: ask plunge in bullish regime → market BUY
            # Take asks up to L + ask_drop (price scales with the drop magnitude)
            max_take_px = _to_tick(fv_now + ask_drop)
            for ask_px in sorted(asks):
                if ask_px > max_take_px:
                    break
                vol = abs(asks[ask_px])
                qty = min(vol, MAX_SIZE_FAV, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty
                    take_event = f"ASK_DROP({ask_drop:.1f}>{thresh_ask:.1f})"

        elif fav == -1 and bid_spike >= thresh_bid:
            # Path B mirror: bid spike in bearish regime → market SELL
            min_take_px = _to_tick(fv_now - bid_spike)
            for bid_px in sorted(bids, reverse=True):
                if bid_px < min_take_px:
                    break
                vol = abs(bids[bid_px])
                qty = min(vol, MAX_SIZE_FAV, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty
                    take_event = f"BID_SPIKE({bid_spike:.1f}>{thresh_bid:.1f})"

        # Fallback: Path A — pure imb-based take (rarely fires after Path B exists)
        # Disabled in v4 since Path B is more selective and reliable.

        # Price-mispricing path (kept from v2, rarely fires)
        if fav == +1 and not take_event:
            for ask_px in sorted(asks):
                if ask_px >= fv_now - take_edge:
                    break
                vol = abs(asks[ask_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty
        elif fav == -1 and not take_event:
            for bid_px in sorted(bids, reverse=True):
                if bid_px <= fv_now + take_edge:
                    break
                vol = abs(bids[bid_px])
                qty = min(vol, 2 * MAX_SIZE_FAV, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty

        # ── PASSIVE QUOTE LEVELS (3 depths) ─────────────────────────────
        bid_tight_raw = _to_tick(r_bid - delta_star)
        ask_tight_raw = _to_tick(r_ask + delta_star)

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

        # ── Sizing with adverse-selection circuit breaker ───────────────
        cb_label = ""
        is_extreme_imb = abs(imb) > imb_extreme

        if fav == +1:
            size_bid = MAX_SIZE_FAV
            # CB: imb extreme positive in bullish regime → reduce bid (trap likely)
            if is_extreme_imb and imb > 0:
                size_bid = max(5, size_bid // 3)
                cb_label = " CB-IMB"
            # Additional CB on bid_spike trap
            if bid_trap:
                size_bid = max(5, size_bid // 2)
                cb_label += " CB-BSPIKE"
            if phase == "ACCUM":
                size_ask = 0
            elif phase == "HYBRID":
                size_ask = MAX_SIZE_OFF
            else:
                size_ask = MAX_SIZE_FAV
        elif fav == -1:
            size_ask = MAX_SIZE_FAV
            if is_extreme_imb and imb < 0:
                size_ask = max(5, size_ask // 3)
                cb_label = " CB-IMB"
            if ask_trap:
                size_ask = max(5, size_ask // 2)
                cb_label += " CB-ADROP"
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
        gate_label = ""
        if bid_trap:
            gate_label = " BIDTRAP"
        elif ask_trap:
            gate_label = " ASKTRAP"
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} {phase}{cb_label}{gate_label} "
            f"B={st.B:+.4f} imb={imb:+.2f} L={st.L:.1f} "
            f"adrop={ask_drop:.1f}/{thresh_ask:.1f} bspike={bid_spike:.1f}/{thresh_bid:.1f} "
            f"b={bid_levels} a={ask_levels} n={len(orders)} {take_event}"
        )

        return {PRODUCT: orders}, 0, st.to_json()
