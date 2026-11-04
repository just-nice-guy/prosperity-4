from __future__ import annotations
import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


PRODUCT = "GALAXY_SOUNDS_SOLAR_FLAMES"

# =========================
# Risk / inventory
# =========================
POS_LIMIT = 10
BASE_SIZE = 5
QUOTE_WIDTH_MULT = 1

# =========================
# Microprice protected
# =========================
W = 0.2
MICRO_BALANCE_TOL = 7.0

# =========================
# OU parameters in log-price space
# =========================
KAPPA = 0.0005
HORIZON = 1.0
DT = 1.0

EPS = 1e-12

# Fallback price level
MU_PRICE_FIXE = 11092.5717
MU_LOG_FIXE = math.log(MU_PRICE_FIXE)

# Fallback absolute variance converted approximately to log variance
#VAR_PRICE_FIXE = 0.00003
VAR_LOG_FIXE = 0.00003 #VAR_PRICE_FIXE / (MU_PRICE_FIXE * MU_PRICE_FIXE)

# Rolling windows
OLS_WINDOW = 500
OLS_MIN_WINDOW = 40

VAR_WINDOW = 100
VAR_MIN_WINDOW = 40

# Trend shrinkage
# 0 = no OLS trend projection
# 1 = full OLS trend projection
TREND_LAMBDA = 0.25

# =========================
# Inventory parameters
# =========================
ETA_INV = 4
THETA_SIZE = 1.0

# =========================
# Avellaneda-Stoikov parameters in log-price space
# =========================
GAMMA = 0.0005
AS_K = 1549.49994621926
MIN_TICK_SPREAD = 1
TAKER_EDGE_TICKS = 1

# =========================
# Precomputed constants
# =========================
PHI_DT = math.exp(-KAPPA * DT)
PHI_H = math.exp(-KAPPA * HORIZON)

DENOM = max(1.0 - math.exp(-2.0 * KAPPA * DT), EPS)
OU_VAR_H_MULT = 1.0 - math.exp(-2.0 * KAPPA * HORIZON)

AS_BASE_DELTA_LOG = (1.0 / GAMMA) * math.log(1.0 + GAMMA / AS_K)


def clamp_list(xs: list[float], max_len: int) -> list[float]:
    if len(xs) > max_len:
        return xs[-max_len:]
    return xs


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

        if vb > 0:
            b_count += 1
            if len(diff) < b_count:
                diff.append(vb)
                difu.append([[pb, vb]])
            else:
                diff[b_count - 1] += vb
                difu[b_count - 1].append([pb, vb])

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
        weight = math.exp(-W * (len(mi) - i))
        num += (difu[mi[i]][0][0] + difu[mi[i]][1][0]) * 0.5 * weight
        den += weight

    return num / max(den, EPS)


def rolling_ols_log(xs: list[float]) -> tuple[float, float, float, float]:
    """
    OLS glissante sur :
        X_i = alpha + beta * i

    où X_i = log(microprice_i)

    Retourne :
        mu_0 : valeur de tendance au temps courant
        mu_h : valeur projetée à horizon HORIZON
        beta : pente log par tick
        r2   : qualité explicative approximative
    """
    n = len(xs)

    if n < OLS_MIN_WINDOW:
        mu_0 = xs[-1] if n > 0 else MU_LOG_FIXE
        return mu_0, mu_0, 0.0, 0.0

    y_mean = sum(xs) / n
    x_mean = (n - 1) / 2.0

    sxx = 0.0
    sxy = 0.0
    syy = 0.0

    for i, y in enumerate(xs):
        dx = i - x_mean
        dy = y - y_mean
        sxx += dx * dx
        sxy += dx * dy
        syy += dy * dy

    beta = sxy / max(sxx, EPS)
    alpha = y_mean - beta * x_mean

    current_x = n - 1

    mu_0_raw = alpha + beta * current_x
    mu_h_raw = alpha + beta * (current_x + HORIZON)

    mu_0 = mu_0_raw
    mu_h = mu_0_raw + TREND_LAMBDA * (mu_h_raw - mu_0_raw)

    r2 = (sxy * sxy) / max(sxx * syy, EPS)

    return mu_0, mu_h, beta, r2


