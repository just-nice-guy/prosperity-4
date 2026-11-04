"""
Final merged trader — Round 1.
  - INTARIAN_PEPPER_ROOT traded by v10 (pre-flip panic on cum-innov z-score).
  - ASH_COATED_OSMIUM traded by moyen2 (A-S micro-price + taker on FV break).

No logic changes to either strategy. Only combined state handling so both
run inside a single Trader.run(). Shared traderData layout:
    {"pepper": "<pepper-state-json-string>", "ash": {"fv_hist": [...]}}
"""
from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ══════════════════════════════════════════════════════════════════════════
# PEPPER (INTARIAN_PEPPER_ROOT) — traderv10 verbatim
# ══════════════════════════════════════════════════════════════════════════
PRODUCT = "INTARIAN_PEPPER_ROOT"
POS_LIMIT = 80
T_END_TICKS = 10000

ALPHA = 0.15
BETA = 0.01
B_PRIOR = 0.1
SIGMA2_INIT = 1.44
LAM_VOL = 0.97
MIN_SIGMA = 1.0
JUMP_CAP_SIGMA = 5

A_HAT = 0.0688
K_HAT = 0.5835
GAMMA = 0.03
TIGHT_EDGE_SCALE = 1.0
LEVEL_MULTIPLIERS = (1.0, 2.0, 3.0)
SPREAD_REF = 8
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)

IMB_BOOST_PASSIVE = 3.0
IMB_EXTREME_Z = 2.5
SIGMA_IMB_INIT = 0.19
LAM_IMB = 0.995
IMB_TAKE_CONFIRM_Z = 1.5

LAM_PRICE_EMA = 0.9
LAM_PRICE_VAR = 0.99
SIGMA_PRICE_INIT = 1.5
Z_PRICE_HEAVY = 3.0
Z_PRICE_LIGHT = 2.0
PATH_C_POS_GATE = 65

Q_TARGET_RATIO = 0.75
MIN_ASK_PROFIT = 1
MIN_BID_DISCOUNT = 1

DRIFT_THRESHOLD = 0.3 * B_PRIOR

NARROW_SPREAD = 5

MAX_SIZE_FAV = 30
MAX_SIZE_OFF = 10
MAX_SIZE_NEU = 20
MAX_SIZE_DERISK = 12
LEVELS = 3

INNOV_BUFFER_LEN = 40
DRIFT_FLIP_RISK_Z = 2.0
DRIFT_FLIP_B_MIN = 0.02
DRIFT_FLIP_POS_GATE = 15
DRIFT_FLIP_MKT_BASE = 10
DRIFT_FLIP_MKT_CAP = 40
DRIFT_FLIP_LIM_BASE = 10
DRIFT_FLIP_LIM_CAP = 40
DRIFT_FLIP_WARMUP = 40


class PepperState:
    __slots__ = (
        "L", "B", "sigma2", "sigma_imb2",
        "ask_ema", "bid_ema", "sigma_ask2", "sigma_bid2",
        "innov_buf",
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
        innov_buf: list[float] | None = None,
    ) -> None:
        self.L = L
        self.B = B
        self.sigma2 = sigma2
        self.sigma_imb2 = sigma_imb2
        self.ask_ema = ask_ema
        self.bid_ema = bid_ema
        self.sigma_ask2 = sigma_ask2
        self.sigma_bid2 = sigma_bid2
        self.innov_buf = innov_buf if innov_buf is not None else []

    def to_json(self) -> str:
        return json.dumps({
            "L": self.L, "B": self.B, "s2": self.sigma2, "si2": self.sigma_imb2,
            "ae": self.ask_ema, "be": self.bid_ema,
            "sa2": self.sigma_ask2, "sb2": self.sigma_bid2,
            "ib": self.innov_buf,
        })

    @classmethod
    def from_json(cls, text: str) -> "PepperState":
        try:
            d = json.loads(text)
            L_val = d.get("L")
            ae, be = d.get("ae"), d.get("be")
            ib = d.get("ib")
            return cls(
                L=float(L_val) if L_val is not None else None,
                B=float(d.get("B", B_PRIOR)),
                sigma2=float(d.get("s2", SIGMA2_INIT)),
                sigma_imb2=float(d.get("si2", SIGMA_IMB_INIT ** 2)),
                ask_ema=float(ae) if ae is not None else None,
                bid_ema=float(be) if be is not None else None,
                sigma_ask2=float(d.get("sa2", SIGMA_PRICE_INIT ** 2)),
                sigma_bid2=float(d.get("sb2", SIGMA_PRICE_INIT ** 2)),
                innov_buf=[float(x) for x in ib] if isinstance(ib, list) else [],
            )
        except Exception:
            return cls()


