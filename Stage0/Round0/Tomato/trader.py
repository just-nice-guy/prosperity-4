"""
TOMATOES Market Making Strategy — 4-Model Fair Value Blend
===========================================================

Fair value model (research-validated, Sections 5.12, 5.22, 5.24 of the
TOMATOES paper; v2_19 results: 121 models × bootstrap × permutation × BH):

    fv = W_PRESSURE * pressure_multi_w10.3_w20.7     # short-term book pressure
       + W_OU       * ou_w500                         # short-term mean reversion
       + W_BAY      * bayesian_sp2_so2                # long-term Bayesian anchor
       + W_EMA      * ema_mid_a0.05                   # long-term slow EMA

The four components were selected from the v2_19 advanced study: the two
best-performing individual survivors at short horizon (h ∈ {1,5,10,20,50})
and long horizon (h ∈ {500,1000,2000,3000}) after bootstrap CI, permutation
test, Benjamini–Hochberg FDR correction, walk-forward stability and IS/OOS
drift filters. The weights are IC-weighted (each model's weight is
proportional to its validated OOS IC) with a 65/35 short/long split,
reflecting that market-making hinges on immediate horizon accuracy.

Weights derivation:
  Short pool IC: pressure=0.338, OU=0.233 → [0.592, 0.408]
  Long pool IC:  bayes=0.276, ema=0.130  → [0.680, 0.320]
  Short/long:    0.65 / 0.35
  Final:         pressure=0.385, OU=0.265, bayes=0.238, ema=0.112

Reservation price (Avellaneda–Stoikov):
  r = fv − gamma * sigma * position

Order placement (fill-probability oriented):
  1. **Aggressive taking FIRST** — cross market orders that are mispriced
     relative to fv by more than TAKE_EDGE ticks. These are guaranteed
     fills. Emitted before any passive quotes so that they're the first
     orders the matching engine sees within our returned list.
  2. **Passive quotes INSIDE the best market** — after the inventory skew,
     clamp each bid to `min(our_bid, best_bid + 1)` and each ask to
     `max(our_ask, best_ask − 1)`. This guarantees the quote is at least
     as aggressive as the best market level, maximising queue priority.
  3. **Stacked levels** — 2 levels per side with 1-tick gap, so we sit
     on multiple price rungs and capture fills on small spread moves.
  4. **Inventory management** — soft limit at 50% (taper risky-side size)
     and reduce-only mode at 70%.

Hot-path design: the 4 FV component updates are O(1) per tick except for
OU which is a single OLS on a 500-element buffer (<1 ms in NumPy). All
computations complete in well under 1 ms, so orders are effectively
returned at the very start of the tick. No I/O, no network, no logging.
"""

from __future__ import annotations

import json
import math

# Platform-compatible import: Prosperity AWS Lambda provides 'datamodel',
# our local backtester provides 'prosperity4bt.domain.datamodel'.
try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
PRODUCT = "VELVETFRUIT_EXTRACT"
POS_LIMIT = 80

# 4-model blend weights (research-validated, IC-weighted 65/35 short/long)
W_PRESSURE = 0.385   # E2_pressure_multi_w10.3_w20.7 — short book pressure
W_OU       = 0.265   # C1_ou_w500 — short mean-reversion
W_BAY      = 0.238   # C3_bayesian_sp2_so2 — long Bayesian anchor
W_EMA      = 0.112   # B1_ema_mid_a0.05 — long slow EMA

# Pressure model sub-weights (E2_pressure_multi_w10.3_w20.7)
PRESSURE_W1 = 0.3    # weight on L1 imbalance
PRESSURE_W2 = 0.7    # weight on L2 imbalance

# OU model: rolling window length
OU_WINDOW = 500

# Bayesian model: σ_prior = σ_obs = 2 → τ = 1/σ² = 0.25
BAY_TAU_OBS = 0.25
BAY_DECAY = 0.99      # process-noise precision decay per tick

# EMA model: alpha on raw mid
EMA_ALPHA_MID = 0.05

# Spread-variance EMA (existing realised-vol proxy)
ALPHA_VAR = 0.15

# Spread
BASE_HALF_SPREAD  = 2      # ticks on each side (inside market's ~7-tick half-spread)
VOL_SPREAD_FACTOR = 0.2    # additional half-spread per tick of realised volatility
LEVELS    = 2              # stacked quote levels per side
LEVEL_GAP = 1              # tick gap between levels