def rolling_sample_variance(xs: list[float]) -> float | None:
    n = len(xs)

    if n < 2:
        return None

    mean = sum(xs) / n
    m2 = 0.0

    for x in xs:
        d = x - mean
        m2 += d * d

    return m2 / (n - 1)


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        st = json.loads(state.traderData) if state.traderData else {}

        if not depth or not depth.buy_orders or not depth.sell_orders:
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
            micro = mid if prev_micro is None else float(prev_micro)

        micro = max(float(micro), EPS)
        x = math.log(micro)

        # =========================
        # 3. Historique glissant du log-microprice
        # =========================
        x_hist = [float(v) for v in st.get("x_hist", [])]
        x_hist.append(x)
        x_hist = clamp_list(x_hist, OLS_WINDOW)

        # =========================
        # 4. Moyenne dynamique OLS en log-prix
        # =========================
        mu_0, mu_h, trend_beta, trend_r2 = rolling_ols_log(x_hist)

        # =========================
        # 5. Résidus OU dynamiques en log-prix
        # =========================
        eps_hist = [float(v) for v in st.get("eps_hist", [])]

        prev_x = st.get("prev_x", None)
        prev_mu_0 = st.get("prev_mu_0", None)
        prev_mu_1 = st.get("prev_mu_1", None)

        if prev_x is not None and prev_mu_0 is not None and prev_mu_1 is not None:
            prev_x = float(prev_x)
            prev_mu_0 = float(prev_mu_0)
            prev_mu_1 = float(prev_mu_1)

            expected_x = prev_mu_1 + PHI_DT * (prev_x - prev_mu_0)
            eps_ou = x - expected_x

            eps_hist.append(float(eps_ou))
            eps_hist = clamp_list(eps_hist, VAR_WINDOW)

        var_eps_raw = rolling_sample_variance(eps_hist)

        if var_eps_raw is None:
            var_eps_raw = VAR_LOG_FIXE * DENOM

        w_var = min(1.0, len(eps_hist) / VAR_MIN_WINDOW)

        var_eps = (1.0 - w_var) * (VAR_LOG_FIXE * DENOM) + w_var * max(var_eps_raw, EPS)

        # Variance stationnaire du OU en log-prix
        var_inf = var_eps / DENOM
        sigma_inf = math.sqrt(max(var_inf, EPS))

        # =========================
        # 6. Fair price OU en log-prix
        # =========================
        fair_log = mu_h + PHI_H * (x - mu_0)
        fair = math.exp(fair_log)

        # =========================
        # 7. Inventaire cible
        # =========================
        z = (x - mu_0) / sigma_inf
        q_star = -POS_LIMIT * math.tanh(ETA_INV * z)

        # =========================
        # 8. Variance conditionnelle OU à horizon H
        # =========================
        var_h = var_inf * OU_VAR_H_MULT

        # =========================
        # 9. Ordres taker
        # =========================
        planned_pos = pos

        buy_capacity = POS_LIMIT - planned_pos
        sell_capacity = POS_LIMIT + planned_pos

        if fair > b_ask + TAKER_EDGE_TICKS and planned_pos < q_star and buy_capacity > 0:
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

        if fair < b_bid - TAKER_EDGE_TICKS and planned_pos > q_star and sell_capacity > 0:
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
        # 10. Prix de réservation en log-prix
        # =========================
        reservation_log = fair_log - GAMMA * var_h * (planned_pos - q_star)

        # =========================
        # 11. Demi-spread A-S en log-prix
        # =========================
        delta_log = AS_BASE_DELTA_LOG + 0.5 * GAMMA * var_h
        delta_log *= QUOTE_WIDTH_MULT
        delta_log = max(delta_log, EPS)

        # Conversion log -> prix
        raw_bid = int(math.floor(math.exp(reservation_log - delta_log)))
        raw_ask = int(math.ceil(math.exp(reservation_log + delta_log)))

        # Sécurité : spread minimal en ticks
        if raw_ask - raw_bid < MIN_TICK_SPREAD:
            center = math.exp(reservation_log)
            raw_bid = int(math.floor(center - MIN_TICK_SPREAD / 2.0))
            raw_ask = int(math.ceil(center + MIN_TICK_SPREAD / 2.0))

        # =========================
        # 12. Quotes maker
        # =========================
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
        mu_1 = mu_0 + TREND_LAMBDA * trend_beta * DT

        new_state = {
            "x_hist": x_hist,
            "eps_hist": eps_hist,

            "prev_micro": micro,
            "prev_x": x,
            "prev_mu_0": mu_0,
            "prev_mu_1": mu_1,

            # Diagnostics
            "mu_0_log": mu_0,
            "mu_h_log": mu_h,
            "fair_log": fair_log,
            "reservation_log": reservation_log,
            "delta_log": delta_log,

            "mu_0_price": math.exp(mu_0),
            "mu_h_price": math.exp(mu_h),
            "fair_price": fair,
            "reservation_price": math.exp(reservation_log),

            "trend_beta": trend_beta,
            "trend_r2": trend_r2,
            "sigma_inf_log": sigma_inf,
            "q_star": q_star,
        }

        return {PRODUCT: orders}, 0, json.dumps(new_state)
