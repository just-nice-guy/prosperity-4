from __future__ import annotations
import json
import math
import statistics
import numpy as np

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


PRODUCT = "HYDROGEL_PACK"

# =========================
# Risk / inventory
# =========================
POS_LIMIT = 200

# L0 dans les maths : taille maker de référence
BASE_SIZE = 11 #5 #36


W=0.2
# =========================
# OU parameters
# =========================
# vitesse de retour a la moyenne
# censé etre fixe par le marché
KAPPA = 0.0054415955 #0.25
# horizon de la prevision
HORIZON = 12.0
# pas de temps du model
DT = 1.0

# Moyenne long terme du microprice
MU_WINDOW = 25*100 #98*100 # 25*100
MU_FIXE=9994

# Variance des résidus OU
VAR_WINDOW = 1000
VAR_FIXE=391.38

EPS = 1e-9

# =========================
# Inventory parameters
# =========================
# aggresivité de l'inventaire cible
ETA_INV = 0.75  #0.9729550745 #0.85
# asymetrie du sizing entre bid et ask (grand = directionelle petit = neutre)
THETA_SIZE = 2 #1.00 plus ou moin entre 0 et 1

# =========================
# Avellaneda-Stoikov parameters
# =========================
# aversion au risque d'inventaire
GAMMA = 0.000005 #0.0023604776 #0.015
# sensibilité proba de fille a la distance du quote
# censé etre fixe par le marché
AS_K = 0.5810298823 #1.50

MIN_HALF_SPREAD = 1

# Pas de frais, pas d'adverse selection
TAKER_EDGE = 0.5


def micro_price_protected(depth: OrderDepth) -> float | None:
    bids = sorted(depth.buy_orders.keys(), reverse=True)
    asks = sorted(depth.sell_orders.keys())

    if not bids or not asks:
        return None

    diff = []
    difu = []
    b_count = 0
    a_count = 0

    for i in range(min(len(bids), len(asks))):
        pb = bids[i]
        pa = asks[i]

        vb = float(depth.buy_orders[pb])
        va = float(abs(depth.sell_orders[pa]))

        # BID
        if vb > 0:
            b_count += 1
            if len(diff) < b_count:
                diff.append(vb)
                difu.append([[pb, vb]])
            else:
                diff[b_count - 1] += vb
                difu[b_count - 1].append([pb, vb])

        # ASK
        if va > 0:
            a_count += 1
            if len(diff) < a_count:
                diff.append(-va)
                difu.append([[pa, va]])
            else:
                diff[a_count - 1] -= va
                difu[a_count - 1].append([pa, va])

    mi = []
    for i in range(len(diff)):
        if diff[i] == 0:
            mi.append(i)

    if mi == []:
        return None

    num=0
    den=0
    for i in range(len(mi)-1,-1,-1):
        num+=(difu[mi[i]][0][0]+difu[mi[i]][1][0])*0.5*np.exp(-W*(len(mi)-i))
        den+=np.exp(-W*(len(mi)-i))
    return num/den