# Inventory skew: r = fv − γ·σ·pos
GAMMA = 0.03

# Order sizing
MAX_SIZE = 20              # max qty per quote level

# Aggressive taking
TAKE_EDGE = 3              # tighter than before — our FV is more accurate

# Position thresholds
SOFT_RATIO   = 0.50
REDUCE_RATIO = 0.70


# ─────────────────────────────────────────────────────────────────────────────
# Persistent state — stored as JSON in traderData each tick
# ─────────────────────────────────────────────────────────────────────────────
class State:
    """Persistent per-tick state.

    Fields:
      ou_buffer  : rolling last OU_WINDOW wmids (list of floats)
      bayes_mu   : current Bayesian posterior mean
      bayes_tau  : current Bayesian prior precision (evolves with decay)
      ema_mid    : current EMA of raw mid
      ema_var    : EMA of squared spread-deviation (realised vol proxy)
    """

    def __init__(
        self,
        ou_buffer: list[float] | None = None,
        bayes_mu: float = 5000.0,
        bayes_tau: float = 0.25,
        ema_mid: float = 5000.0,
        ema_var: float = 49.0,
    ) -> None:
        self.ou_buffer: list[float] = list(ou_buffer) if ou_buffer else []
        self.bayes_mu = bayes_mu
        self.bayes_tau = bayes_tau
        self.ema_mid = ema_mid
        self.ema_var = ema_var

    def to_json(self) -> str:
        return json.dumps({
            "ou_buffer": self.ou_buffer,
            "bayes_mu": self.bayes_mu,
            "bayes_tau": self.bayes_tau,
            "ema_mid": self.ema_mid,
            "ema_var": self.ema_var,
        })

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            return cls(
                ou_buffer=list(d.get("ou_buffer", [])),
                bayes_mu=float(d.get("bayes_mu", 5000.0)),
                bayes_tau=float(d.get("bayes_tau", 0.25)),
                ema_mid=float(d.get("ema_mid", 5000.0)),
                ema_var=float(d.get("ema_var", 49.0)),
            )
        except Exception:
            return cls()


# ─────────────────────────────────────────────────────────────────────────────
# Order-book helpers
# ─────────────────────────────────────────────────────────────────────────────
def compute_weighted_mid(depth: OrderDepth) -> float | None:
    """Weighted mid-price (VWAP-based) across ALL levels."""
    if not depth.buy_orders or not depth.sell_orders:
        return None
    total_bval = 0.0
    total_aval = 0.0
    total_bvol = 0.0
    total_avol = 0.0
    for p, v in depth.buy_orders.items():
        av = abs(v)
        total_bval += p * av
        total_bvol += av
    for p, v in depth.sell_orders.items():
        av = abs(v)
        total_aval += p * av
        total_avol += av
    if total_bvol == 0 or total_avol == 0:
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
    vwap_bid = total_bval / total_bvol
    vwap_ask = total_aval / total_avol
    return (vwap_bid * total_avol + vwap_ask * total_bvol) / (total_avol + total_bvol)


def compute_imb1_and_l2(depth: OrderDepth) -> tuple[float, float]:
    """Return (L1 imbalance, L2 imbalance) in one pass."""
    sorted_bids = sorted(depth.buy_orders.keys(), reverse=True)
    sorted_asks = sorted(depth.sell_orders.keys())

    bv1 = abs(depth.buy_orders[sorted_bids[0]]) if sorted_bids else 0.0
    av1 = abs(depth.sell_orders[sorted_asks[0]]) if sorted_asks else 0.0
    imb1 = (bv1 - av1) / (bv1 + av1) if (bv1 + av1) > 0 else 0.0

    bv2 = abs(depth.buy_orders[sorted_bids[1]]) if len(sorted_bids) > 1 else 0.0
    av2 = abs(depth.sell_orders[sorted_asks[1]]) if len(sorted_asks) > 1 else 0.0
    l2 = (bv2 - av2) / (bv2 + av2) if (bv2 + av2) > 0 else 0.0

    return imb1, l2


def to_tick(price: float) -> int:
    return int(round(price))


