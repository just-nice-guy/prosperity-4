from __future__ import annotations

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT = "INTARIAN_PEPPER_ROOT"
SIZE = 80


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders: list[Order] = []
        depth = state.order_depths.get(PRODUCT)

        if not depth or not depth.sell_orders:
            return {PRODUCT: orders}, 0, ""

        best_ask = min(depth.sell_orders.keys())
        orders.append(Order(PRODUCT, best_ask, SIZE))

        return {PRODUCT: orders}, 0, ""