def rolling_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0

    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        st = json.loads(state.traderData) if state.traderData else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            buy_qty = max(0, min(BASE_SIZE, POS_LIMIT - pos))
            sell_qty = max(0, min(BASE_SIZE, POS_LIMIT + pos))

            if buy_qty > 0:
                orders.append(Order(PRODUCT, 1, buy_qty))

            if sell_qty > 0:
                orders.append(Order(PRODUCT, 10**12, -sell_qty))

            return {PRODUCT: orders}, 0, json.dumps(st)

        # =========================
        # 1. Best bid / best ask
        # =========================
        b_bid = max(depth.buy_orders)
        b_ask = min(depth.sell_orders)

        bid_vol = depth.buy_orders[b_bid]
        ask_vol = -depth.sell_orders[b_ask]

        spread = b_ask - b_bid
        mid = (b_bid + b_ask) / 2.0

        # =========================
        # 2. Microprice
        # =========================
        micro = micro_price_protected(depth)
        if micro is None:
            micro = mid

        # =========================
        # 3. Rolling median pour mu
        # =========================
        micro_hist = st.get("micro_hist", [])
        if len(micro_hist) == 0:
            micro_hist+=[MU_FIXE]*MU_WINDOW
        micro_hist.append(micro)

        if len(micro_hist) > MU_WINDOW:
            micro_hist = micro_hist[-MU_WINDOW:]

        #mu = statistics.median(micro_hist)
        mu= (1/3)*((min(micro_hist)+max(micro_hist))/2+sum(micro_hist)/len(micro_hist)+np.median(micro_hist))
        # =========================
        # 4. Variance OU via résidus one-step
        # =========================
        phi_dt = math.exp(-KAPPA * DT)

        eps_hist = st.get("eps_hist", [])
        if len(eps_hist) == 0:
            eps_hist+=[VAR_FIXE]*VAR_WINDOW
        prev_micro = st.get("prev_micro", None)

        if prev_micro is not None:
            prev_micro = float(prev_micro)

            expected_micro = mu + phi_dt * (prev_micro - mu)

            eps_ou = micro - expected_micro

            eps_hist.append(eps_ou)

            if len(eps_hist) > VAR_WINDOW:
                eps_hist = eps_hist[-VAR_WINDOW:]

        var_eps = max(rolling_variance(eps_hist), EPS)

        denom = max(1.0 - math.exp(-2.0 * KAPPA * DT), EPS)

        var_inf = var_eps / denom
        sigma_inf = math.sqrt(max(var_inf, EPS))

        # =========================
        # 5. Fair price OU du microprice
        # =========================
        phi_h = math.exp(-KAPPA * HORIZON)

        fair = mu + phi_h * (micro - mu)

        alpha = fair - micro

        # =========================
        # 6. Inventaire cible
        # =========================
        z = (micro - mu) / sigma_inf

        q_star = -POS_LIMIT * math.tanh(ETA_INV * z)

        # =========================
        # 7. Variance conditionnelle OU à horizon H
        # =========================
        var_h = var_inf * (1.0 - math.exp(-2.0 * KAPPA * HORIZON))

        # =========================
        # 8. Ordres taker conformes au modèle
        # =========================
        planned_pos = pos

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        # Buy taker si fair > ask et si inventaire sous la cible
        if fair > b_ask + TAKER_EDGE and planned_pos < q_star and buy_capacity > 0:
            desired_buy = int(math.floor(q_star - planned_pos))

            qty = min(
                desired_buy,
                buy_capacity,
                ask_vol
            )

            if qty > 0:
                orders.append(Order(PRODUCT, b_ask, qty))
                planned_pos += qty

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        # Sell taker si fair < bid et si inventaire au-dessus de la cible
        if fair < b_bid - TAKER_EDGE and planned_pos > q_star and sell_capacity > 0:
            desired_sell = int(math.floor(planned_pos - q_star))

            qty = min(
                desired_sell,
                sell_capacity,
                bid_vol
            )

            if qty > 0:
                orders.append(Order(PRODUCT, b_bid, -qty))
                planned_pos -= qty

        # =========================
        # 9. Prix de réservation après takers
        # =========================
        reservation = fair - GAMMA * var_h * (planned_pos - q_star)

        # =========================
        # 10. Demi-spread Avellaneda-Stoikov
        # =========================
        theoretical_delta = (
            (1.0 / GAMMA) * math.log(1.0 + GAMMA / AS_K)
            + 0.5 * GAMMA * var_h
        )

        half_spread = max(MIN_HALF_SPREAD, int(math.ceil(theoretical_delta)))

        # =========================
        # 11. Quotes maker autour du prix de réservation
        # =========================
        raw_bid = int(math.floor(reservation - half_spread))
        raw_ask = int(math.ceil(reservation + half_spread))

        # On garde les ordres maker.
        # Si le spread est large, on peut se placer dans le spread sans croiser.
        if spread >= 3:
            maker_bid = min(raw_bid, b_ask - 1)
            maker_ask = max(raw_ask, b_bid + 1)
        else:
            maker_bid = min(raw_bid, b_bid)
            maker_ask = max(raw_ask, b_ask)

        if maker_bid >= maker_ask:
            maker_bid = b_bid
            maker_ask = b_ask

        # =========================
        # 12. Sizing maker conforme aux maths
        # =========================
        inv_gap = q_star - planned_pos
        normalized_gap = inv_gap / POS_LIMIT

        bid_size_float = BASE_SIZE * max(
            0.0,
            1.0 + THETA_SIZE * normalized_gap
        )

        ask_size_float = BASE_SIZE * max(
            0.0,
            1.0 - THETA_SIZE * normalized_gap
        )

        bid_size = int(round(bid_size_float))
        ask_size = int(round(ask_size_float))

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        buy_qty = max(0, min(bid_size, buy_capacity))
        sell_qty = max(0, min(ask_size, sell_capacity))

        if buy_qty > 0:
            orders.append(Order(PRODUCT, maker_bid, buy_qty))

        if sell_qty > 0:
            orders.append(Order(PRODUCT, maker_ask, -sell_qty))

        # =========================
        # 13. Sauvegarde état
        # =========================
        new_state = {
            "micro_hist": micro_hist,
            "eps_hist": eps_hist,
            "prev_micro": micro,

        }

        return {PRODUCT: orders}, 0, json.dumps(new_state)
