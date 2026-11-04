"""
TOMATOES Market Making Strategy
================================

Fair value model:
  EMA of micro-price  =  (best_bid × ask_vol + best_ask × bid_vol) / (ask_vol + bid_vol)
  Gives a volume-weighted mid that tracks the true mid better than (bid+ask)/2
  when the book is imbalanced.

Reservation price (Avellaneda-Stoikov):
  r = FV − γ · σ · q
  Shifts quotes toward the side that reduces inventory:
    long  → lower both quotes → incentivise selling
    short → raise both quotes → incentivise buying

Spread:
  half_spread = BASE_HALF_SPREAD + VOL_FACTOR · σ
  3 ticks base (inside the ~7-tick half market spread), widens with volatility.
  2 stacked levels on each side to maximise queue presence.

Aggressive taking:
  Cross the market when ask < FV − TAKE_EDGE or bid > FV + TAKE_EDGE (4 ticks).

Position management:
  - soft_limit  (70 %) → taper bid/ask size on the risky side to one-third
  - reduce_limit (90 %) → reduce-only mode: only send orders that shrink position
  - Worst-case position tracker updated before every order submission
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
ALPHA_MICRO = 0.25       # EMA decay for micro-price
ALPHA_VAR   = 0.15       # EMA decay for spread-variance estimate

# Spread
BASE_HALF_SPREAD  = 0    # ticks on each side (inside the market's ~7-tick half-spread)
VOL_SPREAD_FACTOR = 0.2  # additional half-spread per tick of realised volatility
LEVELS    = 2            # stacked quote levels per side
LEVEL_GAP = 1            # tick gap between levels

# Inventory skew
GAMMA = 0.07             # risk aversion: r = FV − γ·σ·q

# Order sizing
MAX_SIZE = 25            # max qty per quote level

# Aggressive taking
TAKE_EDGE = 4            # take when market price beats FV by this many ticks

# Position thresholds
SOFT_RATIO   = 0.3      # start tapering risky-side quotes at this fraction of limit
REDUCE_RATIO = 0.9      # reduce-only mode above this fraction of limit


# ─────────────────────────────────────────────────────────────────────────────
# Persistent state — stored as JSON in traderData each tick
# Using a plain class to avoid dataclass sys.modules registration issues.
# ─────────────────────────────────────────────────────────────────────────────
class State:
    def __init__(self, ema_micro: float = 5000.0, ema_var: float = 49.0) -> None:
        self.ema_micro = ema_micro
        self.ema_var   = ema_var

    def to_json(self) -> str:
        return json.dumps({"ema_micro": self.ema_micro, "ema_var": self.ema_var})

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            return cls(
                ema_micro=float(d.get("ema_micro", 5000.0)),
                ema_var=float(d.get("ema_var", 49.0)),
            )
        except Exception:
            return cls()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def compute_micro_price(depth: OrderDepth) -> float | None:
    """Volume-weighted mid between best bid and best ask."""
    if not depth.buy_orders or not depth.sell_orders:
        return None
    best_bid = max(depth.buy_orders)
    best_ask = min(depth.sell_orders)
    bid_vol = abs(depth.buy_orders[best_bid])
    ask_vol = abs(depth.sell_orders[best_ask])
    total = bid_vol + ask_vol
    if total == 0:
        return (best_bid + best_ask) / 2.0
    return (best_bid * ask_vol + best_ask * bid_vol) / total


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
        mp = compute_micro_price(depth)
        if mp is not None:
            st.ema_micro = ALPHA_MICRO * mp + (1.0 - ALPHA_MICRO) * st.ema_micro

        fv = st.ema_micro

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
