"""
Merged trader — VE + VEV options (476865) + HYDROGEL_PACK (loutre).
Both strategies run independently with separate state.
"""
from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ═══════════════════════════════════════════════════════════════════════════════
#  VE + VEV constants & helpers  (from 476865)
# ═══════════════════════════════════════════════════════════════════════════════
VE = "VELVETFRUIT_EXTRACT"
VE_LIMIT = 200

ALL_VEV: dict[str, float] = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500, "VEV_6000": 6000, "VEV_6500": 6500,
}
VEV_LIMIT = 300

SIGMA_IV = 0.24
TICKS_PER_DAY = 1_000_000

OU_WINDOW = 1500
OU_RECAL_EVERY = 1
OU_MIN_SAMPLES = 100

GAMMA_BASE = 0.003
GAMMA_MIN = 0.001
GAMMA_MAX = 0.03
VE_HALF_SPREAD_MIN = 2
VE_HALF_SPREAD_MAX = 8
VE_LEVELS = 3
VE_SIZE_PER_LEVEL = 40

CUM_INNOV_LOOKBACK = 40
CUM_INNOV_WEIGHT = 0.4

CI_SUPPRESS_Z = 2.0
CI_SUPPRESS_MAX = 0.8

Z_BAND_K_BASE = 1.2
Z_BAND_K_MIN = 0.8
Z_BAND_K_MAX = 2.0
Z_BAND_DECAY = 0.998
Z_BAND_VAR_DECAY = 0.997

Z_TARGET_DEAD = 0.8
Z_TARGET_FULL = 2.5
TARGET_DECAY = 0.9

LAM_PRICE_EMA = 0.9
LAM_PRICE_VAR = 0.99
SIGMA_PRICE_INIT = 1.5
Z_PRICE_HEAVY = 3.0
Z_PRICE_LIGHT = 2.0
AGG_VE_SIZE_HEAVY = 50
AGG_VE_SIZE_LIGHT = 25

GAP_AGG_MIN = 40
GAP_AGG_SIZE = 8
GAP_AGG_COOLDOWN = 1000

AGG_OPT_DELTA_GAP = 20
AGG_OPT_SIZE = 30

HEAVY_VE_SIZE = 60
HEAVY_OPT_SIZE = 40
HEAVY_CI_DELTA = 0.5
HEAVY_COOLDOWN = 50000
HEAVY_MAX_POS = 80
HEAVY_MAX_DELTA = 150

OPT_EDGE_MIN = 1.0
OPT_SIZE_BASE = 20
OPT_SIZE_MAX = 60
OPT_SPREAD_MAX = 6


_SQRT2 = math.sqrt(2.0)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _bs_call(S: float, K: float, T: float, sig: float) -> float:
    if T <= 0 or sig <= 0:
        return max(0.0, S - K)
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / (sig * sqT)
    d2 = d1 - sig * sqT
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def _bs_delta(S: float, K: float, T: float, sig: float) -> float:
    if T <= 0 or sig <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / (sig * math.sqrt(T))
    return _norm_cdf(d1)


def fit_ou(prices: list[float]) -> tuple[float, float, float]:
    n = len(prices)
    if n < 10:
        return 0.001, prices[-1] if prices else 5250.0, 1.0
    sx = sy = sxx = sxy = 0.0
    for i in range(n - 1):
        x, y = prices[i], prices[i + 1]
        sx += x; sy += y; sxx += x * x; sxy += x * y
    nm = n - 1
    denom = nm * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.001, sum(prices) / n, 1.0
    b = (nm * sxy - sx * sy) / denom
    a = (sy - b * sx) / nm
    b = max(0.0001, min(b, 0.9999))
    theta = -math.log(b)
    mu = a / (1.0 - b)
    ss_res = sum((prices[i + 1] - a - b * prices[i]) ** 2 for i in range(nm))
    sigma = math.sqrt(ss_res / nm)
    return theta, mu, sigma


