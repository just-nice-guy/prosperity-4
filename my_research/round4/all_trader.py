from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


EPS = 1e-9

CONFIGS: dict[str, dict] = {
    "HYDROGEL_PACK": {
        "pos_limit": 200,
        "base_size": 12,
        "quote_width_mult": 2.2,
        "w": 0.2,
        "micro_balance_tol": 1.0,
        "kappa": 0.0017832392,
        "horizon": 15.0,
        "dt": 1.0,
        "mu_min_window": 25 * 100,
        "mu_fixe": 9991.0012009026,
        "var_min_window": 1000,
        "var_fixe": 1022.1842605233,
        "eta_inv": 0.75,
        "theta_size": 1.75,
        "gamma": 0.000050,
        "as_k": 0.355792,
        "min_half_spread": 1,
        "taker_edge": 0.5,
        "participant_mode": "mark38_fade",
        "mark38_name": "Mark 38",
        "mark38_decay": 0.96,
        "mark38_alpha": 1.0,
        "mark38_q_scale": 12.0,
        "mark38_max_edge": 2.0,
    },
    "VELVETFRUIT_EXTRACT": {
        "pos_limit": 200,
        "base_size": 22,
        "quote_width_mult": 1.2,
        "w": 0.0,
        "micro_balance_tol": 1.0,
        "kappa": 0.00145,
        "horizon": 50.0,
        "dt": 1.0,
        "mu_min_window": 25 * 100,
        "mu_fixe": 5241.5,
        "var_min_window": 1000,
        "var_fixe": 350.0,
        "eta_inv": 0.4,
        "theta_size": 0.75,
        "gamma": 0.00038,
        "as_k": 0.6,
        "min_half_spread": 1,
        "taker_edge": 1.5,
        "participant_mode": "general",
        "participant_decay": 0.96,
        "participant_q_scale": 8.0,
        "participant_max_edge": 0.3,
        "participant_coefs": {
            "Mark 14": -0.6,
            "Mark 55": 0.4,
        },
    },
    "VEV_4000": {
        "pos_limit": 300,
        "base_size": 90,
        "quote_width_mult": 1.1,
        "w": 0.0,
        "micro_balance_tol": 1.0,
        "kappa": 0.001395,
        "horizon": 340.0,
        "dt": 1.0,
        "mu_min_window": 25 * 100,
        "mu_fixe": 1247.3,
        "var_min_window": 1000,
        "var_fixe": 328.14,
        "eta_inv": 0.42,
        "theta_size": 2.5,
        "gamma": 0.00012,
        "as_k": 0.14,
        "min_half_spread": 1,
        "taker_edge": -0.35,
        "participant_mode": "general",
        "participant_decay": 0.96,
        "participant_q_scale": 8.0,
        "participant_max_edge": 0.0,
        "participant_coefs": {
            "Mark 14": 0.0,
            "Mark 38": -0.0,
        },
    },
    "VEV_4500": {
        "pos_limit": 300,
        "base_size": 20,
        "quote_width_mult": 2.0,
        "w": 0.0,
        "micro_balance_tol": 1.0,
        "kappa": 0.00248,
        "horizon": 140.0,
        "dt": 1.0,
        "mu_min_window": 25 * 100,
        "mu_fixe": 747.46,
        "var_min_window": 1000,
        "var_fixe": 328.5,
        "eta_inv": 0.27,
        "theta_size": 2.0,
        "gamma": 0.00018,
        "as_k": 0.30,
        "min_half_spread": 1,
        "taker_edge": -3.5,
        "participant_mode": "general",
        "participant_decay": 0.96,
        "participant_q_scale": 8.0,
        "participant_max_edge": 0.0,
        "participant_coefs": {
            "Mark 38": 0.0,
            "Mark 22": -0.0,
        },
    },
}


for _cfg in CONFIGS.values():
    kappa = float(_cfg["kappa"])
    dt = float(_cfg["dt"])
    horizon = float(_cfg["horizon"])
    gamma = float(_cfg["gamma"])
    as_k = float(_cfg["as_k"])

    _cfg["phi_dt"] = math.exp(-kappa * dt)
    _cfg["phi_h"] = math.exp(-kappa * horizon)
    _cfg["denom"] = max(1.0 - math.exp(-2.0 * kappa * dt), EPS)
    _cfg["ou_var_h_mult"] = 1.0 - math.exp(-2.0 * kappa * horizon)
    _cfg["as_base_delta"] = (1.0 / gamma) * math.log(1.0 + gamma / as_k)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def micro_price_protected(depth: OrderDepth, w: float, micro_balance_tol: float) -> float | None:
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

        if vb > 0:
            b_count += 1
            if len(diff) < b_count:
                diff.append(vb)
                difu.append([[float(pb), vb]])
            else:
                diff[b_count - 1] += vb
                difu[b_count - 1].append([float(pb), vb])

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
        if abs(diff[i]) <= micro_balance_tol:
            balanced_indices.append(i)

    if not balanced_indices:
        return None

    num = 0.0
    den = 0.0

    for i in range(len(balanced_indices) - 1, -1, -1):
        idx = balanced_indices[i]

        if len(difu[idx]) < 2:
            continue

        weight = math.exp(-w * (len(balanced_indices) - i))
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


