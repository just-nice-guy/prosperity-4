from __future__ import annotations

from dataclasses import dataclass

from prosperity4bt.domain.datamodel import Order


DEFAULT_PRODUCT_LIMITS: dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}


@dataclass(frozen=True)
class LimitCheckResult:
    accepted_orders: list[Order]
    rejected_orders: list[Order]
    reason: str | None = None


def effective_limits(limit_overrides: dict[str, int] | None = None) -> dict[str, int]:
    limits = dict(DEFAULT_PRODUCT_LIMITS)
    if limit_overrides:
        limits.update(limit_overrides)
    return limits


def enforce_limits(
    symbol: str,
    current_positions: dict[str, int],
    orders: list[Order],
    limits: dict[str, int],
) -> LimitCheckResult:
    """Clamp orders to position limits.

    Buys are processed best-priced first (highest bid wins remaining buy
    capacity); sells are processed best-priced first (lowest ask wins remaining
    sell capacity). Any order whose quantity is reduced to 0 is rejected.

    Capacity:
      buy_capacity  = limit - current_position
      sell_capacity = limit + current_position
    """
    if not orders:
        return LimitCheckResult(accepted_orders=[], rejected_orders=[])

    limit = limits.get(symbol)
    if limit is None:
        return LimitCheckResult(accepted_orders=orders, rejected_orders=[])

    pos = current_positions.get(symbol, 0)
    buy_capacity = max(0, limit - pos)
    sell_capacity = max(0, limit + pos)

    # Stable sort with priority: buys descending by price (most aggressive
    # first), sells ascending by price (most aggressive first). Use enumerate
    # to preserve original input order on price ties.
    indexed = list(enumerate(orders))
    buys = sorted(
        [(i, o) for i, o in indexed if o.quantity > 0],
        key=lambda x: (-x[1].price, x[0]),
    )
    sells = sorted(
        [(i, o) for i, o in indexed if o.quantity < 0],
        key=lambda x: (x[1].price, x[0]),
    )

    clamped: dict[int, Order] = {}
    rejected: list[Order] = []

    for i, o in buys:
        allowed = min(o.quantity, buy_capacity)
        if allowed <= 0:
            rejected.append(o)
            continue
        buy_capacity -= allowed
        clamped[i] = Order(o.symbol, o.price, allowed) if allowed != o.quantity else o

    for i, o in sells:
        allowed = max(o.quantity, -sell_capacity)  # both negative; max is the smaller magnitude
        if allowed >= 0:
            rejected.append(o)
            continue
        sell_capacity += allowed  # allowed is negative, this subtracts magnitude
        clamped[i] = Order(o.symbol, o.price, allowed) if allowed != o.quantity else o

    accepted = [clamped[i] for i, _ in indexed if i in clamped]
    reason = None
    if rejected:
        reason = (
            f"Clamped {symbol} orders to position limit {limit}: "
            f"{len(accepted)} accepted, {len(rejected)} rejected (capacity exhausted)"
        )
    return LimitCheckResult(accepted_orders=accepted, rejected_orders=rejected, reason=reason)
