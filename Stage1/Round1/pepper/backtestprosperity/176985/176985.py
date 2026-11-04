"""
INTARIAN_PEPPER_ROOT trader v2 — IMC Prosperity 4, Round 1.

Architecture (revised after user feedback)
───────────────────────────────────────────
Three-phase inventory management on the favorable side:

    Phase 1 — ACCUMULATE   (|pos| < q_target ≈ 60)
        bids at 3 depths (tight, mid, deep) with full size.
        NO asks — pure directional accumulation.

    Phase 2 — HYBRID / CYCLE  (q_target ≤ |pos| < POS_LIMIT)
        bids still active (we can still climb toward POS_LIMIT=80).
        ASKS active on the contre-drift side, but:
          - placed at `best_ask − 1` (deepest possible inside),
          - only if the implied profit > MIN_ASK_PROFIT threshold,
          - with SMALL size (MAX_SIZE_OFF).
        This captures cycle spread while still pushing toward max.

    Phase 3 — REDUCE-ONLY  (|pos| = POS_LIMIT)
        bids are blocked by the worst-case tracker.
        asks emit at full size to unwind toward q_target.

Ask profitability rule in phase 2:
    A sell at price P held until day close yields MTM = P − day_close.
    On a drift market we sell early → MTM cost of leaving the trend.
    The cheapest "acceptable" ask is `L + MIN_ASK_PROFIT`; if the
    market's deep quote (best_ask − 1) is above that, we emit. If not,
    we skip the ask even though we're in phase 2.

Signal handling
───────────────
  - Imbalance boost is ONE-SIDED: only in the drift direction, and
    stronger than v1 (IMB_BOOST_STRONG = 5.0). This exploits the
    long-horizon IC of imbalance aggressively when it aligns with drift
    and ignores it when it contradicts drift (noise filter).

  - Aggressive taking is asymmetric by regime:
      fav=+1 → buy-take only,  never sell-take
      fav=-1 → sell-take only, never buy-take
      fav= 0 → no taking

  - Quotes are emitted in NATURAL order (no reversal). Placing orders
    in the order we computed them; the matching engine handles priority.

Dynamic parameters (state-derived)
──────────────────────────────────
  TAKE_EDGE       = max(1, round(σ))                    — scales with vol
  IMB_TAKE        = IMB_TAKE_Z · σ_imb                  — z-score of EWMA
  q_target        = fav · POS_LIMIT · Q_TARGET_RATIO   — ±60 by default
  δ*              = DELTA_STAR_FLOW + 0.5·γ·σ²·(T−t)/T

TUNING NOTES  (see tuning grid at the bottom of the file)
─────────────
  Q_TARGET_RATIO   0.60 ↔ 0.85     lower = more derisk, less drift capture
  GAMMA            0.01 ↔ 0.05     higher = sharper inventory skew
  IMB_BOOST_STRONG 3.0  ↔ 8.0      higher = more aggressive on imb
  IMB_TAKE_Z       1.0  ↔ 2.5      lower = take more often, higher = selective
  MIN_ASK_PROFIT   2    ↔ 5        minimum ticks above L for phase-2 asks
  MAX_SIZE_OFF     5    ↔ 20       phase-2 ask size

  Tune by running the 1000-tick truncated day 0 backtest (best proxy for the
  official engine) with a grid over each dim, e.g.:

    for q in 0.60, 0.65, 0.70, 0.75, 0.80:
        set Q_TARGET_RATIO = q; run backtest; record PnL
    pick q that maximises 1000-tick PnL while keeping final_pos reasonable.

  Calibration anchors (A_HAT, K_HAT, B_PRIOR, ALPHA, BETA) come from the
  offline calibration on 3 historical days. Leave them fixed unless the
  market regime visibly shifts.
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


# ── Holt linear filter (offline-tuned) ────────────────────────────────────
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
DELTA_STAR_FLOW = (1.0 / GAMMA) * math.log(1.0 + GAMMA / K_HAT)  # ≈ 1.679


# ── Signal aggressiveness ──────────────────────────────────────────────────
# Imbalance boost on the reservation price: ONLY in the drift direction,
# and stronger than v1 (previously 2.5). The EDA regression gave −5.14 on
# eps_mid = α · imb, and roughly half of that value (≈2.5) was used before.
# Going back to the full coefficient: 5.0.
IMB_BOOST_STRONG = 5.0


# ── Inventory policy ──────────────────────────────────────────────────────
Q_TARGET_RATIO = 0.75              # phase-1/phase-2 boundary (pos=60 out of 80)
MIN_ASK_PROFIT = 3                 # min ticks above L to emit a phase-2 ask


# ── Regime thresholds ──────────────────────────────────────────────────────
DRIFT_THRESHOLD = 0.3 * B_PRIOR    # 0.03 — 30% of prior drift
IMB_TAKE_Z = 1.5                   # z-score threshold for strong imbalance
SIGMA_IMB_INIT = 0.19              # empirical std(imb) on 3 historical days
LAM_IMB = 0.995                    # EWMA decay for sigma_imb²


# ── Robustness ─────────────────────────────────────────────────────────────
NARROW_SPREAD = 5


# ── Sizing and levels ─────────────────────────────────────────────────────
MAX_SIZE_FAV = 30                  # per level on the favorable side
MAX_SIZE_OFF = 10                  # phase-2 ask size (contre-drift, smaller)
MAX_SIZE_NEU = 20                  # per level in the deadzone
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
        # ── 0. Restore state ────────────────────────────────────────────
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

        # ── 1. Book guard: one-sided → predict-only ─────────────────────
        if best_bid is None or best_ask is None:
            if st.L is not None:
                st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        spread = best_ask - best_bid
        bv = abs(bids[best_bid])
        av = abs(asks[best_ask])

        # ── 2. Micro-price and raw imbalance ────────────────────────────
        tot = bv + av
        if tot <= 0:
            micro = (best_bid + best_ask) / 2.0
            imb = 0.0
        else:
            micro = (bv * best_ask + av * best_bid) / tot
            imb = (bv - av) / tot

        if st.L is None:
            st.L = micro

        # ── 3. Narrow-spread: predict-only, no orders ───────────────────
        if spread <= NARROW_SPREAD:
            st.L = st.L + st.B
            return {PRODUCT: orders}, 0, st.to_json()

        # ── 4. Winsorize innovation ─────────────────────────────────────
        pred = st.L + st.B
        sigma = max(MIN_SIGMA, math.sqrt(st.sigma2))
        cap = JUMP_CAP_SIGMA * sigma
        innov_raw = micro - pred
        if innov_raw > cap:
            micro = pred + cap
        elif innov_raw < -cap:
            micro = pred - cap

        # ── 5. Holt update ──────────────────────────────────────────────
        L_prev = st.L
        st.L = ALPHA * micro + (1.0 - ALPHA) * (L_prev + st.B)
        st.B = BETA * (st.L - L_prev) + (1.0 - BETA) * st.B

        # ── 6. EWMA updates: vol and imb variance ──────────────────────
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

        # ── 7. Dynamic parameters from state ────────────────────────────
        take_edge = max(1, int(round(sigma)))
        imb_take = IMB_TAKE_Z * sigma_imb  # for logging

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

        # ── 9. A-S reservation price with ONE-SIDED imbalance boost ─────
        # Imbalance is only used as a boost when it ALIGNS with the drift.
        # When it contradicts drift, we ignore it (it would just add noise
        # to the quote center and cost us fills/price).
        skew = (pos - q_target) * GAMMA * sigma2
        r = st.L - skew
        if fav == +1 and imb > 0:
            r += IMB_BOOST_STRONG * imb        # aggressive upward boost
        elif fav == -1 and imb < 0:
            r += IMB_BOOST_STRONG * imb        # aggressive downward boost

        # ── 10. Half-spread ─────────────────────────────────────────────
        ticks_remaining = max(1, T_END_TICKS - state.timestamp // 100)
        time_left = ticks_remaining / T_END_TICKS
        delta_star = DELTA_STAR_FLOW + 0.5 * GAMMA * sigma2 * time_left

        # Worst-case-fully-filled trackers
        wl = pos
        ws = pos
        fv_now = st.L

        # ── 11. AGGRESSIVE TAKING — ASYMMETRIC BY REGIME ────────────────
        if fav == +1:
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

        # ── 12. PASSIVE QUOTE LEVELS ────────────────────────────────────
        # Tight = A-S aggressive (near mid), Deep = best_bid+1/best_ask-1.
        bid_tight_raw = _to_tick(r - delta_star)
        ask_tight_raw = _to_tick(r + delta_star)

        bid_tight = _clamp_inside(bid_tight_raw, best_bid, best_ask)
        bid_deep = _clamp_inside(best_bid + 1, best_bid, best_ask)
        ask_tight = _clamp_inside(ask_tight_raw, best_bid, best_ask)
        ask_deep = _clamp_inside(best_ask - 1, best_bid, best_ask)

        # Mid level = halfway between tight and deep
        bid_mid = None
        if bid_tight is not None and bid_deep is not None:
            bid_mid = _clamp_inside((bid_tight + bid_deep) // 2, best_bid, best_ask)
        ask_mid = None
        if ask_tight is not None and ask_deep is not None:
            ask_mid = _clamp_inside((ask_tight + ask_deep) // 2, best_bid, best_ask)

        # Natural emission order: tight → mid → deep (no reversal)
        bid_levels = _dedup([bid_tight, bid_mid, bid_deep])
        ask_levels = _dedup([ask_tight, ask_mid, ask_deep])

        # ── 13. PHASE DETECTION — 3-phase inventory management ─────────
        # Phase 1: accumulate (|pos| < q_target)
        # Phase 2: hybrid cycling with profitable asks (q_target ≤ |pos| < POS_LIMIT)
        # Phase 3: reduce-only (|pos| = POS_LIMIT)
        if fav == +1:
            if pos < q_target:
                phase = "ACCUM"
            elif pos < POS_LIMIT:
                phase = "HYBRID"
            else:
                phase = "REDUCE"
        elif fav == -1:
            if pos > q_target:
                phase = "ACCUM"
            elif pos > -POS_LIMIT:
                phase = "HYBRID"
            else:
                phase = "REDUCE"
        else:
            phase = "NEUTRAL"

        # ── 14. Emit BID levels ─────────────────────────────────────────
        if fav == +1:
            # Bids active in ACCUM and HYBRID; REDUCE blocks bids via wl=POS_LIMIT
            size_bid = MAX_SIZE_FAV
        elif fav == -1:
            # In SHORT regime, bids are the "contre-drift" (phase 2 small size)
            if phase == "ACCUM":
                size_bid = 0              # don't emit bids while short-accumulating
            elif phase == "HYBRID":
                size_bid = MAX_SIZE_OFF   # small profitable bid
            else:
                size_bid = MAX_SIZE_FAV   # reduce from -POS_LIMIT
        else:
            size_bid = MAX_SIZE_NEU

        for bid_px in bid_levels:
            # In fav=-1 HYBRID mode, only emit the DEEP bid (profitable level)
            if fav == -1 and phase == "HYBRID" and bid_px != bid_deep:
                continue
            # Profitability gate for phase-2 bids (short regime)
            if fav == -1 and phase == "HYBRID":
                if bid_px is None or bid_px >= st.L - MIN_ASK_PROFIT:
                    continue
            qty_b = min(size_bid, POS_LIMIT - wl)
            if qty_b > 0:
                orders.append(Order(PRODUCT, bid_px, qty_b))
                wl += qty_b

        # ── 15. Emit ASK levels ─────────────────────────────────────────
        if fav == +1:
            if phase == "ACCUM":
                size_ask = 0              # no ask during accumulation
            elif phase == "HYBRID":
                size_ask = MAX_SIZE_OFF   # small profitable ask
            else:
                size_ask = MAX_SIZE_FAV   # reduce from +POS_LIMIT
        elif fav == -1:
            size_ask = MAX_SIZE_FAV       # asks are the main accumulation side
        else:
            size_ask = MAX_SIZE_NEU

        for ask_px in ask_levels:
            # In fav=+1 HYBRID mode, only emit the DEEP ask (profitable level)
            if fav == +1 and phase == "HYBRID" and ask_px != ask_deep:
                continue
            # Profitability gate for phase-2 asks (long regime)
            if fav == +1 and phase == "HYBRID":
                if ask_px is None or ask_px <= st.L + MIN_ASK_PROFIT:
                    continue
            qty_a = min(size_ask, ws + POS_LIMIT)
            if qty_a > 0:
                orders.append(Order(PRODUCT, ask_px, -qty_a))
                ws -= qty_a

        # ── 16. Debug log ───────────────────────────────────────────────
        print(
            f"t={state.timestamp} pos={pos} fav={fav:+d} phase={phase} "
            f"B={st.B:+.4f} imb={imb:+.2f} L={st.L:.1f} r={r:.1f} "
            f"te={take_edge} qT={q_target:+d} "
            f"b={bid_levels} a={ask_levels} n={len(orders)}"
        )

        return {PRODUCT: orders}, 0, st.to_json()


# ─────────────────────────────────────────────────────────────────────────
# TUNING REFERENCE (how to pick parameter values)
# ─────────────────────────────────────────────────────────────────────────
#
# The following constants can be varied to shift the risk/PnL trade-off.
# Backtest in `matching_mode="prosperity"` on the 1000-tick truncation of
# day 0 (most faithful local proxy for the official Prosperity engine)
# and/or the full 30 000-tick 3-day run.
#
#   Parameter             Default   Range       Effect
#   --------------------  --------  ----------  ------------------------------
#   Q_TARGET_RATIO        0.75      0.60-0.85   lower = more derisk, less PnL
#   GAMMA                 0.03      0.01-0.05   higher = sharper A-S skew
#   IMB_BOOST_STRONG      5.0       3.0-8.0     higher = more aggressive on imb
#   IMB_TAKE_Z            1.5       1.0-2.5     lower = more takes, higher = selective
#   MIN_ASK_PROFIT        3         2-5         minimum edge for phase-2 asks
#   MAX_SIZE_OFF          10        5-20        phase-2 contre-drift size
#   MAX_SIZE_FAV          30        20-40       favorable side per-level size
#   ALPHA, BETA           .15, .01  —           leave unless observation noise shifts
#   DRIFT_THRESHOLD       0.03      0.02-0.05   deadzone for regime switch
#
# RECOMMENDED TUNING PROCEDURE:
#   1. Fix everything to defaults.
#   2. Vary ONE parameter at a time over its range.
#   3. For each value, backtest 1000-tick day-0 and record PnL + final_pos.
#   4. Pick the value that maximises PnL while keeping final_pos within
#      [q_target, POS_LIMIT] on fav=+1 regime days.
#   5. After tuning individually, do a coarse grid search on the top-2
#      most sensitive params (usually Q_TARGET_RATIO × IMB_BOOST_STRONG).
#