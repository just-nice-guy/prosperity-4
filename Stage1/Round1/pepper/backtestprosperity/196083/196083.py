"""
INTARIAN_PEPPER_ROOT trader v7 — IMC Prosperity 4, Round 1.

v7 fixes 3 issues found in v6 (visualizer audit on 180495):

1.  A-S MODEL FREED — v6 had 3 hardcoded constraints that overrode A-S:
    `_clamp_inside` forced quotes between best_bid+1 and best_ask-1 (no
    joining or queueing behind L1). `TIGHT_OFFSET_FROM_L1=2` capped the
    tight quote at 2 ticks inside L1 even when A-S delta_star said deeper.
    `bid_deep = best_bid + 1` was hardcoded, decorrelated from A-S. v7
    lets A-S decide the tight, places deep AT best_bid/best_ask (joins
    the L1 queue for passive priority).

2.  BID_TRAP NOW ZEROES PASSIVE BIDS — v6 only halved size_bid on bid_spike
    detection (30→15), still posting 3 levels × 15 = 45 units of adverse-
    selectable bids. v7 sets size_bid = 0 entirely. Symmetric on ask_trap.
    PATH_C_POS_GATE lowered 70→40 so Path C derisks earlier into spikes.

3.  PATH B LIGHT TRIGGER FREED FROM IMB GATE — v6 required imb ≥ +0.285 to
    confirm light ask_drops, but ask_drops happen WHEN sellers attack →
    imb is usually negative at that exact tick → most medium drops were
    filtered out. v7 only excludes when imb is STRONGLY negative
    (imb < -imb_take_confirm). Symmetric on bid_spike in fav=-1.

Inherited from v6: Holt filter, drift-symmetric Path B/C, BIDTRAP/ASKTRAP
gates on reservation prices, 3-phase inventory, dynamic thresholds.
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


# ════════════════════════════════════════════════════════════════════════
# QUOTE TIGHTNESS PARAMETERS — distance of our tight quote from mid (L)
# ════════════════════════════════════════════════════════════════════════
# Tight bid is placed at:  L - skew + IMB*imb - delta_star
# Tight ask is placed at:  L - skew + IMB*imb + delta_star
# where delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma^2 * time_left
#       DELTA_STAR_FLOW = (1/GAMMA) * ln(1 + GAMMA/K_HAT)
#
# Knobs (in order of impact):
#
# 1. K_HAT — quote-arrival sensitivity. HIGHER = tighter (closer to mid).
#    Reference values:
#      K_HAT = 0.5835 (calibrated)  → delta_star ≈ 1.7 ticks  [too passive]
#      K_HAT = 1.0                  → delta_star ≈ 1.0 ticks
#      K_HAT = 1.5                  → delta_star ≈ 0.7 ticks  [current]
#      K_HAT = 2.5                  → delta_star ≈ 0.4 ticks  [very tight]
#
# 2. GAMMA — risk aversion. Affects ONLY the inventory term of delta_star.
#    Higher GAMMA = quotes pushed wider when sigma2 grows. Default 0.03 is
#    fine; pushing it doesn't materially shift placement relative to mid.
#
# 3. MIN_ASK_PROFIT (and MIN_BID_DISCOUNT below) — hard floors that override
#    A-S when phase requires a minimum margin around L. Set to 1 so they
#    don't shadow A-S's tight quote in normal regime.
#
# 4. TIGHT_EDGE_SCALE — explicit multiplier on delta_star if you want to
#    decouple tightness from K_HAT calibration. 1.0 = use A-S directly,
#    0.5 = quote half-distance from mid, 1.5 = wider than A-S.
# ════════════════════════════════════════════════════════════════════════
A_HAT = 0.0688
K_HAT = 1.5                          # ↑ raise → tighter quotes (closer to mid)
GAMMA = 0.03                         # ↑ raise → wider when vol high
TIGHT_EDGE_SCALE = 1.0               # final multiplier on delta_star
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)


# ── Signal V (imbalance) ──────────────────────────────────────────────────
IMB_BOOST_PASSIVE = 3.0
IMB_EXTREME_Z = 2.5
SIGMA_IMB_INIT = 0.19
LAM_IMB = 0.995
IMB_TAKE_CONFIRM_Z = 1.5         # used only as NEGATIVE guard now (v7)


# ── Signal P (price events) ───────────────────────────────────────────────
LAM_PRICE_EMA = 0.9
LAM_PRICE_VAR = 0.99
SIGMA_PRICE_INIT = 1.5
Z_PRICE_HEAVY = 3.0              # solo trigger
Z_PRICE_LIGHT = 2.0              # light trigger (no longer needs +imb)
PATH_C_POS_GATE = 40             # v7: was 70, derisk earlier into spikes


# ── Inventory policy ──────────────────────────────────────────────────────
Q_TARGET_RATIO = 0.75
# Hard floors enforced at emit time (override A-S when phase requires margin).
# Set both to 1 so A-S is the dominant placement mechanism in normal regime.
# Raise (e.g. 3) to force wider asks/bids in REDUCE/HYBRID phases.
MIN_ASK_PROFIT = 1                   # ask quote must be ≥ L + MIN_ASK_PROFIT + 1
MIN_BID_DISCOUNT = 1                 # bid quote must be ≤ L - MIN_BID_DISCOUNT - 1 (HYBRID only)
# v7: A-S model decides tight quote distance — no TIGHT_OFFSET_FROM_L1 cap.
# Deep quote sits AT L1 (joins queue) for passive priority.


# ── Regime threshold ──────────────────────────────────────────────────────
DRIFT_THRESHOLD = 0.3 * B_PRIOR


# ── Robustness ─────────────────────────────────────────────────────────────
NARROW_SPREAD = 5


# ── Sizing and levels ─────────────────────────────────────────────────────
MAX_SIZE_FAV = 30
MAX_SIZE_OFF = 10
MAX_SIZE_NEU = 20
MAX_SIZE_DERISK = 12
LEVELS = 3


# ──────────────────────────────────────────────────────────────────────────
class State:
    __slots__ = (
        "L", "B", "sigma2", "sigma_imb2",
        "ask_ema", "bid_ema", "sigma_ask2", "sigma_bid2",
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
            "L": self.L, "B": self.B, "s2": self.sigma2, "si2": self.sigma_imb2,
            "ae": self.ask_ema, "be": self.bid_ema,
            "sa2": self.sigma_ask2, "sb2": self.sigma_bid2,
        })

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            L_val = d.get("L")
            ae, be = d.get("ae"), d.get("be")
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


def _clamp_bid(px: int | None, best_bid: int, best_ask: int) -> int | None:
    """v7: bids may sit AT best_bid (join L1) up to best_ask-1 (cross would be take)."""
    if px is None:
        return None
    return max(best_bid, min(best_ask - 1, px))


def _clamp_ask(px: int | None, best_bid: int, best_ask: int) -> int | None:
    """v7: asks may sit from best_bid+1 (cross would be take) up to best_ask (join L1)."""
    if px is None:
        return None
    return max(best_bid + 1, min(best_ask, px))


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

        # ── Imbalance variance ───────────────────────────────────────────
        st.sigma_imb2 = LAM_IMB * st.sigma_imb2 + (1.0 - LAM_IMB) * imb * imb
        if st.sigma_imb2 < 0.0025:
            st.sigma_imb2 = 0.0025
        sigma_imb = math.sqrt(st.sigma_imb2)
        imb_take_confirm = IMB_TAKE_CONFIRM_Z * sigma_imb

        # ── Price event trackers ─────────────────────────────────────────
        if st.ask_ema is None:
            st.ask_ema = float(best_ask)
        if st.bid_ema is None:
            st.bid_ema = float(best_bid)

        delta_ask = best_ask - st.ask_ema
        delta_bid = best_bid - st.bid_ema

        st.sigma_ask2 = LAM_PRICE_VAR * st.sigma_ask2 + (1 - LAM_PRICE_VAR) * delta_ask * delta_ask
        st.sigma_bid2 = LAM_PRICE_VAR * st.sigma_bid2 + (1 - LAM_PRICE_VAR) * delta_bid * delta_bid
        sigma_ask = max(0.5, math.sqrt(st.sigma_ask2))
        sigma_bid = max(0.5, math.sqrt(st.sigma_bid2))

        st.ask_ema = LAM_PRICE_EMA * st.ask_ema + (1 - LAM_PRICE_EMA) * best_ask
        st.bid_ema = LAM_PRICE_EMA * st.bid_ema + (1 - LAM_PRICE_EMA) * best_bid

        ask_drop = max(0.0, -delta_ask)
        bid_spike = max(0.0, delta_bid)

        thresh_ask_heavy = Z_PRICE_HEAVY * sigma_ask
        thresh_ask_light = Z_PRICE_LIGHT * sigma_ask
        thresh_bid_heavy = Z_PRICE_HEAVY * sigma_bid
        thresh_bid_light = Z_PRICE_LIGHT * sigma_bid
        imb_extreme = IMB_EXTREME_Z * sigma_imb

        take_edge = max(1, int(round(sigma)))

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

        # ── Half-spread (A-S) ────────────────────────────────────────────
        # delta_star = distance of tight quote from reservation price.
        # Two terms: DELTA_STAR_FLOW (from K_HAT/GAMMA calibration) +
        # inventory term (grows with sigma^2 and time remaining).
        # TIGHT_EDGE_SCALE multiplies the whole thing if you want to override
        # A-S aggressiveness without retuning K_HAT.
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = TIGHT_EDGE_SCALE * (
            DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left
        )

        # ── Reservation prices with side-specific imb gate ───────────────
        skew = (pos - q_target) * GAMMA * sigma2
        r_bid_base = st.L - skew
        r_ask_base = st.L - skew

        bid_trap = (fav == +1) and (bid_spike >= thresh_bid_light)
        ask_trap = (fav == -1) and (ask_drop >= thresh_ask_light)

        if bid_trap:
            r_bid = r_bid_base
            r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb
        elif ask_trap:
            r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
            r_ask = r_ask_base
        else:
            r_bid = r_bid_base + IMB_BOOST_PASSIVE * imb
            r_ask = r_ask_base + IMB_BOOST_PASSIVE * imb

        wl = pos
        ws = pos
        fv_now = st.L
        take_event = ""

        # ── PATH B — Market take on ASK_DROP (v7: imb gate relaxed) ─────
        # Heavy (≥3σ): solo fire
        # Light (≥2σ): fires UNLESS imb is strongly negative (-imb_take_confirm).
        # Rationale: ask_drops naturally come with negative imb (sellers attack),
        # so requiring +imb confirmation filtered out 80% of real opportunities.
        # Drift +1 already confirms direction; only veto on EXTREME bearish imb.
        if fav == +1:
            ask_drop_fires = (
                ask_drop >= thresh_ask_heavy
                or (ask_drop >= thresh_ask_light and imb >= -imb_take_confirm)
            )
            if ask_drop_fires:
                max_take_px = _to_tick(fv_now + ask_drop)
                for ask_px in sorted(asks):
                    if ask_px > max_take_px:
                        break
                    vol = abs(asks[ask_px])
                    qty = min(vol, MAX_SIZE_FAV, POS_LIMIT - wl)
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, qty))
                        wl += qty
                        if not take_event:
                            tag = "HEAVY" if ask_drop >= thresh_ask_heavy else "LIGHT"
                            take_event = f"PATH_B_{tag}({ask_drop:.1f})"

            # PATH C — Opportunistic derisk on bid_spike. v7: gate lowered
            # 70→40 so we sell into spikes earlier (not just when saturated).
            elif pos >= PATH_C_POS_GATE and bid_spike >= thresh_bid_heavy:
                min_take_px = _to_tick(fv_now - bid_spike)
                for bid_px in sorted(bids, reverse=True):
                    if bid_px < min_take_px:
                        break
                    vol = abs(bids[bid_px])
                    qty = min(vol, MAX_SIZE_DERISK, ws + POS_LIMIT, max(0, pos - q_target))
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty
                        if not take_event:
                            take_event = f"PATH_C_DERISK({bid_spike:.1f}>{thresh_bid_heavy:.1f},pos={pos})"

        elif fav == -1:
            bid_spike_fires_neg = (
                bid_spike >= thresh_bid_heavy
                or (bid_spike >= thresh_bid_light and imb <= imb_take_confirm)
            )
            if bid_spike_fires_neg:
                min_take_px = _to_tick(fv_now - bid_spike)
                for bid_px in sorted(bids, reverse=True):
                    if bid_px < min_take_px:
                        break
                    vol = abs(bids[bid_px])
                    qty = min(vol, MAX_SIZE_FAV, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty
                        if not take_event:
                            take_event = f"PATH_B_BEAR({bid_spike:.1f})"
            elif pos <= -PATH_C_POS_GATE and ask_drop >= thresh_ask_heavy:
                max_take_px = _to_tick(fv_now + ask_drop)
                for ask_px in sorted(asks):
                    if ask_px > max_take_px:
                        break
                    vol = abs(asks[ask_px])
                    qty = min(vol, MAX_SIZE_DERISK, POS_LIMIT - wl, max(0, q_target - pos))
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, qty))
                        wl += qty
                        if not take_event:
                            take_event = f"PATH_C_DERISK_BEAR({ask_drop:.1f},pos={pos})"

        # Price-mispricing fallback (very rarely fires)
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

        # ── PASSIVE QUOTES — A-S DRIVES TIGHT, DEEP JOINS L1 (v7) ────────
        # Tight: A-S delta_star alone, no L1-distance cap. If A-S says quote
        # 4 ticks inside on a wide spread, we trust it.
        # Deep:  AT best_bid / best_ask — joins the L1 queue for passive
        # priority instead of jumping inside.
        # Mid:   midpoint between tight and deep.
        bid_tight_raw = _to_tick(r_bid - delta_star)
        ask_tight_raw = _to_tick(r_ask + delta_star)

        bid_tight = _clamp_bid(bid_tight_raw, best_bid, best_ask)
        bid_deep = _clamp_bid(best_bid, best_bid, best_ask)
        ask_tight = _clamp_ask(ask_tight_raw, best_bid, best_ask)
        ask_deep = _clamp_ask(best_ask, best_bid, best_ask)

        bid_mid = None
        if bid_tight is not None and bid_deep is not None:
            bid_mid = _clamp_bid((bid_tight + bid_deep) // 2, best_bid, best_ask)
        ask_mid = None
        if ask_tight is not None and ask_deep is not None:
            ask_mid = _clamp_ask((ask_tight + ask_deep) // 2, best_bid, best_ask)

        bid_levels = _dedup([bid_tight, bid_mid, bid_deep])
        ask_levels = _dedup([ask_tight, ask_mid, ask_deep])

        # ── Phase ────────────────────────────────────────────────────────
        if fav == +1:
            phase = "ACCUM" if pos < q_target else ("HYBRID" if pos < POS_LIMIT else "REDUCE")
        elif fav == -1:
            phase = "ACCUM" if pos > q_target else ("HYBRID" if pos > -POS_LIMIT else "REDUCE")
        else:
            phase = "NEUTRAL"

        cb_label = ""
        is_extreme_imb = abs(imb) > imb_extreme

        if fav == +1:
            size_bid = MAX_SIZE_FAV
            if is_extreme_imb and imb > 0:
                size_bid = max(5, size_bid // 3)
                cb_label = " CB-IMB"
            # v7: bid_trap → ZERO passive bids (was halve). Bid_spike has
            # IC≈-0.44 short-term; any passive fill is adverse selection.
            if bid_trap:
                size_bid = 0
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
            # v7: symmetric — ask_trap zeroes passive asks.
            if ask_trap:
                size_ask = 0
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
                if fav == +1 and ask_px is not None and ask_px <= int(st.L) + MIN_ASK_PROFIT:
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
            f"adrop={ask_drop:.1f}/{thresh_ask_light:.1f}/{thresh_ask_heavy:.1f} "
            f"bspike={bid_spike:.1f}/{thresh_bid_light:.1f}/{thresh_bid_heavy:.1f} "
            f"b={bid_levels} a={ask_levels} n={len(orders)} {take_event}"
        )

        return {PRODUCT: orders}, 0, st.to_json()