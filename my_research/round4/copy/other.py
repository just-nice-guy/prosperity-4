from __future__ import annotations
import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


PRODUCT = "HYDROGEL_PACK"

# =========================
# Risk / inventory
# =========================
# Official exchange limit only.
# No artificial +/-180 cap is used anywhere in the code.
POS_LIMIT = 200

# L0 dans les maths : taille maker de référence
BASE_SIZE = 12

QUOTE_WIDTH_MULT = 2.2

# =========================
# Microprice protected
# =========================
W = 0.2
MICRO_BALANCE_TOL = 1.0

# =========================
# OU parameters
# =========================
# Market parameters: kept equal to your original calibration.
# They describe the market and are not optimised directly for PnL.
KAPPA = 0.0017832392
HORIZON = 15.0
DT = 1.0

MU_MIN_WINDOW = 25 * 100
MU_FIXE = 9991.0012009026

VAR_MIN_WINDOW = 1000
VAR_FIXE = 1022.1842605233

EPS = 1e-9

# =========================
# Inventory parameters
# =========================
# Optimised policy parameter.
ETA_INV = 0.75

# asymétrie du sizing entre bid et ask
THETA_SIZE = 1.75

# =========================
# Avellaneda-Stoikov parameters
# =========================
GAMMA = 0.000050
AS_K = 0.355792

MIN_HALF_SPREAD = 1

# Pas de frais, pas d'adverse selection explicite dans les takers.
# Le signal participant est utilisé seulement pour skew la reservation maker.
TAKER_EDGE = 0.5

# =========================
# Participant-aware reservation skew
# =========================
# Empirical observation on supplied data:
# Mark 38 is the systematic aggressor and is profitable to fade.
MARK38_NAME = "Mark 38"

MARK38_DECAY = 0.96
MARK38_ALPHA = 1.0
MARK38_Q_SCALE = 12.0
MARK38_MAX_EDGE = 2.0


# =========================
# Precomputed constants
# =========================
PHI_DT = math.exp(-KAPPA * DT)
PHI_H = math.exp(-KAPPA * HORIZON)

DENOM = max(1.0 - math.exp(-2.0 * KAPPA * DT), EPS)
OU_VAR_H_MULT = 1.0 - math.exp(-2.0 * KAPPA * HORIZON)

AS_BASE_DELTA = (1.0 / GAMMA) * math.log(1.0 + GAMMA / AS_K)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


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
        if abs(diff[i]) <= MICRO_BALANCE_TOL:
            mi.append(i)

    if mi == []:
        return None

    num = 0.0
    den = 0.0

    for i in range(len(mi) - 1, -1, -1):
        idx = mi[i]
        weight = math.exp(-W * (len(mi) - i))
        num += (difu[idx][0][0] + difu[idx][1][0]) * 0.5 * weight
        den += weight

    if den <= 0:
        return None

    return num / den


