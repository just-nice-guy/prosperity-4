from __future__ import annotations
import json
try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT   = "ASH_COATED_OSMIUM"
POS_LIMIT = 80
SIZE      = 80
MOVE=0

class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []
        st=json.loads(state.traderData) if state.traderData else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            #orders.append(Order(PRODUCT, 1,  min(SIZE, POS_LIMIT - pos)))
            #orders.append(Order(PRODUCT, 10**9,  -min(SIZE, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, json.dumps(st)

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)
        #fv  = round(mid)
        mid=(b_ask+b_bid)/2
        spread=b_ask-b_bid
        if st != {}:
            if st['spread']/2 > spread+MOVE:
                if st['mid'] < mid:
                    orders.append(Order(PRODUCT, b_bid, -min(SIZE, POS_LIMIT + pos)))
                elif st['mid'] > mid:
                    orders.append(Order(PRODUCT, b_ask,  min(SIZE, POS_LIMIT - pos)))

        orders.append(Order(PRODUCT, b_bid + 1,  min(SIZE, POS_LIMIT - pos)))   # bid
        orders.append(Order(PRODUCT, b_ask - 1, -min(SIZE, POS_LIMIT + pos)))   # ask
        return {PRODUCT: orders}, 0, json.dumps({'mid':mid,'spread':spread})
