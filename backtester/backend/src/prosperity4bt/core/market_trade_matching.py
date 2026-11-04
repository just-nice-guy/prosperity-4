from __future__ import annotations

import random
from dataclasses import dataclass

from prosperity4bt.domain.datamodel import Order, Trade


@dataclass
class MarketTradeSlot:
    """Wraps a historical market trade with independent buy/sell quantity tracking.

    When a BUY order fills against this slot the *sell_quantity* is consumed;
    when a SELL order fills the *buy_quantity* is consumed.  After all matching
    for a tick is done, ``remaining_trades()`` returns the trades with quantity
    reduced to ``min(buy_quantity, sell_quantity)``.
    """

    trade: Trade
    buy_quantity: int
    sell_quantity: int


@dataclass
class MarketTradeState:
    symbol: str
    slots: list[MarketTradeSlot]


@dataclass(frozen=True)
class MarketTradeMatchResult:
    trades: list[Trade]
    remaining_quantity: int


def build_market_trade_state(trades_by_symbol: dict[str, list[Trade]]) -> dict[str, MarketTradeState]:
    state: dict[str, MarketTradeState] = {}
    for symbol, trades in trades_by_symbol.items():
        state[symbol] = MarketTradeState(
            symbol=symbol,
            slots=[
                MarketTradeSlot(
                    trade=trade,
                    buy_quantity=int(trade.quantity),
                    sell_quantity=int(trade.quantity),
                )
                for trade in trades
            ],
        )
    return state


def remaining_trades(market_trade_state: dict[str, MarketTradeState]) -> dict[str, list[Trade]]:
    """Return market trades with quantities reduced by what was consumed.

    ``trade.quantity = min(buy_quantity, sell_quantity)`` after our fills.
    Trades whose remaining quantity is zero are dropped entirely.
    """
    result: dict[str, list[Trade]] = {}
    for symbol, mts in market_trade_state.items():
        remaining: list[Trade] = []
        for slot in mts.slots:
            qty = min(slot.buy_quantity, slot.sell_quantity)
            if qty > 0:
                remaining.append(
                    Trade(
                        symbol=slot.trade.symbol,
                        price=slot.trade.price,
                        quantity=qty,
                        buyer=slot.trade.buyer,
                        seller=slot.trade.seller,
                        timestamp=slot.trade.timestamp,
                    )
                )
        if remaining:
            result[symbol] = remaining
    return result


def _is_price_eligible(
    order: Order,
    trade_price: int,
    best_market_bid: int | None,
    best_market_ask: int | None,
) -> bool:
    """Prosperity exchange fill eligibility.

    Fill conditions:
      1. Our limit price is STRICTLY BETTER than the best market-maker price
         (``our_bid > bid_price_1`` or ``our_ask < ask_price_1``), so we are
         the unique best quote on that side of the book.
      2. A market trade at this timestamp crosses our price:
           ``trade_price <= our_bid``  (for buy orders)
           ``trade_price >= our_ask``  (for sell orders)
      3. The fill price is OUR LIMIT PRICE (we are the maker).

    When our order price equals the best market price we are tied with a
    market-maker bot; real time-priority is unknown so we conservatively
    assume we do NOT fill in that case.
    """
    if order.quantity > 0:  # passive BUY
        if best_market_bid is None:
            return trade_price < order.price
        return order.price > best_market_bid and trade_price <= order.price
    else:  # passive SELL
        if best_market_ask is None:
            return trade_price > order.price
        return order.price < best_market_ask and trade_price >= order.price


def match_against_market_trades(
    order: Order,
    market_state: MarketTradeState | None,
    timestamp: int,
    best_market_bid: int | None = None,
    best_market_ask: int | None = None,
) -> MarketTradeMatchResult:
    if market_state is None or order.quantity == 0:
        return MarketTradeMatchResult(trades=[], remaining_quantity=order.quantity)

    remaining = int(order.quantity)
    fills: list[Trade] = []
    is_buy = remaining > 0

    for slot in market_state.slots:
        available = slot.sell_quantity if is_buy else slot.buy_quantity
        if available <= 0 or remaining == 0:
            continue

        if not _is_price_eligible(order, slot.trade.price, best_market_bid, best_market_ask):
            continue

        traded_quantity = min(abs(remaining), available)

        if is_buy:
            slot.sell_quantity -= traded_quantity
        else:
            slot.buy_quantity -= traded_quantity

        # Fill at our limit price (maker model)
        fill_price = order.price

        if is_buy:
            fills.append(
                Trade(
                    symbol=order.symbol,
                    price=fill_price,
                    quantity=traded_quantity,
                    buyer="SUBMISSION",
                    seller=slot.trade.seller or "MARKET",
                    timestamp=timestamp,
                )
            )
            remaining -= traded_quantity
        else:
            fills.append(
                Trade(
                    symbol=order.symbol,
                    price=fill_price,
                    quantity=traded_quantity,
                    buyer=slot.trade.buyer or "MARKET",
                    seller="SUBMISSION",
                    timestamp=timestamp,
                )
            )
            remaining += traded_quantity

    return MarketTradeMatchResult(trades=fills, remaining_quantity=remaining)


