from __future__ import annotations
import json

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT   = "HYDROGEL_PACK"
POS_LIMIT = 200
SIZE      = 50


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []
        trades = state.market_trades.get(PRODUCT)
        #st = json.loads(state.traderData) if state.traderData else {}

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)

        if trades is not None:
            for i in trades:
                if i.seller == "Mark 14":
                    orders.append(Order(PRODUCT, b_ask,  i.quantity))
                if i.buyer == "Mark 14":
                    orders.append(Order(PRODUCT, b_bid,  -i.quantity))
        """
        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,  min(SIZE, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**9,  -min(SIZE, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, ""

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)
        #fv  = round(mid)

        orders.append(Order(PRODUCT, b_bid + 1,  min(SIZE, POS_LIMIT - pos)))   # bid
        orders.append(Order(PRODUCT, b_ask - 1, -min(SIZE, POS_LIMIT + pos)))   # ask
        """
        return {PRODUCT: orders}, 0, "" #json.dumps({"counter": counter})
