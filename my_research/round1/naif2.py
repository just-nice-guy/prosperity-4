from __future__ import annotations
import json
import math
try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT   = "ASH_COATED_OSMIUM"
POS_LIMIT = 80
SIZE      = 16
SIZE_MARKET= 10
MOVE=0
N_LEVELS=3
W_DECAY=0.2748

class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []
        st=json.loads(state.traderData) if state.traderData else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,  min(SIZE, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**12,  -min(SIZE, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, json.dumps(st)

        bids = sorted(depth.buy_orders.items(),  reverse=True)[:N_LEVELS]
        asks = sorted(depth.sell_orders.items())[:N_LEVELS]
        num, den, imb_b, imb_a = 0.0, 0.0, 0.0, 0.0
        for i, ((bp, bq), (ap, aq)) in enumerate(zip(bids, asks)):
            w   = math.exp(-W_DECAY * i)
            bq, aq = abs(bq), abs(aq)
            num += w * (aq * bp + bq * ap)
            den += w * (bq + aq)
        mid  = num / den if den else (bids[0][0] + asks[0][0]) / 2

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)

        spread=b_ask-b_bid

        if st != {}:
            if st['spread']/2 > spread+MOVE:
                if st['mid'] < mid:
                    orders.append(Order(PRODUCT, b_bid, -min(SIZE_MARKET, POS_LIMIT + pos)))
                    orders.append(Order(PRODUCT, b_ask - 1, -min(SIZE, POS_LIMIT + pos)))   # ask
                elif st['mid'] > mid:
                    orders.append(Order(PRODUCT, b_ask,  min(SIZE_MARKET, POS_LIMIT - pos)))
                    orders.append(Order(PRODUCT, b_bid + 1,  min(SIZE, POS_LIMIT - pos)))   # bid
            else:
                orders.append(Order(PRODUCT, b_ask - 1, -min(SIZE, POS_LIMIT + pos)))   # ask
                orders.append(Order(PRODUCT, b_bid + 1,  min(SIZE, POS_LIMIT - pos)))   # bid

        return {PRODUCT: orders}, 0, json.dumps({'mid':mid,'spread':spread})