def match_invisible_taker(
    order: Order,
    timestamp: int,
    best_market_bid: int | None,
    best_market_ask: int | None,
    has_market_activity: bool,
    rng: random.Random,
    base_fill_prob: float = 0.005,
    activity_boost: float = 0.003,
    sigma: float = 0.0,
    fill_skip_prob: float = 0.0,
    adverse_selection: float = 0.0,
    mid_price_delta: float = 0.0,
    min_fill_fraction: float = 0.5,
    max_fill_fraction: float = 1.0,
    edge_fill_boost: float = 0.0,
) -> MarketTradeMatchResult:
    """Simulate invisible taker bots probabilistically.

    On the real Prosperity exchange, fills come from invisible taker bots
    that are NOT recorded in the market trades CSV.  This function models
    that behaviour: when our order is the best quote, there is a random
    chance an invisible taker fills us.

    The fill probability centre = ``base_fill_prob`` + ``activity_boost``
    when bot-to-bot trades exist at this timestamp.

    When ``sigma > 0``, the effective probability is drawn from a normal
    distribution ``N(centre, sigma)`` clamped to [0, 1] each tick, making
    fills more stochastic.  ``sigma = 0`` (default) gives the flat
    deterministic probability.

    Additional professional parameters:

    ``fill_skip_prob``: after a fill is decided, randomly discard it with
    this probability.  Simulates queue-position uncertainty — you thought
    you'd be filled but someone else was ahead.

    ``adverse_selection``: when the mid-price moved against the maker
    (``mid_price_delta`` is negative for buys, positive for sells), the
    fill probability is multiplied by ``(1 + adverse_selection)``.
    Models toxic flow — you get filled more when the market moves against
    you, which is the dominant P&L drain for real market makers.

    ``min_fill_fraction`` / ``max_fill_fraction``: control the partial-fill
    range (default 50–100 %).  Tighter ranges simulate thinner liquidity.

    ``edge_fill_boost``: when > 0, the fill probability increases
    proportionally to how many ticks our order price improves over the
    best market quote.  On the real Prosperity exchange, tighter quotes
    (better price than other market-makers) attract more invisible taker
    fills.  The boost is multiplicative:
      ``centre *= (1 + edge_fill_boost * edge)``
    where ``edge`` is the absolute price difference in integer ticks
    between our order and the best market quote on the same side.
    Example: ``edge_fill_boost=0.5`` with an edge of 3 ticks gives
    ``centre *= 2.5`` (150% boost).  Set to 0 (default) to disable.

    Fill price is always our order price (maker model), matching real
    exchange behaviour.
    """
    if order.quantity == 0:
        return MarketTradeMatchResult(trades=[], remaining_quantity=0)

    is_buy = order.quantity > 0

    # Must be strictly the best quote (same eligibility as prosperity mode)
    if is_buy:
        if best_market_bid is not None and order.price <= best_market_bid:
            return MarketTradeMatchResult(trades=[], remaining_quantity=order.quantity)
    else:
        if best_market_ask is not None and order.price >= best_market_ask:
            return MarketTradeMatchResult(trades=[], remaining_quantity=order.quantity)

    # Probabilistic fill decision — optionally randomized with normal dist
    centre = base_fill_prob + (activity_boost if has_market_activity else 0.0)

    # Edge fill boost: tighter quotes get more fills (observed on real exchange)
    if edge_fill_boost > 0:
        if is_buy and best_market_bid is not None:
            edge = order.price - best_market_bid  # always >= 1 (we passed eligibility)
            centre *= (1.0 + edge_fill_boost * edge)
        elif not is_buy and best_market_ask is not None:
            edge = best_market_ask - order.price  # always >= 1
            centre *= (1.0 + edge_fill_boost * edge)

    # Adverse selection: boost probability when mid moved against maker
    if adverse_selection > 0 and mid_price_delta != 0.0:
        adverse_move = (is_buy and mid_price_delta < 0) or (not is_buy and mid_price_delta > 0)
        if adverse_move:
            centre *= (1.0 + adverse_selection)

    if sigma > 0:
        prob = max(0.0, min(1.0, rng.gauss(centre, sigma)))
    else:
        prob = centre
    if rng.random() >= prob:
        return MarketTradeMatchResult(trades=[], remaining_quantity=order.quantity)

    # Fill skip: randomly discard a fill that would have happened
    if fill_skip_prob > 0 and rng.random() < fill_skip_prob:
        return MarketTradeMatchResult(trades=[], remaining_quantity=order.quantity)

    # Partial fill with configurable fraction range
    lo = max(0.01, min(min_fill_fraction, max_fill_fraction))
    hi = max(lo, max_fill_fraction)
    fill_qty = max(1, int(abs(order.quantity) * rng.uniform(lo, hi)))

    if is_buy:
        fill = Trade(
            symbol=order.symbol,
            price=order.price,
            quantity=fill_qty,
            buyer="SUBMISSION",
            seller="INVISIBLE_TAKER",
            timestamp=timestamp,
        )
        remaining = order.quantity - fill_qty
    else:
        fill = Trade(
            symbol=order.symbol,
            price=order.price,
            quantity=fill_qty,
            buyer="INVISIBLE_TAKER",
            seller="SUBMISSION",
            timestamp=timestamp,
        )
        remaining = order.quantity + fill_qty

    return MarketTradeMatchResult(trades=[fill], remaining_quantity=remaining)