class S2State:
    __slots__ = (
        "price_buf", "ou_theta", "ou_mu", "ou_sigma",
        "ticks_since_recal", "has_calibrated",
        "pred_errors",
        "tte_base_days",
        "ask_ema", "bid_ema", "sigma_ask2", "sigma_bid2",
        "z_ema", "z_var",
        "smooth_target", "last_agg_ts",
        "prev_ci", "last_heavy_ts",
    )

    def __init__(self):
        self.price_buf: list[float] = []
        self.ou_theta: float = 0.002
        self.ou_mu: float = 0.0
        self.ou_sigma: float = 1.1
        self.ticks_since_recal: int = 0
        self.has_calibrated: bool = False
        self.pred_errors: list[float] = []
        self.tte_base_days: float = 8.0
        self.ask_ema: float | None = None
        self.bid_ema: float | None = None
        self.sigma_ask2: float = SIGMA_PRICE_INIT ** 2
        self.sigma_bid2: float = SIGMA_PRICE_INIT ** 2
        self.z_ema: float = 0.0
        self.z_var: float = 1.0

        self.smooth_target: float = 0.0
        self.last_agg_ts: int = -9999
        self.prev_ci: float = 0.0
        self.last_heavy_ts: int = -9999

    def to_json(self) -> str:
        buf = self.price_buf[-OU_WINDOW:] if len(self.price_buf) > OU_WINDOW else self.price_buf
        errs = self.pred_errors[-200:] if len(self.pred_errors) > 200 else self.pred_errors
        return json.dumps({
            "pb": buf, "ot": self.ou_theta, "om": self.ou_mu, "os": self.ou_sigma,
            "tr": self.ticks_since_recal, "hc": self.has_calibrated,
            "pe": errs, "td": self.tte_base_days,
            "ae": self.ask_ema, "be": self.bid_ema,
            "sa2": self.sigma_ask2, "sb2": self.sigma_bid2,
            "ze": self.z_ema, "zv": self.z_var,
            "st": self.smooth_target, "lat": self.last_agg_ts,
            "pci": self.prev_ci, "lht": self.last_heavy_ts,
        })

    @classmethod
    def from_json(cls, text: str) -> "S2State":
        st = cls()
        try:
            d = json.loads(text)
            st.price_buf = d.get("pb", [])
            st.ou_theta = d.get("ot", 0.002)
            st.ou_mu = d.get("om", 0.0)
            st.ou_sigma = d.get("os", 1.1)
            st.ticks_since_recal = d.get("tr", 0)
            st.has_calibrated = d.get("hc", False)
            st.pred_errors = d.get("pe", [])
            st.tte_base_days = d.get("td", 8.0)
            st.ask_ema = d.get("ae")
            st.bid_ema = d.get("be")
            st.sigma_ask2 = d.get("sa2", SIGMA_PRICE_INIT ** 2)
            st.sigma_bid2 = d.get("sb2", SIGMA_PRICE_INIT ** 2)
            st.z_ema = d.get("ze", 0.0)
            st.z_var = d.get("zv", 1.0)

            st.smooth_target = d.get("st", 0.0)
            st.last_agg_ts = d.get("lat", -9999)
            st.prev_ci = d.get("pci", 0.0)
            st.last_heavy_ts = d.get("lht", -9999)
        except Exception:
            pass
        return st


def _micro(depth: OrderDepth) -> float | None:
    bids, asks = depth.buy_orders, depth.sell_orders
    if not bids or not asks:
        return None
    bb, ba = max(bids), min(asks)
    bv, av = abs(bids[bb]), abs(asks[ba])
    tot = bv + av
    return (bv * ba + av * bb) / tot if tot > 0 else (bb + ba) / 2.0


def _best(depth: OrderDepth) -> tuple[int | None, int | None]:
    bb = max(depth.buy_orders) if depth.buy_orders else None
    ba = min(depth.sell_orders) if depth.sell_orders else None
    return bb, ba


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ═══════════════════════════════════════════════════════════════════════════════
#  HYDROGEL_PACK constants & helpers  (from loutre)
# ═══════════════════════════════════════════════════════════════════════════════
HP_PRODUCT = "HYDROGEL_PACK"

HP_POS_LIMIT = 200
HP_BASE_SIZE = 12
HP_QUOTE_WIDTH_MULT = 2.2

HP_W = 0.2
HP_MICRO_BALANCE_TOL = 1.0

HP_KAPPA = 0.0017832392
HP_HORIZON = 15.0
HP_DT = 1.0

HP_MU_MIN_WINDOW = 25 * 100
HP_MU_FIXE = 9991.0012009026

HP_VAR_MIN_WINDOW = 1000
HP_VAR_FIXE = 1022.1842605233

HP_EPS = 1e-9

HP_ETA_INV = 0.6
HP_THETA_SIZE = 1.75

HP_GAMMA = 0.000050
HP_AS_K = 0.355792
HP_MIN_HALF_SPREAD = 1
HP_TAKER_EDGE = 0.5