def compute_participant_edge(
    product: str,
    state: TradingState,
    cfg: dict,
    st: dict,
) -> tuple[float, dict]:
    mode = cfg.get("participant_mode", "none")

    if mode == "mark38_fade":
        mark38_flow = float(st.get("mark38_flow", 0.0))
        mark38_flow *= float(cfg["mark38_decay"])

        mark38_name = str(cfg["mark38_name"])

        for tr in state.market_trades.get(product, []):
            qty = float(tr.quantity)

            if tr.buyer == mark38_name:
                mark38_flow += qty

            if tr.seller == mark38_name:
                mark38_flow -= qty

        mark38_edge = -float(cfg["mark38_alpha"]) * math.tanh(
            mark38_flow / float(cfg["mark38_q_scale"])
        )
        mark38_edge = clamp(
            mark38_edge,
            -float(cfg["mark38_max_edge"]),
            float(cfg["mark38_max_edge"]),
        )

        return mark38_edge, {"mark38_flow": mark38_flow}

    if mode == "general":
        participant_flows = st.get("participant_flows", {})
        if not isinstance(participant_flows, dict):
            participant_flows = {}

        decay = float(cfg["participant_decay"])
        for name in list(participant_flows.keys()):
            try:
                participant_flows[name] = float(participant_flows[name]) * decay
            except Exception:
                participant_flows[name] = 0.0

        participant_coefs: dict[str, float] = cfg["participant_coefs"]

        for tr in state.market_trades.get(product, []):
            qty = float(tr.quantity)

            if tr.buyer in participant_coefs:
                participant_flows[tr.buyer] = participant_flows.get(tr.buyer, 0.0) + qty

            if tr.seller in participant_coefs:
                participant_flows[tr.seller] = participant_flows.get(tr.seller, 0.0) - qty

        participant_edge = 0.0

        q_scale = float(cfg["participant_q_scale"])
        for name, coef in participant_coefs.items():
            flow = float(participant_flows.get(name, 0.0))
            participant_edge += float(coef) * math.tanh(flow / q_scale)

        participant_edge = clamp(
            participant_edge,
            -float(cfg["participant_max_edge"]),
            float(cfg["participant_max_edge"]),
        )

        return participant_edge, {"participant_flows": participant_flows}

    return 0.0, {}


