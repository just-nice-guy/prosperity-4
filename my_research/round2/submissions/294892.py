from __future__ import annotations
import json, math
try:
    from datamodel import Order, OrderDepth, TradingState
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState

PRODUCT   = "ASH_COATED_OSMIUM"
POS_LIMIT = 80
SIZE      = 12 #10
SIZE_TAKER= 12 #6

# A-S params
GAMMA     = 0.05 # 10**-10 #0.1    # aversion au risque
ALPHA     = -3.8 #-3.4943 #1.5    # poids imbalance dans skew
KAPPA     = 0.135 #0.1903 #1.0    # élasticité d'exécution (calibrer)
T         = 1.0    # horizon normalisé

# Taker params
K_SIGMA   = 0 #0.1 #0.0 2.0    # nb sigma pour cassure FV
BETA_VOL  = 4 #10     # fenêtre volatilité rolling
N_LEVELS  = 2      # profondeur micro-price
W_DECAY   = 0.12 #0.2748 #0.5    # décroissance des poids par niveau

AVG_DURATION = 5
AVG_DECAY=0.19

class Trader:
    def bid(self):
        return 1 #faudra trouver le nombre qui fait qu'on reste rentable si on a + 25% de volume supplementaire

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []
        st = json.loads(state.traderData) if state.traderData else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,  min(80, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**12,  -min(80, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, json.dumps(st)

        # --- FV micro-price multiniveau ---
        bids = sorted(depth.buy_orders.items(),  reverse=True)[:N_LEVELS]
        asks = sorted(depth.sell_orders.items())[:N_LEVELS]
        num, den, imb_b, imb_a = 0.0, 0.0, 0.0, 0.0
        for i, ((bp, bq), (ap, aq)) in enumerate(zip(bids, asks)):
            w   = math.exp(-W_DECAY * i)
            bq, aq = abs(bq), abs(aq)
            num += w * (aq * bp + bq * ap)
            den += w * (bq + aq)
            imb_b += w * bq
            imb_a += w * aq
        fv  = num / den if den else (bids[0][0] + asks[0][0]) / 2
        imb = (imb_b - imb_a) / (imb_b + imb_a)   # [-1, 1]

        # --- Volatilité rolling ---
        history = st.get("fv_hist", [])
        history.append(fv)
        if len(history) >= AVG_DURATION:
            num=0
            den=0
            for i in range(AVG_DURATION):
                num+=math.exp(-AVG_DECAY*i)*history[-i]
                den+=math.exp(-AVG_DECAY*i)
            fv=num/den
        if len(history) > BETA_VOL:
            history = history[-BETA_VOL:]
        if len(history) > 2:
            mean = sum(history) / len(history)
            sigma = math.sqrt(sum((x - mean)**2 for x in history) / len(history))
        else:
            sigma = 1

        # --- A-S : prix de réservation + spread ---
        r      = fv - pos * GAMMA * sigma**2 * T + ALPHA * imb
        spread = GAMMA * sigma**2 * T + (2 / GAMMA) * math.log(1 + GAMMA / KAPPA)
        spread = max(spread, 2)   # spread minimum 1 tick de chaque côté

        bid_price = round(r - spread / 2)
        ask_price = round(r + spread / 2)

        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)

        # --- Taker agressif sur cassure FV ---
        taker_triggered = False
        if sigma > 0:
            deviation = b_bid - fv if b_bid > fv else fv - b_ask if b_ask < fv else 0
            if deviation > K_SIGMA * sigma:
                if b_bid > fv:   # cassure haussière → on vend en taker
                    qty = min(SIZE_TAKER, POS_LIMIT + pos)
                    if qty > 0:
                        orders.append(Order(PRODUCT, b_bid, -qty))
                        taker_triggered = True
                elif b_ask < fv:  # cassure baissière → on achète en taker
                    qty = min(SIZE_TAKER, POS_LIMIT - pos)
                    if qty > 0:
                        orders.append(Order(PRODUCT, b_ask, qty))
                        taker_triggered = True

        # --- Quotes maker A-S (si pas de taker) ---
        if not taker_triggered:
            buy_qty  = min(SIZE, POS_LIMIT - pos)
            sell_qty = min(SIZE, POS_LIMIT + pos)
            if buy_qty  > 0: orders.append(Order(PRODUCT, bid_price, buy_qty))
            if sell_qty > 0: orders.append(Order(PRODUCT, ask_price, -sell_qty))

        st = {"fv_hist": history}
        return {PRODUCT: orders}, 0, json.dumps(st)