HP_PHI_DT = math.exp(-HP_KAPPA * HP_DT)
HP_PHI_H = math.exp(-HP_KAPPA * HP_HORIZON)
HP_DENOM = max(1.0 - math.exp(-2.0 * HP_KAPPA * HP_DT), HP_EPS)
HP_OU_VAR_H_MULT = 1.0 - math.exp(-2.0 * HP_KAPPA * HP_HORIZON)
HP_AS_BASE_DELTA = (1.0 / HP_GAMMA) * math.log(1.0 + HP_GAMMA / HP_AS_K)


def _hp_micro_price_protected(depth: OrderDepth) -> float | None:
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
        if abs(diff[i]) <= HP_MICRO_BALANCE_TOL:
            mi.append(i)

    if mi == []:
        return None

    num = 0
    den = 0
    for i in range(len(mi) - 1, -1, -1):
        num += (difu[mi[i]][0][0] + difu[mi[i]][1][0]) * 0.5 * math.exp(-HP_W * (len(mi) - i))
        den += math.exp(-HP_W * (len(mi) - i))
    return num / den


def _hp_welford_step(x: float, n: int, mean: float, M2: float) -> tuple[int, float, float]:
    n_new = n + 1
    delta = x - mean
    mean_new = mean + delta / n_new
    delta2 = x - mean_new
    M2_new = M2 + delta * delta2
    return n_new, mean_new, M2_new


