from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from prosperity4bt.domain.datamodel import Order, OrderDepth, Trade


@dataclass(frozen=True)
class BookMatchResult:
    trades: list[Trade]
    remaining_quantity: int
    updated_depth: OrderDepth


def _clone_depth(depth: OrderDepth) -> OrderDepth:
    return OrderDepth(
        buy_orders=deepcopy(depth.buy_orders),
        sell_orders=deepcopy(depth.sell_orders),
    )


def match_order_against_book(
    order: Order,
    depth: OrderDepth,
    timestamp: int,
) -> BookMatchResult:
    updated_depth = _clone_depth(depth)
    remaining = int(order.quantity)
    trades: list[Trade] = []

    if remaining > 0:
        for ask_price in sorted(updated_depth.sell_orders):
            available = abs(updated_depth.sell_orders[ask_price])
            if available <= 0 or ask_price > order.price or remaining <= 0:
                continue
            traded_quantity = min(remaining, available)
            trades.append(
                Trade(
                    symbol=order.symbol,
                    price=ask_price,
                    quantity=traded_quantity,
                    buyer="SUBMISSION",
                    seller="BOOK",
                    timestamp=timestamp,
                )
            )
            remaining -= traded_quantity
            new_volume = updated_depth.sell_orders[ask_price] + traded_quantity
            if new_volume == 0:
                del updated_depth.sell_orders[ask_price]
            else:
                updated_depth.sell_orders[ask_price] = new_volume
            if remaining == 0:
                break
    elif remaining < 0:
        for bid_price in sorted(updated_depth.buy_orders, reverse=True):
            available = updated_depth.buy_orders[bid_price]
            if available <= 0 or bid_price < order.price or remaining >= 0:
                continue
            traded_quantity = min(abs(remaining), available)
            trades.append(
                Trade(
                    symbol=order.symbol,
                    price=bid_price,
                    quantity=traded_quantity,
                    buyer="BOOK",
                    seller="SUBMISSION",
                    timestamp=timestamp,
                )
            )
            remaining += traded_quantity
            new_volume = updated_depth.buy_orders[bid_price] - traded_quantity
            if new_volume == 0:
                del updated_depth.buy_orders[bid_price]
            else:
                updated_depth.buy_orders[bid_price] = new_volume
            if remaining == 0:
                break

    return BookMatchResult(
        trades=trades,
        remaining_quantity=remaining,
        updated_depth=updated_depth,
    )