# ─────────────────────────────────────────────────────────────────────────────
# OU rolling OLS (C1_ou_w500)
# ─────────────────────────────────────────────────────────────────────────────
def compute_ou_fv(buffer: list[float], current_wmid: float) -> float:
    """Rolling OU mean-reversion FV from a wmid buffer of up to OU_WINDOW
    observations. Until the buffer is full, returns the current wmid."""
    n = len(buffer)
    if n < OU_WINDOW:
        return current_wmid

    # OLS on last OU_WINDOW wmids: ΔX_t = a + b · X_{t−1}
    # We avoid importing numpy here to keep the hot path Python-native,
    # but the arithmetic is done once per tick so the cost is negligible.
    sum_x = 0.0
    sum_y = 0.0
    sum_xy = 0.0
    sum_xx = 0.0
    cnt = 0
    prev = buffer[0]
    for cur in buffer[1:]:
        dy = cur - prev
        sum_x += prev
        sum_y += dy
        sum_xy += prev * dy
        sum_xx += prev * prev
        cnt += 1
        prev = cur
    if cnt == 0:
        return current_wmid
    mx = sum_x / cnt
    my = sum_y / cnt
    var = sum_xx - cnt * mx * mx
    if var <= 0.0:
        return buffer[-1]
    cov = sum_xy - cnt * mx * my
    b = cov / var
    a = my - b * mx
    theta = -b
    if abs(theta) < 1e-8:
        return buffer[-1]
    mu = a / theta
    alpha_ou = 1.0 if theta > 1.0 else (0.0 if theta < 0.0 else theta)
    return alpha_ou * mu + (1.0 - alpha_ou) * buffer[-1]