# ═══════════════════════════════════════════════════════════════════════════════
#  VE + VEV strategy  (from 476865 — logic unchanged)
# ═══════════════════════════════════════════════════════════════════════════════
def _run_ve(state: TradingState, ve_data: str) -> tuple[dict[str, list[Order]], str]:
    st = S2State.from_json(ve_data) if ve_data else S2State()
    ts = state.timestamp
    all_orders: dict[str, list[Order]] = {}

    ve_depth = state.order_depths.get(VE)
    if ve_depth is None:
        return all_orders, st.to_json()

    ve_micro = _micro(ve_depth)
    bb_ve, ba_ve = _best(ve_depth)
    if ve_micro is None or bb_ve is None or ba_ve is None:
        return all_orders, st.to_json()

    pos_ve = state.position.get(VE, 0)

    if st.ou_mu == 0.0:
        st.ou_mu = ve_micro

    st.price_buf.append(ve_micro)
    if len(st.price_buf) > OU_WINDOW + 500:
        st.price_buf = st.price_buf[-(OU_WINDOW + 500):]

    if st.has_calibrated and len(st.price_buf) >= 2:
        pred_err = st.price_buf[-1] - st.ou_mu
        st.pred_errors.append(pred_err)
        if len(st.pred_errors) > 200:
            st.pred_errors = st.pred_errors[-200:]

    st.ticks_since_recal += 1
    n_buf = len(st.price_buf)
    if n_buf >= OU_MIN_SAMPLES and st.ticks_since_recal >= OU_RECAL_EVERY:
        window = st.price_buf[-min(n_buf, OU_WINDOW):]
        theta_new, mu_new, sigma_new = fit_ou(window)
        if theta_new > 1e-6:
            st.ou_theta = theta_new
            st.ou_mu = mu_new
            st.ou_sigma = sigma_new
            st.ticks_since_recal = 0
            st.has_calibrated = True

    theta = st.ou_theta
    mu = st.ou_mu
    ou_sigma = max(0.3, st.ou_sigma)

    deviation = ve_micro - mu
    ou_std = ou_sigma / math.sqrt(2.0 * theta) if theta > 1e-8 else ou_sigma * 20
    z_raw = deviation / ou_std if ou_std > 0.1 else 0.0

    cum_innov = 0.0
    if n_buf >= CUM_INNOV_LOOKBACK:
        tail = st.price_buf[-CUM_INNOV_LOOKBACK:]
        innov_sum = sum(p - mu for p in tail)
        innov_std = 0.0
        innov_mean = innov_sum / CUM_INNOV_LOOKBACK
        for p in tail:
            d = (p - mu) - innov_mean
            innov_std += d * d
        innov_std = math.sqrt(innov_std / CUM_INNOV_LOOKBACK)
        if innov_std > 0.01:
            cum_innov = innov_sum / (innov_std * math.sqrt(CUM_INNOV_LOOKBACK))

    z_blend = (1.0 - CUM_INNOV_WEIGHT) * z_raw + CUM_INNOV_WEIGHT * cum_innov

    st.z_ema = Z_BAND_DECAY * st.z_ema + (1 - Z_BAND_DECAY) * z_raw
    z_dev = z_raw - st.z_ema
    st.z_var = Z_BAND_VAR_DECAY * st.z_var + (1 - Z_BAND_VAR_DECAY) * z_dev * z_dev
    z_std = math.sqrt(st.z_var)
    z_band_k = _clamp(Z_BAND_K_BASE * z_std, Z_BAND_K_MIN, Z_BAND_K_MAX)
    z_upper = st.z_ema + z_band_k
    z_lower = st.z_ema - z_band_k

    tte_years = max((st.tte_base_days - ts / TICKS_PER_DAY) / 365.0, 0.0001)

    # ── Inventory target — absolute z_raw tiers + EMA smoothing ──
    abs_z = abs(z_raw)
    if not st.has_calibrated or abs_z < Z_TARGET_DEAD:
        raw_target = 0.0
    else:
        frac = min(1.0, (abs_z - Z_TARGET_DEAD) / (Z_TARGET_FULL - Z_TARGET_DEAD))
        if z_raw > 0:
            frac = -frac
        raw_target = frac * VE_LIMIT

    if abs(cum_innov) > CI_SUPPRESS_Z:
        suppress = min(CI_SUPPRESS_MAX, (abs(cum_innov) - CI_SUPPRESS_Z) / 2.0)
        raw_target *= (1.0 - suppress)

    st.smooth_target = TARGET_DECAY * st.smooth_target + (1 - TARGET_DECAY) * raw_target
    target_pos = st.smooth_target

    # ── Heavy reversal entry — band breakout + CI reversal ──
    delta_ci = cum_innov - st.prev_ci
    st.prev_ci = cum_innov
    heavy_buy = False
    heavy_sell = False

    pre_delta = float(pos_ve)
    for sym_d, K_d in ALL_VEV.items():
        pre_delta += state.position.get(sym_d, 0) * _bs_delta(ve_micro, K_d, tte_years, SIGMA_IV)

    if st.has_calibrated and (ts - st.last_heavy_ts) >= HEAVY_COOLDOWN:
        if (z_raw < z_lower and delta_ci > HEAVY_CI_DELTA
                and pos_ve < HEAVY_MAX_POS and pre_delta < HEAVY_MAX_DELTA):
            heavy_buy = True
            st.last_heavy_ts = ts
        elif (z_raw > z_upper and delta_ci < -HEAVY_CI_DELTA
                and pos_ve > -HEAVY_MAX_POS and pre_delta > -HEAVY_MAX_DELTA):
            heavy_sell = True
            st.last_heavy_ts = ts

    heavy_ve_orders: list[Order] = []
    heavy_ve_filled = 0
    if heavy_buy:
        buy_cap = min(VE_LIMIT - pos_ve, HEAVY_VE_SIZE)
        for ask_px in sorted(ve_depth.sell_orders.keys()):
            avail = abs(ve_depth.sell_orders[ask_px])
            sz = min(buy_cap - heavy_ve_filled, avail)
            if sz > 0:
                heavy_ve_orders.append(Order(VE, ask_px, sz))
                heavy_ve_filled += sz
            if heavy_ve_filled >= buy_cap:
                break

    if heavy_sell:
        sell_cap = min(VE_LIMIT + pos_ve, HEAVY_VE_SIZE)
        for bid_px in sorted(ve_depth.buy_orders.keys(), reverse=True):
            avail = abs(ve_depth.buy_orders[bid_px])
            sz = min(sell_cap - heavy_ve_filled, avail)
            if sz > 0:
                heavy_ve_orders.append(Order(VE, bid_px, -sz))
                heavy_ve_filled += sz
            if heavy_ve_filled >= sell_cap:
                break

    # ── VE market-making — Avellaneda-Stoikov ──
    gamma = GAMMA_BASE
    overshoot = abs(pos_ve - target_pos) / VE_LIMIT
    if overshoot > 0.3:
        gamma *= 1.0 + 2.0 * (overshoot - 0.3)
    gamma = _clamp(gamma, GAMMA_MIN, GAMMA_MAX)

    sigma_tick = max(0.5, ou_sigma)
    tau = max(0.01, 1.0 - ts / TICKS_PER_DAY)
    q_deviation = pos_ve - target_pos
    reservation = ve_micro - q_deviation * gamma * sigma_tick * sigma_tick * tau

    kappa = 0.5
    as_half = (gamma * sigma_tick * sigma_tick * tau + (2.0 / gamma) * math.log(1.0 + gamma / kappa)) / 2.0
    half_spread = _clamp(as_half, VE_HALF_SPREAD_MIN, VE_HALF_SPREAD_MAX)

    fair_ve = reservation

    ve_orders: list[Order] = []
    ve_bid_quotes: list[int] = []
    ve_ask_quotes: list[int] = []

    # ── L1 spike tracking ──
    if st.ask_ema is None:
        st.ask_ema = float(ba_ve)
    if st.bid_ema is None:
        st.bid_ema = float(bb_ve)

    delta_ask = ba_ve - st.ask_ema
    delta_bid = bb_ve - st.bid_ema

    st.sigma_ask2 = LAM_PRICE_VAR * st.sigma_ask2 + (1 - LAM_PRICE_VAR) * delta_ask * delta_ask
    st.sigma_bid2 = LAM_PRICE_VAR * st.sigma_bid2 + (1 - LAM_PRICE_VAR) * delta_bid * delta_bid
    sigma_ask = max(0.5, math.sqrt(st.sigma_ask2))
    sigma_bid = max(0.5, math.sqrt(st.sigma_bid2))

    st.ask_ema = LAM_PRICE_EMA * st.ask_ema + (1 - LAM_PRICE_EMA) * ba_ve
    st.bid_ema = LAM_PRICE_EMA * st.bid_ema + (1 - LAM_PRICE_EMA) * bb_ve

    ask_drop = max(0.0, -delta_ask)
    bid_spike = max(0.0, delta_bid)
    z_ask_drop = ask_drop / sigma_ask if sigma_ask > 0.01 else 0.0
    z_bid_spike = bid_spike / sigma_bid if sigma_bid > 0.01 else 0.0

    # ── Spike-only aggressive entries ──
    agg_buy_ve = 0
    agg_sell_ve = 0
    gap = target_pos - pos_ve

    if z_ask_drop >= Z_PRICE_HEAVY and gap > 0:
        buy_cap = VE_LIMIT - pos_ve
        size = min(AGG_VE_SIZE_HEAVY, int(gap), buy_cap,
                   abs(ve_depth.sell_orders.get(ba_ve, 0)))
        if size > 0:
            ve_orders.append(Order(VE, ba_ve, size))
            agg_buy_ve = size

    if z_bid_spike >= Z_PRICE_HEAVY and gap < 0:
        sell_cap = VE_LIMIT + pos_ve
        size = min(AGG_VE_SIZE_HEAVY, int(-gap), sell_cap,
                   abs(ve_depth.buy_orders.get(bb_ve, 0)))
        if size > 0:
            ve_orders.append(Order(VE, bb_ve, -size))
            agg_sell_ve = size

    # ── Gap-based controlled crossing ──
    if abs(gap) > GAP_AGG_MIN and (ts - st.last_agg_ts) >= GAP_AGG_COOLDOWN:
        if gap > GAP_AGG_MIN and agg_buy_ve == 0:
            buy_cap = VE_LIMIT - pos_ve
            avail = abs(ve_depth.sell_orders.get(ba_ve, 0))
            size = min(GAP_AGG_SIZE, int(gap) - GAP_AGG_MIN, buy_cap, avail)
            if size > 0:
                ve_orders.append(Order(VE, ba_ve, size))
                agg_buy_ve += size
                st.last_agg_ts = ts
        elif gap < -GAP_AGG_MIN and agg_sell_ve == 0:
            sell_cap = VE_LIMIT + pos_ve
            avail = abs(ve_depth.buy_orders.get(bb_ve, 0))
            size = min(GAP_AGG_SIZE, int(-gap) - GAP_AGG_MIN, sell_cap, avail)
            if size > 0:
                ve_orders.append(Order(VE, bb_ve, -size))
                agg_sell_ve += size
                st.last_agg_ts = ts

    # ── Passive VE quotes ──
    buy_cap_base = VE_LIMIT - pos_ve - agg_buy_ve - (heavy_ve_filled if heavy_buy else 0)
    sell_cap_base = VE_LIMIT + pos_ve - agg_sell_ve - (heavy_ve_filled if heavy_sell else 0)

    bid_budget = max(0, int(gap) - agg_buy_ve) if gap > 5 else (10 * VE_LEVELS if abs(gap) <= 5 else 0)
    ask_budget = max(0, int(-gap) - agg_sell_ve) if gap < -5 else (10 * VE_LEVELS if abs(gap) <= 5 else 0)

    for lvl in range(VE_LEVELS):
        bid_px = ask_px = bid_sz = ask_sz = 0

        if gap > 5:
            improve = 2 if gap > 30 else 1
            bid_px = min(bb_ve + improve - lvl, ba_ve - 1)
            bid_sz = min(VE_SIZE_PER_LEVEL, bid_budget, buy_cap_base)
            bid_budget -= max(0, bid_sz)
        elif gap < -5:
            improve = 2 if gap < -30 else 1
            ask_px = max(ba_ve - improve + lvl, bb_ve + 1)
            ask_sz = min(VE_SIZE_PER_LEVEL, ask_budget, sell_cap_base)
            ask_budget -= max(0, ask_sz)
        else:
            offset = half_spread * (1.0 + lvl * 0.6)
            bid_px = int(round(fair_ve - offset))
            ask_px = int(round(fair_ve + offset))
            bid_px = min(bid_px, ba_ve - 1)
            ask_px = max(ask_px, bb_ve + 1)
            bid_sz = min(10, bid_budget, buy_cap_base) if gap >= 0 else 0
            ask_sz = min(10, ask_budget, sell_cap_base) if gap <= 0 else 0
            bid_budget -= max(0, bid_sz)
            ask_budget -= max(0, ask_sz)

        if bid_sz > 0 and bid_px > 0:
            ve_orders.append(Order(VE, bid_px, bid_sz))
            ve_bid_quotes.append(bid_px)
            buy_cap_base -= bid_sz
        if ask_sz > 0 and ask_px > 0:
            ve_orders.append(Order(VE, ask_px, -ask_sz))
            ve_ask_quotes.append(ask_px)
            sell_cap_base -= ask_sz

    all_orders[VE] = heavy_ve_orders + ve_orders

    # ── Options — BS edge + directional signal + aggressive delta ──
    S = ve_micro
    portfolio_delta = float(pos_ve)
    delta_gap = target_pos - portfolio_delta

    for symbol, K in ALL_VEV.items():
        opt_depth = state.order_depths.get(symbol)
        if opt_depth is None:
            continue
        bb_opt, ba_opt = _best(opt_depth)
        if bb_opt is None and ba_opt is None:
            continue

        pos_opt = state.position.get(symbol, 0)
        delta_k = _bs_delta(S, K, tte_years, SIGMA_IV)
        portfolio_delta += pos_opt * delta_k

        if bb_opt is not None and ba_opt is not None:
            opt_spread = ba_opt - bb_opt
        else:
            opt_spread = 999

        if opt_spread > OPT_SPREAD_MAX:
            continue

        opt_orders: list[Order] = []
        buy_cap_opt = VEV_LIMIT - pos_opt
        sell_cap_opt = VEV_LIMIT + pos_opt
        tight = opt_spread <= 3

        # Heavy reversal: cross spread on high-delta strikes only
        if heavy_buy and delta_k > 0.3 and ba_opt is not None and buy_cap_opt > 0:
            heavy_opt_cap = min(HEAVY_OPT_SIZE, buy_cap_opt)
            filled_opt = 0
            for ask_px_o in sorted(opt_depth.sell_orders.keys()):
                avail = abs(opt_depth.sell_orders[ask_px_o])
                sz = min(heavy_opt_cap - filled_opt, avail)
                if sz > 0:
                    opt_orders.append(Order(symbol, ask_px_o, sz))
                    filled_opt += sz
                    buy_cap_opt -= sz
                if filled_opt >= heavy_opt_cap:
                    break

        if heavy_sell and delta_k > 0.3 and bb_opt is not None and sell_cap_opt > 0:
            heavy_opt_cap = min(HEAVY_OPT_SIZE, sell_cap_opt)
            filled_opt = 0
            for bid_px_o in sorted(opt_depth.buy_orders.keys(), reverse=True):
                avail = abs(opt_depth.buy_orders[bid_px_o])
                sz = min(heavy_opt_cap - filled_opt, avail)
                if sz > 0:
                    opt_orders.append(Order(symbol, bid_px_o, -sz))
                    filled_opt += sz
                    sell_cap_opt -= sz
                if filled_opt >= heavy_opt_cap:
                    break

        want_buy = delta_gap > 0 and delta_k > 0.15
        want_sell = delta_gap < 0 and delta_k > 0.15

        if want_buy and buy_cap_opt > 0 and bb_opt is not None:
            buy_px = bb_opt
            if tight:
                buy_px = bb_opt + 1
            buy_px = min(buy_px, ba_opt - 1) if ba_opt is not None else buy_px
            sz = min(OPT_SIZE_BASE, buy_cap_opt)
            if buy_px > 0 and sz > 0:
                opt_orders.append(Order(symbol, buy_px, sz))

        if want_sell and sell_cap_opt > 0 and ba_opt is not None:
            sell_px = ba_opt
            if tight:
                sell_px = ba_opt - 1
            sell_px = max(sell_px, bb_opt + 1) if bb_opt is not None else sell_px
            sz = min(OPT_SIZE_BASE, sell_cap_opt)
            if sell_px > 0 and sz > 0:
                opt_orders.append(Order(symbol, sell_px, -sz))

        if z_ask_drop >= Z_PRICE_LIGHT and want_buy and ba_opt is not None and buy_cap_opt > 0:
            sz = min(AGG_OPT_SIZE, buy_cap_opt)
            opt_orders.append(Order(symbol, ba_opt, sz))
            delta_gap -= sz * delta_k

        if z_bid_spike >= Z_PRICE_LIGHT and want_sell and bb_opt is not None and sell_cap_opt > 0:
            sz = min(AGG_OPT_SIZE, sell_cap_opt)
            opt_orders.append(Order(symbol, bb_opt, -sz))
            delta_gap += sz * delta_k

        if opt_orders:
            all_orders[symbol] = opt_orders

    portfolio_delta = float(pos_ve)
    for symbol, K in ALL_VEV.items():
        pos_opt = state.position.get(symbol, 0)
        delta_k = _bs_delta(S, K, tte_years, SIGMA_IV)
        portfolio_delta += pos_opt * delta_k

    print(
        f"t={ts} "
        f"L={fair_ve:.1f} "
        f"mu={mu:.1f} "
        f"z={z_raw:+.2f} "
        f"ci={cum_innov:+.2f} "
        f"conf=1.00 "
        f"mr={-z_blend:+.2f} "
        f"target={target_pos:+.0f} "
        f"pos={pos_ve:+d} "
        f"gamma={gamma:.4f} "
        f"hs={half_spread:.1f} "
        f"delta={portfolio_delta:+.1f} "
        f"zu={z_upper:+.2f} "
        f"zl={z_lower:+.2f} "
        f"zad={z_ask_drop:.1f} "
        f"zbs={z_bid_spike:.1f} "
        f"gap={gap:+.0f} "
        f"ab={agg_buy_ve} as={agg_sell_ve} "
        f"b=[{','.join(str(p) for p in ve_bid_quotes)}] "
        f"a=[{','.join(str(p) for p in ve_ask_quotes)}]"
    )

    return all_orders, st.to_json()