def run_product(
    product: str,
    state: TradingState,
    cfg: dict,
    st: dict,
) -> tuple[list[Order], dict]:
    pos = state.position.get(product, 0)
    depth = state.order_depths.get(product)
    orders: list[Order] = []

    pos_limit = int(cfg["pos_limit"])

    if depth is None:
        return orders, st

    if not depth.buy_orders or not depth.sell_orders:
        buy_qty = max(0, min(pos_limit, pos_limit - pos))
        sell_qty = max(0, min(pos_limit, pos_limit + pos))

        if buy_qty > 0:
            orders.append(Order(product, 1, buy_qty))

        if sell_qty > 0:
            orders.append(Order(product, 10**12, -sell_qty))

        return orders, st

    b_bid = max(depth.buy_orders)
    b_ask = min(depth.sell_orders)

    bid_vol = int(depth.buy_orders[b_bid])
    ask_vol = int(-depth.sell_orders[b_ask])

    spread = b_ask - b_bid
    mid = 0.5 * (b_bid + b_ask)

    micro = micro_price_protected(
        depth,
        float(cfg["w"]),
        float(cfg["micro_balance_tol"]),
    )

    if micro is None:
        prev_micro = st.get("prev_micro", None)

        if prev_micro is None:
            micro = mid
        else:
            try:
                micro = float(prev_micro)
            except Exception:
                micro = mid

    micro_mean = st.get("micro_mean", -1)
    micro_counter = st.get("micro_counter", 0)

    if micro_mean == -1:
        micro_mean = float(cfg["mu_fixe"])
        micro_counter = int(cfg["mu_min_window"])

    micro_counter, micro_mean, _ = welford_step(
        float(micro),
        int(micro_counter),
        float(micro_mean),
        0.0,
    )

    mu = float(micro_mean)

    eps_mean = float(st.get("eps_mean", 0.0))
    eps_counter = int(st.get("eps_counter", 0))
    eps_M2 = float(st.get("eps_M2", 0.0))

    prev_micro = st.get("prev_micro", None)

    if prev_micro is not None:
        try:
            prev_micro_float = float(prev_micro)

            expected_micro = mu + float(cfg["phi_dt"]) * (prev_micro_float - mu)
            eps_ou = float(micro) - expected_micro

            eps_counter, eps_mean, eps_M2 = welford_step(
                float(eps_ou),
                eps_counter,
                eps_mean,
                eps_M2,
            )
        except Exception:
            pass

    denom = float(cfg["denom"])

    if eps_counter > 1:
        var_eps_raw = max(eps_M2 / (eps_counter - 1), EPS)
    else:
        var_eps_raw = max(float(cfg["var_fixe"]) * denom, EPS)

    w_var = min(1.0, eps_counter / int(cfg["var_min_window"]))

    var_eps = (1.0 - w_var) * (float(cfg["var_fixe"]) * denom) + w_var * var_eps_raw

    var_inf = var_eps / denom
    sigma_inf = math.sqrt(max(var_inf, EPS))

    fair = mu + float(cfg["phi_h"]) * (float(micro) - mu)

    z = (float(micro) - mu) / sigma_inf
    q_star = -pos_limit * math.tanh(float(cfg["eta_inv"]) * z)

    var_h = var_inf * float(cfg["ou_var_h_mult"])

    participant_edge, participant_state = compute_participant_edge(product, state, cfg, st)

    planned_pos = pos

    buy_capacity = pos_limit - planned_pos
    sell_capacity = pos_limit + planned_pos

    taker_edge = float(cfg["taker_edge"])

    if fair > b_ask + taker_edge and planned_pos < q_star and buy_capacity > 0:
        desired_buy = int(math.floor(q_star - planned_pos))
        qty = min(desired_buy, buy_capacity, ask_vol)

        if qty > 0:
            orders.append(Order(product, b_ask, qty))
            planned_pos += qty

    buy_capacity = pos_limit - planned_pos
    sell_capacity = pos_limit + planned_pos

    if fair < b_bid - taker_edge and planned_pos > q_star and sell_capacity > 0:
        desired_sell = int(math.floor(planned_pos - q_star))
        qty = min(desired_sell, sell_capacity, bid_vol)

        if qty > 0:
            orders.append(Order(product, b_bid, -qty))
            planned_pos -= qty

    reservation = (
        fair
        + participant_edge
        - float(cfg["gamma"]) * var_h * (planned_pos - q_star)
    )

    theoretical_delta = float(cfg["as_base_delta"]) + 0.5 * float(cfg["gamma"]) * var_h
    theoretical_delta *= float(cfg["quote_width_mult"])

    half_spread = max(int(cfg["min_half_spread"]), int(math.ceil(theoretical_delta)))

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

    inv_gap = q_star - planned_pos
    normalized_gap = inv_gap / pos_limit

    bid_size_float = float(cfg["base_size"]) * max(
        0.0,
        1.0 + float(cfg["theta_size"]) * normalized_gap,
    )

    ask_size_float = float(cfg["base_size"]) * max(
        0.0,
        1.0 - float(cfg["theta_size"]) * normalized_gap,
    )

    bid_size = int(round(bid_size_float))
    ask_size = int(round(ask_size_float))

    buy_capacity = pos_limit - planned_pos
    sell_capacity = pos_limit + planned_pos

    buy_qty = max(0, min(bid_size, buy_capacity))
    sell_qty = max(0, min(ask_size, sell_capacity))

    if buy_qty > 0:
        orders.append(Order(product, maker_bid, buy_qty))

    if sell_qty > 0:
        orders.append(Order(product, maker_ask, -sell_qty))

    new_state = {
        "micro_mean": micro_mean,
        "micro_counter": micro_counter,
        "eps_mean": eps_mean,
        "eps_counter": eps_counter,
        "eps_M2": eps_M2,
        "prev_micro": micro,
    }
    new_state.update(participant_state)

    return orders, new_state


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        try:
            all_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            all_state = {}

        if not isinstance(all_state, dict):
            all_state = {}

        result: dict[str, list[Order]] = {}
        new_all_state: dict[str, dict] = {}

        for product, cfg in CONFIGS.items():
            product_state = all_state.get(product, {})
            if not isinstance(product_state, dict):
                product_state = {}

            orders, new_product_state = run_product(product, state, cfg, product_state)

            if orders:
                result[product] = orders

            new_all_state[product] = new_product_state

        return result, 0, json.dumps(new_all_state, separators=(",", ":"))