def welford_step(x: float, n: int, mean: float, M2: float) -> tuple[int, float, float]:
    n_new = n + 1
    delta = x - mean
    mean_new = mean + delta / n_new
    delta2 = x - mean_new
    M2_new = M2 + delta * delta2

    return n_new, mean_new, M2_new


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        try:
            st = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            st = {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
            buy_qty = max(0, min(POS_LIMIT, POS_LIMIT - pos))
            sell_qty = max(0, min(POS_LIMIT, POS_LIMIT + pos))

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
        # 2. Microprice protected
        # =========================
        micro = micro_price_protected(depth)

        if micro is None:
            prev_micro = st.get("prev_micro", None)

            if prev_micro is None:
                micro = mid
            else:
                try:
                    micro = float(prev_micro)
                except Exception:
                    micro = mid

        # =========================
        # 3. Historical mean with prior
        # =========================
        micro_mean = st.get("micro_mean", -1)
        micro_counter = st.get("micro_counter", 0)

        if micro_mean == -1:
            micro_mean = MU_FIXE
            micro_counter = MU_MIN_WINDOW

        micro_counter, micro_mean, _ = welford_step(
            float(micro),
            int(micro_counter),
            float(micro_mean),
            0.0,
        )

        mu = micro_mean

        # =========================
        # 4. OU residual variance with prior
        # =========================
        eps_mean = float(st.get("eps_mean", 0.0))
        eps_counter = int(st.get("eps_counter", 0))
        eps_M2 = float(st.get("eps_M2", 0.0))

        prev_micro = st.get("prev_micro", None)

        if prev_micro is not None:
            try:
                prev_micro = float(prev_micro)

                expected_micro = mu + PHI_DT * (prev_micro - mu)
                eps_ou = micro - expected_micro

                eps_counter, eps_mean, eps_M2 = welford_step(
                    float(eps_ou),
                    eps_counter,
                    eps_mean,
                    eps_M2,
                )
            except Exception:
                pass

        if eps_counter > 1:
            var_eps_raw = max(eps_M2 / (eps_counter - 1), EPS)
        else:
            var_eps_raw = max(VAR_FIXE * DENOM, EPS)

        w_var = min(1.0, eps_counter / VAR_MIN_WINDOW)

        var_eps = (1.0 - w_var) * (VAR_FIXE * DENOM) + w_var * var_eps_raw

        var_inf = var_eps / DENOM
        sigma_inf = math.sqrt(max(var_inf, EPS))

        # =========================
        # 5. Fair price OU du microprice
        # =========================
        fair = mu + PHI_H * (micro - mu)

        # =========================
        # 6. Inventaire cible
        # =========================
        z = (micro - mu) / sigma_inf

        q_star = -POS_LIMIT * math.tanh(ETA_INV * z)

        # =========================
        # 7. Variance conditionnelle OU à horizon H
        # =========================
        var_h = var_inf * OU_VAR_H_MULT

        # =========================
        # 8. Participant signal: fade Mark 38
        # =========================
        mark38_flow = float(st.get("mark38_flow", 0.0))
        mark38_flow *= MARK38_DECAY

        for tr in state.market_trades.get(PRODUCT, []):
            qty = float(tr.quantity)

            if tr.buyer == MARK38_NAME:
                mark38_flow += qty

            if tr.seller == MARK38_NAME:
                mark38_flow -= qty

        mark38_edge = -MARK38_ALPHA * math.tanh(mark38_flow / MARK38_Q_SCALE)
        mark38_edge = clamp(mark38_edge, -MARK38_MAX_EDGE, MARK38_MAX_EDGE)

        # Important:
        # The participant edge is NOT used in taker logic.
        # It is only used later as a maker reservation skew.

        # =========================
        # 9. Ordres taker
        # =========================
        planned_pos = pos

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        # Buy taker: unchanged, based only on OU fair value.
        if fair > b_ask + TAKER_EDGE and planned_pos < q_star and buy_capacity > 0:
            desired_buy = int(math.floor(q_star - planned_pos))

            qty = min(
                desired_buy,
                buy_capacity,
                ask_vol,
            )

            if qty > 0:
                orders.append(Order(PRODUCT, b_ask, qty))
                planned_pos += qty

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        # Sell taker: unchanged, based only on OU fair value.
        if fair < b_bid - TAKER_EDGE and planned_pos > q_star and sell_capacity > 0:
            desired_sell = int(math.floor(planned_pos - q_star))

            qty = min(
                desired_sell,
                sell_capacity,
                bid_vol,
            )

            if qty > 0:
                orders.append(Order(PRODUCT, b_bid, -qty))
                planned_pos -= qty

        # =========================
        # 10. Prix de réservation après takers
        # =========================
        # Mark 38 skew is applied only here.
        # If Mark 38 buys aggressively -> mark38_edge < 0 -> reservation lower.
        # If Mark 38 sells aggressively -> mark38_edge > 0 -> reservation higher.
        reservation = fair + mark38_edge - GAMMA * var_h * (planned_pos - q_star)

        # =========================
        # 11. Demi-spread Avellaneda-Stoikov
        # =========================
        theoretical_delta = AS_BASE_DELTA + 0.5 * GAMMA * var_h
        theoretical_delta *= QUOTE_WIDTH_MULT

        half_spread = max(MIN_HALF_SPREAD, int(math.ceil(theoretical_delta)))

        # =========================
        # 12. Quotes maker autour du prix de réservation
        # =========================
        raw_bid = int(math.floor(reservation - half_spread))
        raw_ask = int(math.ceil(reservation + half_spread))

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
        # 13. Sizing maker
        # =========================
        inv_gap = q_star - planned_pos
        normalized_gap = inv_gap / POS_LIMIT

        bid_size_float = BASE_SIZE * max(
            0.0,
            1.0 + THETA_SIZE * normalized_gap,
        )

        ask_size_float = BASE_SIZE * max(
            0.0,
            1.0 - THETA_SIZE * normalized_gap,
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
        # 14. Sauvegarde état
        # =========================
        new_state = {
            "micro_mean": micro_mean,
            "micro_counter": micro_counter,
            "eps_mean": eps_mean,
            "eps_counter": eps_counter,
            "eps_M2": eps_M2,
            "prev_micro": micro,
            "mark38_flow": mark38_flow,
        }

        return {PRODUCT: orders}, 0, json.dumps(new_state)