# ═══════════════════════════════════════════════════════════════════════════════
#  HYDROGEL_PACK strategy  (from loutre — logic unchanged)
# ═══════════════════════════════════════════════════════════════════════════════
def _run_hp(state: TradingState, hp_st: dict) -> tuple[dict[str, list[Order]], dict]:
    pos = state.position.get(HP_PRODUCT, 0)
    depth = state.order_depths.get(HP_PRODUCT)
    orders: list[Order] = []
    st = hp_st

    if not depth or not depth.buy_orders or not depth.sell_orders:
        buy_qty = max(0, min(HP_POS_LIMIT, HP_POS_LIMIT - pos))
        sell_qty = max(0, min(HP_POS_LIMIT, HP_POS_LIMIT + pos))

        if buy_qty > 0:
            orders.append(Order(HP_PRODUCT, 1, buy_qty))

        if sell_qty > 0:
            orders.append(Order(HP_PRODUCT, 10**12, -sell_qty))

        return {HP_PRODUCT: orders}, st

    b_bid = max(depth.buy_orders)
    b_ask = min(depth.sell_orders)

    bid_vol = depth.buy_orders[b_bid]
    ask_vol = -depth.sell_orders[b_ask]

    spread = b_ask - b_bid
    mid = (b_bid + b_ask) / 2.0

    micro = _hp_micro_price_protected(depth)

    if micro is None:
        prev_micro = st.get("prev_micro", None)

        if prev_micro is None:
            micro = mid
        else:
            micro = float(prev_micro)

    micro_mean = st.get("micro_mean", -1)
    micro_counter = st.get("micro_counter", 0)

    if micro_mean == -1:
        micro_mean = HP_MU_FIXE
        micro_counter = HP_MU_MIN_WINDOW

    micro_counter, micro_mean, _ = _hp_welford_step(
        float(micro),
        int(micro_counter),
        float(micro_mean),
        0.0,
    )

    mu = micro_mean

    eps_mean = float(st.get("eps_mean", 0.0))
    eps_counter = int(st.get("eps_counter", 0))
    eps_M2 = float(st.get("eps_M2", 0.0))

    prev_micro = st.get("prev_micro", None)

    if prev_micro is not None:
        prev_micro = float(prev_micro)

        expected_micro = mu + HP_PHI_DT * (prev_micro - mu)
        eps_ou = micro - expected_micro

        eps_counter, eps_mean, eps_M2 = _hp_welford_step(
            float(eps_ou),
            eps_counter,
            eps_mean,
            eps_M2,
        )

    if eps_counter > 1:
        var_eps_raw = max(eps_M2 / (eps_counter - 1), HP_EPS)
    else:
        var_eps_raw = max(HP_VAR_FIXE * HP_DENOM, HP_EPS)

    w_var = min(1.0, eps_counter / HP_VAR_MIN_WINDOW)

    var_eps = (1.0 - w_var) * (HP_VAR_FIXE * HP_DENOM) + w_var * var_eps_raw

    var_inf = var_eps / HP_DENOM
    sigma_inf = math.sqrt(max(var_inf, HP_EPS))

    fair = mu + HP_PHI_H * (micro - mu)

    z = (micro - mu) / sigma_inf

    q_star = -HP_POS_LIMIT * math.tanh(HP_ETA_INV * z)

    var_h = var_inf * HP_OU_VAR_H_MULT

    planned_pos = pos

    buy_capacity = HP_POS_LIMIT - planned_pos
    sell_capacity = HP_POS_LIMIT + planned_pos

    if fair > b_ask + HP_TAKER_EDGE and planned_pos < q_star and buy_capacity > 0:
        desired_buy = int(math.floor(q_star - planned_pos))

        qty = min(
            desired_buy,
            buy_capacity,
            ask_vol,
        )

        if qty > 0:
            orders.append(Order(HP_PRODUCT, b_ask, qty))
            planned_pos += qty

    buy_capacity = HP_POS_LIMIT - planned_pos
    sell_capacity = HP_POS_LIMIT + planned_pos

    if fair < b_bid - HP_TAKER_EDGE and planned_pos > q_star and sell_capacity > 0:
        desired_sell = int(math.floor(planned_pos - q_star))

        qty = min(
            desired_sell,
            sell_capacity,
            bid_vol,
        )

        if qty > 0:
            orders.append(Order(HP_PRODUCT, b_bid, -qty))
            planned_pos -= qty

    reservation = fair - HP_GAMMA * var_h * (planned_pos - q_star)

    theoretical_delta = HP_AS_BASE_DELTA + 0.5 * HP_GAMMA * var_h
    theoretical_delta *= HP_QUOTE_WIDTH_MULT

    half_spread = max(HP_MIN_HALF_SPREAD, int(math.ceil(theoretical_delta)))

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
    normalized_gap = inv_gap / HP_POS_LIMIT

    bid_size_float = HP_BASE_SIZE * max(
        0.0,
        1.0 + HP_THETA_SIZE * normalized_gap,
    )

    ask_size_float = HP_BASE_SIZE * max(
        0.0,
        1.0 - HP_THETA_SIZE * normalized_gap,
    )

    bid_size = int(round(bid_size_float))
    ask_size = int(round(ask_size_float))

    buy_capacity = HP_POS_LIMIT - planned_pos
    sell_capacity = HP_POS_LIMIT + planned_pos

    buy_qty = max(0, min(bid_size, buy_capacity))
    sell_qty = max(0, min(ask_size, sell_capacity))

    if buy_qty > 0:
        orders.append(Order(HP_PRODUCT, maker_bid, buy_qty))

    if sell_qty > 0:
        orders.append(Order(HP_PRODUCT, maker_ask, -sell_qty))

    new_state = {
        "micro_mean": micro_mean,
        "micro_counter": micro_counter,
        "eps_mean": eps_mean,
        "eps_counter": eps_counter,
        "eps_M2": eps_M2,
        "prev_micro": micro,
    }

    return {HP_PRODUCT: orders}, new_state


# ═══════════════════════════════════════════════════════════════════════════════
#  Unified Trader
# ═══════════════════════════════════════════════════════════════════════════════
class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        combined = json.loads(state.traderData) if state.traderData else {}
        ve_data = combined.get("ve", "")
        hp_data = combined.get("hp", {})

        ve_orders, ve_state = _run_ve(state, ve_data)
        hp_orders, hp_state = _run_hp(state, hp_data)

        all_orders: dict[str, list[Order]] = {}
        all_orders.update(ve_orders)
        all_orders.update(hp_orders)

        return all_orders, 0, json.dumps({"ve": ve_state, "hp": hp_state})