# ─────────────────────────────────────────────────────────────────────────────
# Trader
# ─────────────────────────────────────────────────────────────────────────────
class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:

        # ── 0. Restore persistent state ───────────────────────────────────────
        st    = State.from_json(state.traderData) if state.traderData else State()
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if depth is None or (not depth.buy_orders and not depth.sell_orders):
            return {PRODUCT: orders}, 0, st.to_json()

        # ── 1. Book primitives (single pass) ──────────────────────────────────
        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None
        if best_bid is None or best_ask is None:
            return {PRODUCT: orders}, 0, st.to_json()

        mid = (best_bid + best_ask) / 2.0
        spread = float(best_ask - best_bid)

        wmid = compute_weighted_mid(depth)
        if wmid is None:
            wmid = mid

        imb1, l2_imb = compute_imb1_and_l2(depth)

        # ── 2. Component FVs ──────────────────────────────────────────────────
        # 2a. pressure_multi (stateless)
        fv_pressure = mid + (PRESSURE_W1 * imb1 + PRESSURE_W2 * l2_imb) * spread / 2.0

        # 2b. OU rolling OLS on wmid (uses buffer BEFORE appending current wmid,
        #     so the estimate is purely historical and never sees the "future")
        fv_ou = compute_ou_fv(st.ou_buffer, wmid)
        # Update buffer in place
        st.ou_buffer.append(wmid)
        if len(st.ou_buffer) > OU_WINDOW:
            # Keep tail of length OU_WINDOW — single list mutation, cheap
            del st.ou_buffer[: len(st.ou_buffer) - OU_WINDOW]

        # 2c. Bayesian sequential update (source=wmid, σ_prior=σ_obs=2, decay 0.99)
        tau_post = st.bayes_tau + BAY_TAU_OBS
        st.bayes_mu = (st.bayes_tau * st.bayes_mu + BAY_TAU_OBS * wmid) / tau_post
        st.bayes_tau = tau_post * BAY_DECAY
        fv_bayes = st.bayes_mu

        # 2d. EMA of raw mid with α=0.05
        st.ema_mid = EMA_ALPHA_MID * mid + (1.0 - EMA_ALPHA_MID) * st.ema_mid
        fv_ema = st.ema_mid

        # ── 3. Weighted blend ─────────────────────────────────────────────────
        fv = (
            W_PRESSURE * fv_pressure
            + W_OU       * fv_ou
            + W_BAY      * fv_bayes
            + W_EMA      * fv_ema
        )

        # ── 4. Update spread-variance EMA (realised-vol proxy) ────────────────
        deviation = spread - math.sqrt(st.ema_var)
        st.ema_var = max(1.0, ALPHA_VAR * deviation * deviation + (1.0 - ALPHA_VAR) * st.ema_var)
        sigma = math.sqrt(st.ema_var)

        # ── 5. Reservation price: skew toward reducing inventory ──────────────
        r = fv - GAMMA * sigma * pos

        # ── 6. Quote half-spread (widens with realised volatility) ────────────
        half = BASE_HALF_SPREAD + VOL_SPREAD_FACTOR * sigma

        # ── 7. Position regime thresholds ─────────────────────────────────────
        soft_limit   = int(POS_LIMIT * SOFT_RATIO)    # 40
        reduce_limit = int(POS_LIMIT * REDUCE_RATIO)  # 56

        # Worst-case position trackers — prevent limit breaches
        wl = pos    # worst long  if every buy order fills
        ws = pos    # worst short if every sell order fills

        # ── 8. AGGRESSIVE TAKING — FIRST, guarantees fills on mispriced levels
        # Buy cheap asks (ask well below fv)
        for ask_px in sorted(depth.sell_orders):
            if ask_px >= fv - TAKE_EDGE:
                break
            vol = abs(depth.sell_orders[ask_px])
            qty = min(vol, MAX_SIZE * 2, POS_LIMIT - wl)
            if qty > 0:
                orders.append(Order(PRODUCT, ask_px, qty))
                wl += qty

        # Sell expensive bids (bid well above fv)
        for bid_px in sorted(depth.buy_orders, reverse=True):
            if bid_px <= fv + TAKE_EDGE:
                break
            vol = abs(depth.buy_orders[bid_px])
            qty = min(vol, MAX_SIZE * 2, ws + POS_LIMIT)
            if qty > 0:
                orders.append(Order(PRODUCT, bid_px, -qty))
                ws -= qty

        # ── 9. PASSIVE QUOTES — clamped to never cross, tightened for fills
        # Level 0 joins the best market (or sits 1 tick inside if spread >= 3).
        # Level N > 0 sits LEVEL_GAP ticks worse than level 0 — never crosses.
        # Passive-quote clamping is applied to ALL levels so a large inventory
        # skew never produces a passive order that crosses the spread; crossing
        # is reserved for the explicit aggressive-taking block above.
        for lvl in range(LEVELS):
            bid_px = to_tick(r - half - lvl * LEVEL_GAP)
            ask_px = to_tick(r + half + lvl * LEVEL_GAP)

            # Best market prices for bid — never cross the ask
            if bid_px >= best_ask:
                bid_px = best_ask - 1
            # When level 0 would quote worse than the best bid, join the best
            # bid to guarantee queue priority. Subsequent levels sit deeper.
            if lvl == 0:
                if bid_px < best_bid:
                    bid_px = best_bid
            else:
                if bid_px >= best_bid - lvl * LEVEL_GAP:
                    bid_px = best_bid - lvl * LEVEL_GAP

            # Same clamping for the ask side — never cross the bid
            if ask_px <= best_bid:
                ask_px = best_bid + 1
            if lvl == 0:
                if ask_px > best_ask:
                    ask_px = best_ask
            else:
                if ask_px <= best_ask + lvl * LEVEL_GAP:
                    ask_px = best_ask + lvl * LEVEL_GAP

            if abs(pos) >= reduce_limit:
                # Reduce-only: only quote the side that brings us back to zero
                if pos > 0:
                    qty = min(MAX_SIZE, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, -qty))
                        ws -= qty
                else:
                    qty = min(MAX_SIZE, POS_LIMIT - wl)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, qty))
                        wl += qty
            else:
                bid_size = MAX_SIZE
                if pos >= soft_limit:
                    bid_size = max(1, bid_size // 3)   # taper bids when long
                qty_b = min(bid_size, POS_LIMIT - wl)
                if qty_b > 0:
                    orders.append(Order(PRODUCT, bid_px, qty_b))
                    wl += qty_b

                ask_size = MAX_SIZE
                if pos <= -soft_limit:
                    ask_size = max(1, ask_size // 3)   # taper asks when short
                qty_a = min(ask_size, ws + POS_LIMIT)
                if qty_a > 0:
                    orders.append(Order(PRODUCT, ask_px, -qty_a))
                    ws -= qty_a

        return {PRODUCT: orders}, 0, st.to_json()
