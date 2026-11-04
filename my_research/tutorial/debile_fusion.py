from __future__ import annotations

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCTS  = ["TOMATOES","EMERALDS"]
POS_LIMIT = 80
SIZE      = 80


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        f_orders=[]
        for product in PRODUCTS:
            pos   = state.position.get(product, 0)
            depth = state.order_depths.get(product)
            orders: list[Order] = []

            if not depth or not depth.buy_orders or not depth.sell_orders:
                f_orders.append(orders)
            else:
                b_bid = max(depth.buy_orders)
                b_ask = min(depth.sell_orders)
                #fv  = round(mid)

                orders.append(Order(product, b_bid + 1,  min(SIZE, POS_LIMIT - pos)))   # bid
                orders.append(Order(product, b_ask - 1, -min(SIZE, POS_LIMIT + pos)))   # ask
                f_orders.append(orders)
        return {PRODUCTS[0]: f_orders[0], PRODUCTS[1]: f_orders[1]}, 0, ""
