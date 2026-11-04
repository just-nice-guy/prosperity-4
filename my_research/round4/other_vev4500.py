from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


PRODUCT = "VEV_4500"

# =========================
# Risk / inventory
# =========================
# Official exchange limit only.
# The optimisation constraint +/-180 is NOT coded here.
POS_LIMIT = 300

# Maker reference size
BASE_SIZE = 20

QUOTE_WIDTH_MULT = 2.0

# =========================
# Microprice protected
# =========================
# MICRO_BALANCE_TOL is fixed by constraint.
W = 0.0
MICRO_BALANCE_TOL = 1.0

# =========================
# OU parameters
# =========================
KAPPA = 0.00248
HORIZON = 140.0
DT = 1.0

MU_MIN_WINDOW = 25 * 100
MU_FIXE = 747.46

VAR_MIN_WINDOW = 1000
VAR_FIXE = 328.5

EPS = 1e-9

# =========================
# Inventory parameters
# =========================
ETA_INV = 0.27
THETA_SIZE = 2

# =========================
# Avellaneda-Stoikov parameters
# =========================
GAMMA = 0.00018
AS_K = 0.30

MIN_HALF_SPREAD = 1
TAKER_EDGE = -3.5

# =========================
# Participant-aware reservation skew
# =========================
# Coef > 0 : follow participant flow.
# Coef < 0 : fade participant flow.
PARTICIPANT_DECAY = 0.96
PARTICIPANT_Q_SCALE = 8.0
PARTICIPANT_MAX_EDGE =0.0

PARTICIPANT_COEFS = {
    "Mark 38": 0.0,
    "Mark 22": -0.0,
}
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

    diff: list[float] = []
    difu: list[list[list[float]]] = []

    b_count = 0
    a_count = 0

    for i in range(min(len(bids), len(asks))):
        pb = bids[i]
        pa = asks[i]

        vb = float(depth.buy_orders[pb])
        va = float(abs(depth.sell_orders[pa]))

        # BID side
        if vb > 0:
            b_count += 1

            if len(diff) < b_count:
                diff.append(vb)
                difu.append([[float(pb), vb]])
            else:
                diff[b_count - 1] += vb
                difu[b_count - 1].append([float(pb), vb])

        # ASK side
        if va > 0:
            a_count += 1

            if len(diff) < a_count:
                diff.append(-va)
                difu.append([[float(pa), va]])
            else:
                diff[a_count - 1] -= va
                difu[a_count - 1].append([float(pa), va])

    balanced_indices: list[int] = []

    for i in range(len(diff)):
        if abs(diff[i]) <= MICRO_BALANCE_TOL:
            balanced_indices.append(i)

    if not balanced_indices:
        return None

    num = 0.0
    den = 0.0

    for i in range(len(balanced_indices) - 1, -1, -1):
        idx = balanced_indices[i]

        if len(difu[idx]) < 2:
            continue

        weight = math.exp(-W * (len(balanced_indices) - i))

        local_price = 0.5 * (difu[idx][0][0] + difu[idx][1][0])

        num += local_price * weight
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

        # =========================
        # Empty book fallback
        # =========================
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

        bid_vol = int(depth.buy_orders[b_bid])
        ask_vol = int(-depth.sell_orders[b_ask])

        spread = b_ask - b_bid
        mid = 0.5 * (b_bid + b_ask)

        # =========================
        # 2. Protected microprice
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

        mu = float(micro_mean)

        # =========================
        # 4. OU residual variance with prior
        # =========================
        eps_mean = float(st.get("eps_mean", 0.0))
        eps_counter = int(st.get("eps_counter", 0))
        eps_M2 = float(st.get("eps_M2", 0.0))

        prev_micro = st.get("prev_micro", None)

        if prev_micro is not None:
            try:
                prev_micro_float = float(prev_micro)

                expected_micro = mu + PHI_DT * (prev_micro_float - mu)
                eps_ou = float(micro) - expected_micro

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
        # 5. OU fair price
        # =========================
        fair = mu + PHI_H * (float(micro) - mu)

        # =========================
        # 6. Target inventory
        # =========================
        z = (float(micro) - mu) / sigma_inf

        q_star = -POS_LIMIT * math.tanh(ETA_INV * z)

        # =========================
        # 7. Conditional OU variance over horizon
        # =========================
        var_h = var_inf * OU_VAR_H_MULT

        # =========================
        # 8. Participant signal
        # =========================
        participant_flows = st.get("participant_flows", {})

        if not isinstance(participant_flows, dict):
            participant_flows = {}

        # Decay stored participant flows
        for name in list(participant_flows.keys()):
            try:
                participant_flows[name] = float(participant_flows[name]) * PARTICIPANT_DECAY
            except Exception:
                participant_flows[name] = 0.0

        # Update flows using current market trades
        for tr in state.market_trades.get(PRODUCT, []):
            qty = float(tr.quantity)

            if tr.buyer in PARTICIPANT_COEFS:
                participant_flows[tr.buyer] = participant_flows.get(tr.buyer, 0.0) + qty

            if tr.seller in PARTICIPANT_COEFS:
                participant_flows[tr.seller] = participant_flows.get(tr.seller, 0.0) - qty

        participant_edge = 0.0

        for name, coef in PARTICIPANT_COEFS.items():
            flow = float(participant_flows.get(name, 0.0))
            participant_edge += float(coef) * math.tanh(flow / PARTICIPANT_Q_SCALE)

        participant_edge = clamp(
            participant_edge,
            -PARTICIPANT_MAX_EDGE,
            PARTICIPANT_MAX_EDGE,
        )

        # Important:
        # The participant signal is used only as maker reservation skew.
        # It is not used in taker logic.

        # =========================
        # 9. Taker orders
        # =========================
        planned_pos = pos

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        # Buy taker: based only on OU fair value.
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

        # Sell taker: based only on OU fair value.
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
        # 10. Reservation price after takers
        # =========================
        reservation = (
            fair
            + participant_edge
            - GAMMA * var_h * (planned_pos - q_star)
        )

        # =========================
        # 11. Avellaneda-Stoikov half-spread
        # =========================
        theoretical_delta = AS_BASE_DELTA + 0.5 * GAMMA * var_h
        theoretical_delta *= QUOTE_WIDTH_MULT

        half_spread = max(MIN_HALF_SPREAD, int(math.ceil(theoretical_delta)))

        # =========================
        # 12. Maker quotes around reservation
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
        # 13. Maker sizing
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
        # 14. Save state
        # =========================
        new_state = {
            "micro_mean": micro_mean,
            "micro_counter": micro_counter,
            "eps_mean": eps_mean,
            "eps_counter": eps_counter,
            "eps_M2": eps_M2,
            "prev_micro": micro,
            "participant_flows": participant_flows,
        }

        return {PRODUCT: orders}, 0, json.dumps(new_state)
