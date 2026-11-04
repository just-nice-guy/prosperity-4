"""
TOMATOES Market Making Strategy
================================

Fair value model:
  EMA of weighted mid-price (all book levels) + L2 imbalance adjustment.
  Weighted mid = VWAP-bid * ask_vol + VWAP-ask * bid_vol, using ALL levels.
  L2 imbalance = (bid_L2_vol - ask_L2_vol) / (bid_L2_vol + ask_L2_vol)
  FV = EMA(wmid) + L2_WEIGHT * l2_imb * spread

  Research finding: L2 is more informative than L1 (IC +0.36 vs +0.27).
  Weighted mid beats micro-price at all horizons. Combined model gives
  +10.8% PnL and +16% more fills vs the old L1 micro-price EMA.

Reservation price (Avellaneda-Stoikov):
  r = FV - gamma * sigma * q

Spread:
  half_spread = BASE_HALF_SPREAD + VOL_FACTOR * sigma
  2 stacked levels on each side.

Aggressive taking:
  Cross the market when ask < FV - TAKE_EDGE or bid > FV + TAKE_EDGE.

Position management:
  - soft_limit  (50%) -> taper bid/ask size on the risky side
  - reduce_limit (70%) -> reduce-only mode
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
PRODUCT = "TOMATOES"
POS_LIMIT = 80

# Fair value
ALPHA_WMID  = 0.4       # EMA decay for weighted mid-price
L2_WEIGHT   = 0.10       # L2 imbalance adjustment weight
ALPHA_VAR   = 0.15       # EMA decay for spread-variance estimate

# Spread
BASE_HALF_SPREAD  = 2    # ticks on each side (inside the market's ~7-tick half-spread)
VOL_SPREAD_FACTOR = 0.2  # additional half-spread per tick of realised volatility
LEVELS    = 2            # stacked quote levels per side
LEVEL_GAP = 1            # tick gap between levels

# Inventory skew
GAMMA = 0.003             # risk aversion: r = FV − γ·σ·q

# Order sizing
MAX_SIZE = 10            # max qty per quote level

# Aggressive taking
TAKE_EDGE = 2            # take when market price beats FV by this many ticks

# Position thresholds
SOFT_RATIO   = 0.50      # start tapering risky-side quotes at this fraction of limit
REDUCE_RATIO = 0.70      # reduce-only mode above this fraction of limit


# ─────────────────────────────────────────────────────────────────────────────
# Persistent state — stored as JSON in traderData each tick
# Using a plain class to avoid dataclass sys.modules registration issues.
# ─────────────────────────────────────────────────────────────────────────────
class State:
    def __init__(self, ema_wmid: float = 5000.0, ema_var: float = 49.0) -> None:
        self.ema_wmid = ema_wmid
        self.ema_var  = ema_var

    def to_json(self) -> str:
        return json.dumps({"ema_wmid": self.ema_wmid, "ema_var": self.ema_var})

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            return cls(
                ema_wmid=float(d.get("ema_wmid", 5000.0)),
                ema_var=float(d.get("ema_var", 49.0)),
            )
        except Exception:
            return cls()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def compute_weighted_mid(depth: OrderDepth) -> float | None:
    """Weighted mid-price using ALL book levels (VWAP-based)."""
    if not depth.buy_orders or not depth.sell_orders:
        return None
    total_bval = sum(p * abs(depth.buy_orders[p]) for p in depth.buy_orders)
    total_aval = sum(p * abs(depth.sell_orders[p]) for p in depth.sell_orders)
    total_bvol = sum(abs(depth.buy_orders[p]) for p in depth.buy_orders)
    total_avol = sum(abs(depth.sell_orders[p]) for p in depth.sell_orders)
    if total_bvol == 0 or total_avol == 0:
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
    vwap_bid = total_bval / total_bvol
    vwap_ask = total_aval / total_avol
    return (vwap_bid * total_avol + vwap_ask * total_bvol) / (total_avol + total_bvol)


def compute_l2_imbalance(depth: OrderDepth) -> float:
    """Imbalance at the second level of the order book."""
    sorted_bids = sorted(depth.buy_orders.keys(), reverse=True)
    sorted_asks = sorted(depth.sell_orders.keys())
    bv2 = abs(depth.buy_orders[sorted_bids[1]]) if len(sorted_bids) > 1 else 0
    av2 = abs(depth.sell_orders[sorted_asks[1]]) if len(sorted_asks) > 1 else 0
    if bv2 + av2 == 0:
        return 0.0
    return (bv2 - av2) / (bv2 + av2)


def to_tick(price: float) -> int:
    return int(round(price))


# ─────────────────────────────────────────────────────────────────────────────
# Trader
# ─────────────────────────────────────────────────────────────────────────────
class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:

        # ── Restore persistent state ──────────────────────────────────────────
        st    = State.from_json(state.traderData) if state.traderData else State()
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if depth is None or (not depth.buy_orders and not depth.sell_orders):
            return {PRODUCT: orders}, 0, st.to_json()

        # ── Update fair value EMA ─────────────────────────────────────────────
        wmid = compute_weighted_mid(depth)
        if wmid is not None:
            st.ema_wmid = ALPHA_WMID * wmid + (1.0 - ALPHA_WMID) * st.ema_wmid

        # L2 imbalance adjustment
        spread = float(min(depth.sell_orders) - max(depth.buy_orders)) if depth.buy_orders and depth.sell_orders else 0.0
        l2_imb = compute_l2_imbalance(depth)
        fv = st.ema_wmid + L2_WEIGHT * l2_imb * spread

        # ── Update spread-variance EMA ────────────────────────────────────────
        if depth.buy_orders and depth.sell_orders:
            raw_spread = float(min(depth.sell_orders) - max(depth.buy_orders))
            deviation  = raw_spread - math.sqrt(st.ema_var)
            st.ema_var = max(1.0, ALPHA_VAR * deviation ** 2 + (1.0 - ALPHA_VAR) * st.ema_var)

        sigma = math.sqrt(st.ema_var)   # ≈ typical market half-spread in ticks

        # ── Reservation price: skew toward reducing inventory ─────────────────
        r = fv - GAMMA * sigma * pos

        # ── Quote half-spread (widens when the market is volatile) ────────────
        half = BASE_HALF_SPREAD + VOL_SPREAD_FACTOR * sigma

        # ── Position regime thresholds ────────────────────────────────────────
        soft_limit   = int(POS_LIMIT * SOFT_RATIO)    # 56
        reduce_limit = int(POS_LIMIT * REDUCE_RATIO)  # 72

        # Worst-case position trackers — prevent limit breaches
        wl = pos    # worst long  if every buy order fills
        ws = pos    # worst short if every sell order fills

        # ── Aggressive taking: cross market on mispriced quotes ───────────────
        # Buy cheap asks (ask is well below fair value)
        if depth.sell_orders:
            for ask_px in sorted(depth.sell_orders):
                if ask_px >= fv - TAKE_EDGE:
                    break
                vol = abs(depth.sell_orders[ask_px])
                qty = min(vol, MAX_SIZE * 2, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty

        # Sell expensive bids (bid is well above fair value)
        if depth.buy_orders:
            for bid_px in sorted(depth.buy_orders, reverse=True):
                if bid_px <= fv + TAKE_EDGE:
                    break
                vol = abs(depth.buy_orders[bid_px])
                qty = min(vol, MAX_SIZE * 2, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty

        # ── Passive market-making quotes ──────────────────────────────────────
        for lvl in range(LEVELS):
            bid_px = to_tick(r - half - lvl * LEVEL_GAP)
            ask_px = to_tick(r + half + lvl * LEVEL_GAP)

            if abs(pos) >= reduce_limit:
                # Reduce-only: only quote the side that brings us back toward zero
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
                # Normal two-sided quoting
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