def _to_tick(x: float) -> int:
    return int(round(x))


def _clamp_bid_no_cross(px: int | None, best_ask: int) -> int | None:
    if px is None:
        return None
    return min(px, best_ask - 1)


def _clamp_ask_no_cross(px: int | None, best_bid: int) -> int | None:
    if px is None:
        return None
    return max(px, best_bid + 1)


def _dedup(levels: list[int | None]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for lvl in levels:
        if lvl is not None and lvl not in seen:
            seen.add(lvl)
            out.append(lvl)
    return out


# ══════════════════════════════════════════════════════════════════════════
# ASH (ASH_COATED_OSMIUM) — moyen2 verbatim (constants prefixed)
# ══════════════════════════════════════════════════════════════════════════
ASH_PRODUCT = "ASH_COATED_OSMIUM"
ASH_POS_LIMIT = 80
ASH_SIZE = 12
ASH_SIZE_TAKER = 12

# A-S params
ASH_GAMMA = 0.05
ASH_ALPHA = -3.8
ASH_KAPPA = 0.135
ASH_T = 1.0

# Taker params
ASH_K_SIGMA = 0
ASH_BETA_VOL = 4
ASH_N_LEVELS = 2
ASH_W_DECAY = 0.12

ASH_AVG_DURATION = 5
ASH_AVG_DECAY = 0.19


# ══════════════════════════════════════════════════════════════════════════
# Merged Trader
# ══════════════════════════════════════════════════════════════════════════
class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:
        # Parse merged traderData
        try:
            outer = json.loads(state.traderData) if state.traderData else {}
            if not isinstance(outer, dict):
                outer = {}
        except Exception:
            outer = {}
        pepper_td_str = outer.get("pepper") or ""
        ash_td = outer.get("ash") if isinstance(outer.get("ash"), dict) else {}

        pepper_orders, new_pepper_td = self._run_pepper(state, pepper_td_str)
        ash_orders, new_ash_td = self._run_ash(state, ash_td)

        result: dict[str, list[Order]] = {}
        if pepper_orders:
            result[PRODUCT] = pepper_orders
        if ash_orders:
            result[ASH_PRODUCT] = ash_orders

        merged_td = json.dumps({"pepper": new_pepper_td, "ash": new_ash_td})
        return result, 0, merged_td

    # ─────────────────────────────────────────────────────────────────────
    # PEPPER block — identical to traderv10.py
    # ─────────────────────────────────────────────────────────────────────
    def _run_pepper(
        self, state: TradingState, pepper_td_str: str
    ) -> tuple[list[Order], str]:
        st = PepperState.from_json(pepper_td_str) if pepper_td_str else PepperState()
        pos = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if depth is None:
            return orders, st.to_json()

        bids = depth.buy_orders or {}
        asks = depth.sell_orders or {}
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None

        if best_bid is None or best_ask is None:
            if st.L is not None:
                st.L = st.L + st.B
            return orders, st.to_json()

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
            return orders, st.to_json()

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

        # ── Pre-flip predictor (v10) ─────────────────────────────────────
        st.innov_buf.append(innov)
        if len(st.innov_buf) > INNOV_BUFFER_LEN:
            st.innov_buf = st.innov_buf[-INNOV_BUFFER_LEN:]
        L_buf = len(st.innov_buf)
        if L_buf >= DRIFT_FLIP_WARMUP and abs(st.B) > DRIFT_FLIP_B_MIN:
            cum_innov = sum(st.innov_buf)
            z_pressure = cum_innov / (max(MIN_SIGMA, sigma) * math.sqrt(L_buf))
            sign_B = 1.0 if st.B > 0 else -1.0
            pressure_against_B = -z_pressure * sign_B
        else:
            pressure_against_B = 0.0

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

        # ── Half-spread (A-S + spread scaling) ───────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        spread_scale = max(1.0, spread / SPREAD_REF)
        delta_star = TIGHT_EDGE_SCALE * spread_scale * (
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

        # ════════════════════════════════════════════════════════════════
        # PATH D — PRE-FLIP PANIC
        # ════════════════════════════════════════════════════════════════
        sign_B = 1 if st.B > 0 else (-1 if st.B < 0 else 0)
        sign_pos = 1 if pos > 0 else (-1 if pos < 0 else 0)
        drift_panic = (
            pressure_against_B >= DRIFT_FLIP_RISK_Z
            and sign_B != 0
            and sign_pos == sign_B
            and abs(pos) > DRIFT_FLIP_POS_GATE
        )
        skip_normal_logic = False

        if drift_panic:
            skip_normal_logic = True
            excess = pressure_against_B - DRIFT_FLIP_RISK_Z
            size_mkt = min(
                DRIFT_FLIP_MKT_CAP,
                int(round(DRIFT_FLIP_MKT_BASE * (1.0 + excess))),
            )
            size_lim = min(
                DRIFT_FLIP_LIM_CAP,
                int(round(DRIFT_FLIP_LIM_BASE * (1.0 + excess))),
            )

            if pos > 0:
                need = pos
                mkt_left = min(size_mkt, need)
                took_mkt = 0
                for bid_px in sorted(bids, reverse=True):
                    if mkt_left <= 0:
                        break
                    vol = abs(bids[bid_px])
                    qty = min(vol, mkt_left, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty
                        mkt_left -= qty
                        took_mkt += qty
                        need -= qty
                posted_lim = 0
                if need > 0 and best_bid + 1 < best_ask:
                    qty_a = min(size_lim, need, ws + POS_LIMIT)
                    if qty_a > 0:
                        orders.append(Order(PRODUCT, best_bid + 1, -qty_a))
                        ws -= qty_a
                        posted_lim = qty_a
                take_event = (
                    f"PATH_D_LONG(pB={pressure_against_B:.2f},mkt={took_mkt},"
                    f"lim={posted_lim})"
                )
            elif pos < 0:
                need = -pos
                mkt_left = min(size_mkt, need)
                took_mkt = 0
                for ask_px in sorted(asks):
                    if mkt_left <= 0:
                        break
                    vol = abs(asks[ask_px])
                    qty = min(vol, mkt_left, POS_LIMIT - wl)
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, qty))
                        wl += qty
                        mkt_left -= qty
                        took_mkt += qty
                        need -= qty
                posted_lim = 0
                if need > 0 and best_ask - 1 > best_bid:
                    qty_b = min(size_lim, need, POS_LIMIT - wl)
                    if qty_b > 0:
                        orders.append(Order(PRODUCT, best_ask - 1, qty_b))
                        wl += qty_b
                        posted_lim = qty_b
                take_event = (
                    f"PATH_D_SHORT(pB={pressure_against_B:.2f},mkt={took_mkt},"
                    f"lim={posted_lim})"
                )

        # ── PATH B — Take available L1 vol on ASK_DROP signal ────────────
        if not skip_normal_logic and fav == +1:
            ask_drop_fires = (
                ask_drop >= thresh_ask_heavy
                or (ask_drop >= thresh_ask_light and imb >= -imb_take_confirm)
            )
            if ask_drop_fires:
                max_take_px = _to_tick(fv_now + ask_drop)
                total_taken = 0
                levels_taken = 0
                for ask_px in sorted(asks):
                    if ask_px > max_take_px or wl >= POS_LIMIT:
                        break
                    vol = abs(asks[ask_px])
                    qty = min(vol, POS_LIMIT - wl)
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, qty))
                        wl += qty
                        total_taken += qty
                        levels_taken += 1
                if levels_taken > 0 and not take_event:
                    tag = "HEAVY" if ask_drop >= thresh_ask_heavy else "LIGHT"
                    z_drop = ask_drop / max(0.5, sigma_ask)
                    take_event = f"PATH_B_{tag}(z={z_drop:.1f},took={total_taken},lvls={levels_taken})"

            elif pos >= PATH_C_POS_GATE and bid_spike >= thresh_bid_heavy:
                for bid_px in sorted(bids, reverse=True):
                    vol = abs(bids[bid_px])
                    qty = min(vol, MAX_SIZE_DERISK, ws + POS_LIMIT, max(0, pos - q_target))
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty
                        if not take_event:
                            take_event = f"PATH_C_DERISK({bid_spike:.1f},pos={pos},L1only)"
                    break

        elif not skip_normal_logic and fav == -1:
            bid_spike_fires_neg = (
                bid_spike >= thresh_bid_heavy
                or (bid_spike >= thresh_bid_light and imb <= imb_take_confirm)
            )
            if bid_spike_fires_neg:
                min_take_px = _to_tick(fv_now - bid_spike)
                total_taken = 0
                levels_taken = 0
                for bid_px in sorted(bids, reverse=True):
                    if bid_px < min_take_px or ws + POS_LIMIT <= 0:
                        break
                    vol = abs(bids[bid_px])
                    qty = min(vol, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, -qty))
                        ws -= qty
                        total_taken += qty
                        levels_taken += 1
                if levels_taken > 0 and not take_event:
                    z_spike = bid_spike / max(0.5, sigma_bid)
                    take_event = f"PATH_B_BEAR(z={z_spike:.1f},took={total_taken},lvls={levels_taken})"
            elif pos <= -PATH_C_POS_GATE and ask_drop >= thresh_ask_heavy:
                for ask_px in sorted(asks):
                    vol = abs(asks[ask_px])
                    qty = min(vol, MAX_SIZE_DERISK, POS_LIMIT - wl, max(0, q_target - pos))
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, qty))
                        wl += qty
                        if not take_event:
                            take_event = f"PATH_C_DERISK_BEAR({ask_drop:.1f},pos={pos},L1only)"
                    break

        # ── PASSIVE QUOTES — PURE A-S ────────────────────────────────────
        if not skip_normal_logic:
            bid_raw = [_to_tick(r_bid - mult * delta_star) for mult in LEVEL_MULTIPLIERS]
            ask_raw = [_to_tick(r_ask + mult * delta_star) for mult in LEVEL_MULTIPLIERS]

            bid_clamped = [_clamp_bid_no_cross(p, best_ask) for p in bid_raw]
            ask_clamped = [_clamp_ask_no_cross(p, best_bid) for p in ask_raw]

            bid_tight, bid_mid, bid_deep = bid_clamped
            ask_tight, ask_mid, ask_deep = ask_clamped

            bid_levels = _dedup([bid_tight, bid_mid, bid_deep])
            ask_levels = _dedup([ask_tight, ask_mid, ask_deep])

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

            # ── Emit BIDs ────────────────────────────────────────────────
            bid_cap = q_target if fav == +1 and phase == "ACCUM" else POS_LIMIT
            for bid_px in bid_levels:
                if fav == -1 and phase == "HYBRID" and bid_px is not None and bid_px >= int(st.L) - MIN_ASK_PROFIT:
                    continue
                qty_b = min(size_bid, bid_cap - wl)
                if qty_b > 0:
                    orders.append(Order(PRODUCT, bid_px, qty_b))
                    wl += qty_b

            # ── Emit ASKs ───────────────────────────────────────────────
            should_emit_ask = True
            if fav == +1 and pos < q_target:
                should_emit_ask = False
            elif fav == -1 and pos < q_target:
                should_emit_ask = False

            if should_emit_ask:
                for ask_px in ask_levels:
                    if fav == +1 and ask_px is not None and ask_px <= int(st.L) + MIN_ASK_PROFIT:
                        continue
                    qty_a = min(size_ask, ws + POS_LIMIT)
                    if qty_a > 0:
                        orders.append(Order(PRODUCT, ask_px, -qty_a))
                        ws -= qty_a
        else:
            bid_levels = []
            ask_levels = []
            phase = "PANIC"
            cb_label = ""

        # ── Log ──────────────────────────────────────────────────────────
        gate_label = ""
        if drift_panic:
            gate_label = " PANIC"
        elif bid_trap:
            gate_label = " BIDTRAP"
        elif ask_trap:
            gate_label = " ASKTRAP"
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} {phase}{cb_label}{gate_label} "
            f"B={st.B:+.4f} pB={pressure_against_B:+.2f} imb={imb:+.2f} L={st.L:.1f} "
            f"adrop={ask_drop:.1f}/{thresh_ask_light:.1f}/{thresh_ask_heavy:.1f} "
            f"bspike={bid_spike:.1f}/{thresh_bid_light:.1f}/{thresh_bid_heavy:.1f} "
            f"b={bid_levels} a={ask_levels} n={len(orders)} {take_event}"
        )

        return orders, st.to_json()

    # ─────────────────────────────────────────────────────────────────────
    # ASH block — identical to moyen2.py
    # ─────────────────────────────────────────────────────────────────────
    def _run_ash(
        self, state: TradingState, ash_td: dict
    ) -> tuple[list[Order], dict]:
        pos = state.position.get(ASH_PRODUCT, 0)
        depth = state.order_depths.get(ASH_PRODUCT)
        orders: list[Order] = []
        st = ash_td if isinstance(ash_td, dict) else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(ASH_PRODUCT, 1, min(80, ASH_POS_LIMIT - pos)))
            orders.append(Order(ASH_PRODUCT, 10**12, -min(80, ASH_POS_LIMIT + pos)))
            return orders, st

        # --- FV micro-price multiniveau ---
        bids = sorted(depth.buy_orders.items(), reverse=True)[:ASH_N_LEVELS]
        asks = sorted(depth.sell_orders.items())[:ASH_N_LEVELS]
        num, den, imb_b, imb_a = 0.0, 0.0, 0.0, 0.0
        for i, ((bp, bq), (ap, aq)) in enumerate(zip(bids, asks)):
            w = math.exp(-ASH_W_DECAY * i)
            bq, aq = abs(bq), abs(aq)
            num += w * (aq * bp + bq * ap)
            den += w * (bq + aq)
            imb_b += w * bq
            imb_a += w * aq
        fv = num / den if den else (bids[0][0] + asks[0][0]) / 2
        imb = (imb_b - imb_a) / (imb_b + imb_a)

        # --- Volatilité rolling ---
        history = st.get("fv_hist", [])
        history.append(fv)
        if len(history) >= ASH_AVG_DURATION:
            num = 0
            den = 0
            for i in range(ASH_AVG_DURATION):
                num += math.exp(-ASH_AVG_DECAY * i) * history[-i]
                den += math.exp(-ASH_AVG_DECAY * i)
            fv = num / den
        if len(history) > ASH_BETA_VOL:
            history = history[-ASH_BETA_VOL:]
        if len(history) > 2:
            mean = sum(history) / len(history)
            sigma = math.sqrt(sum((x - mean) ** 2 for x in history) / len(history))
        else:
            sigma = 1

        # --- A-S : prix de réservation + spread ---
        r = fv - pos * ASH_GAMMA * sigma ** 2 * ASH_T + ASH_ALPHA * imb
        spread = ASH_GAMMA * sigma ** 2 * ASH_T + (2 / ASH_GAMMA) * math.log(1 + ASH_GAMMA / ASH_KAPPA)
        spread = max(spread, 2)

        bid_price = round(r - spread / 2)
        ask_price = round(r + spread / 2)

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)

        # --- Taker agressif sur cassure FV ---
        taker_triggered = False
        if sigma > 0:
            deviation = b_bid - fv if b_bid > fv else fv - b_ask if b_ask < fv else 0
            if deviation > ASH_K_SIGMA * sigma:
                if b_bid > fv:
                    qty = min(ASH_SIZE_TAKER, ASH_POS_LIMIT + pos)
                    if qty > 0:
                        orders.append(Order(ASH_PRODUCT, b_bid, -qty))
                        taker_triggered = True
                elif b_ask < fv:
                    qty = min(ASH_SIZE_TAKER, ASH_POS_LIMIT - pos)
                    if qty > 0:
                        orders.append(Order(ASH_PRODUCT, b_ask, qty))
                        taker_triggered = True

        # --- Quotes maker A-S (si pas de taker) ---
        if not taker_triggered:
            buy_qty = min(ASH_SIZE, ASH_POS_LIMIT - pos)
            sell_qty = min(ASH_SIZE, ASH_POS_LIMIT + pos)
            if buy_qty > 0:
                orders.append(Order(ASH_PRODUCT, bid_price, buy_qty))
            if sell_qty > 0:
                orders.append(Order(ASH_PRODUCT, ask_price, -sell_qty))

        return orders, {"fv_hist": history}