from __future__ import annotations

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT   = "ASH_COATED_OSMIUM"
POS_LIMIT = 80
SIZE      = 10


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,  min(SIZE, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**9,  -min(SIZE, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, ""

        mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
        fv  = round(mid)

        orders.append(Order(PRODUCT, fv - 1,  min(SIZE, POS_LIMIT - pos)))   # bid
        orders.append(Order(PRODUCT, fv + 1, -min(SIZE, POS_LIMIT + pos)))   # ask

        return {PRODUCT: orders}, 0, ""