from __future__ import annotations

from dataclasses import dataclass

from prosperity4bt.domain.datamodel import Trade


@dataclass(frozen=True)
class PnlSnapshot:
    cash_by_product: dict[str, float]
    mark_to_market_by_product: dict[str, float]
    total: float


def apply_fill(
    trade: Trade,
    positions: dict[str, int],
    cash_by_product: dict[str, float],
) -> None:
    product = trade.symbol
    quantity = int(trade.quantity)
    price = float(trade.price)
    positions.setdefault(product, 0)
    cash_by_product.setdefault(product, 0.0)

    if trade.buyer == "SUBMISSION":
        positions[product] += quantity
        cash_by_product[product] -= price * quantity
    elif trade.seller == "SUBMISSION":
        positions[product] -= quantity
        cash_by_product[product] += price * quantity


def mark_to_market(
    positions: dict[str, int],
    cash_by_product: dict[str, float],
    mid_prices: dict[str, float],
) -> PnlSnapshot:
    cash_snapshot = dict(cash_by_product)
    mtm_by_product: dict[str, float] = {}
    for product in set(positions) | set(cash_by_product) | set(mid_prices):
        mtm_by_product[product] = cash_snapshot.get(product, 0.0) + (
            positions.get(product, 0) * mid_prices.get(product, 0.0)
        )
    return PnlSnapshot(
        cash_by_product=cash_snapshot,
        mark_to_market_by_product=mtm_by_product,
        total=sum(mtm_by_product.values()),
    )
