from __future__ import annotations

import csv
import io
import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]


# ============================================================
# Collez ici votre CSV de paramètres.
# Les colonnes pnl, sharpe, drawdown, etc. peuvent rester :
# elles seront ignorées par le parser.
# ============================================================

PARAMS_CSV = """
product,pnl,sharpe,drawdown,max_inv,taker_qty,maker_qty,BASE_SIZE,QUOTE_WIDTH_MULT,W,MICRO_BALANCE_TOL,KAPPA,HORIZON,DT,MU_PRICE_FIXE,VAR_PRICE_FIXE,OLS_WINDOW,OLS_MIN_WINDOW,VAR_WINDOW,VAR_MIN_WINDOW,TREND_LAMBDA,ETA_INV,THETA_SIZE,GAMMA,AS_K,MIN_TICK_SPREAD,TAKER_EDGE_TICKS,EPS,POS_LIMIT
GALAXY_SOUNDS_BLACK_HOLES,20399.5,1.4802842350377374,7614.0,9,6,9,5,2.0,0.2,30.0,0.0005,10.0,1.0,11466.872083333334,39446.7466126588,80,40,25,10,0.25,16.0,5.0,0.0005,1553.4999463576585,1,8.0,1e-12,10
GALAXY_SOUNDS_DARK_MATTER,16858.0,1.7059801091199551,4478.0,9,362,2,1,2.0,0.05,7.0,0.0005,15.0,1.0,10226.661816666669,3137.538357374039,2000,40,50,40,0.25,2.0,1.0,0.0005,1548.4230231047422,1,8.0,1e-12,10
GALAXY_SOUNDS_PLANETARY_RINGS,30132.5,2.5358086556555475,10664.5,9,38,3,5,2.0,0.5,7.0,0.0002,5.0,1.0,10766.673183333334,115.92125143670914,1250,40,100,5,1.0,16.0,3.0,0.0005,1551.3666129505052,1,20.0,1e-12,10
GALAXY_SOUNDS_SOLAR_FLAMES,28824.0,2.433418045883244,8814.5,9,433,4,10,2.0,0.1,7.0,0.0005,5.0,1.0,11092.5717,123.04514691964089,1250,40,500,5,0.0,4.0,8.0,0.0005,1550.0713748103667,1,8.0,1e-12,10
GALAXY_SOUNDS_SOLAR_WINDS,27810.0,2.731537351027828,5971.0,9,342,12,2,1.0,0.5,3.0,0.0001000050003333,2.0,1.0,10437.543966666666,10894.232405609973,500,40,10,10,0.0,16.0,3.0,0.0005,1545.92851752336,1,12.0,1e-12,10
MICROCHIP_CIRCLE,26103.5,1.989078963089506,7628.0,9,20,7,8,5.0,0.2,1.0,0.0002,15.0,1.0,9214.885283333333,2547.4233235497973,1250,40,50,80,1.0,2.0,0.5,0.0005,2220.49996247039,1,30.0,1e-12,10
MICROCHIP_OVAL,14026.0,2.0527322074575927,3090.5,8,5,17,8,1.0,0.3,15.0,0.0001000050003333,1.0,1.0,8179.598716666666,2007.1750549708493,500,40,10,5,0.75,2.0,3.0,0.0005,2176.8332950514236,1,12.0,1e-12,10
MICROCHIP_RECTANGLE,14703.0,1.2980062599164606,6233.0,9,310,60,3,1.0,0.2,7.0,0.0005,5.0,1.0,8732.43935,228.7664910042853,250,40,10,40,0.0,2.0,2.0,0.0005,2207.214247959505,1,30.0,1e-12,10
MICROCHIP_SQUARE,59816.0,2.624540070445012,11219.5,9,179,2,1,1.0,0.3,3.0,0.0002,2.0,1.0,13594.7483,18481.718134035287,2000,40,10,20,0.25,12.0,0.5,0.0005,2287.0384251015553,1,5.0,1e-12,10
MICROCHIP_TRIANGLE,18878.5,1.5961704511559724,6955.0,9,214,9,1,5.0,0.05,3.0,0.001,15.0,1.0,9686.391083333334,93.82617221927952,750,40,500,10,0.25,16.0,8.0,0.0005,2234.83329604495,1,30.0,1e-12,10
OXYGEN_SHAKE_CHOCOLATE,15841.0,1.0362460105242566,8235.0,9,21,1,8,1.0,0.3,15.0,0.0002,1.0,1.0,9556.879133333334,913.339387691421,750,40,25,80,0.75,32.0,2.0,0.0005,1543.3460998506719,1,2.0,1e-12,10
OXYGEN_SHAKE_EVENING_BREATH,21587.0,1.8727960019024565,10706.0,9,1381,5,8,2.0,0.1,3.0,0.0001000050003333,2.0,1.0,9271.895,859.6803689102501,250,40,100,10,0.75,32.0,1.0,0.0005,1545.4999460797692,1,1.0,1e-12,10
OXYGEN_SHAKE_GARLIC,33617.0,2.395613183895542,8887.5,9,491,3,8,2.0,0.2,7.0,0.001,5.0,1.0,11925.639766666667,1422.2088384430142,1250,40,250,80,1.0,4.0,1.0,0.0005,1556.0881817407667,1,8.0,1e-12,10
OXYGEN_SHAKE_MINT,31681.0,2.6379569341031037,9140.5,9,1467,4,8,2.0,0.05,3.0,0.001,5.0,1.0,9838.394083333333,9679.399813896833,120,40,100,10,0.0,24.0,1.0,0.0005,1538.8845612330636,1,0.5,1e-12,10
OXYGEN_SHAKE_MORNING_BREATH,35229.5,3.560325567829469,4682.5,9,218,7,2,1.0,0.05,7.0,0.0005,5.0,1.0,10000.45335,10000.906720552623,250,40,100,10,0.0,16.0,0.5,0.0005,1547.6428032973856,1,12.0,1e-12,10
PANEL_1X2,10563.0,1.8350586578058379,3052.0,9,917,188,1,1.0,0.1,1.0,0.0002,15.0,1.0,8922.729016666666,796.150931048653,250,40,250,40,0.25,4.0,1.0,0.0005,1520.9999452113789,1,1.0,1e-12,10
PANEL_1X4,16722.5,2.5612478268148555,4648.5,9,339,374,10,2.0,0.5,1.0,0.0001000050003333,15.0,1.0,9397.580616666666,2649.435643402471,120,40,25,3,1.0,2.0,2.0,0.0005,2199.749962116837,1,20.0,1e-12,10
PANEL_2X2,16809.0,1.181480516796266,8675.5,9,84,1,1,2.0,0.3,30.0,0.0002,5.0,1.0,9576.598433333333,9171.123755332244,500,40,10,80,0.5,4.0,3.0,0.0005,2203.249962177375,1,0.5,1e-12,10
PANEL_2X4,18665.5,1.0644580630504703,11367.0,9,8,1,8,2.0,0.3,15.0,5e-05,5.0,1.0,11265.372983333333,1269.0862845361657,2000,40,50,80,1.0,12.0,1.0,0.0005,2256.499963069682,1,1.0,1e-12,10
PANEL_4X4,16305.5,1.1892843857732138,9669.0,9,490,3,8,5.0,0.3,1.0,0.0005,15.0,1.0,9878.719266666669,29276.728304883363,2000,40,100,3,1.0,8.0,3.0,0.0005,2229.2777403968676,1,12.0,1e-12,10
PEBBLES_L,26737.0,1.2895101119325019,13352.0,9,87,7,8,2.0,0.5,30.0,0.0001000050003333,10.0,1.0,10174.110583333331,1035.1252616189536,1250,40,500,20,0.5,4.0,1.0,0.0005,1549.8076385376148,1,0.5,1e-12,10
PEBBLES_M,15930.0,1.4071094618297868,6075.0,6,47,8,8,1.0,0.05,1.0,5e-05,1.0,1.0,10263.243183333334,3160.024819207144,80,40,10,5,0.0,24.0,5.0,0.0005,1548.3012275652295,1,30.0,1e-12,10
PEBBLES_S,16433.5,1.0455286035946127,12060.5,9,92,11,2,2.0,0.05,3.0,0.0002,1.0,1.0,8932.356733333334,23936.0990434576,120,40,50,80,0.75,32.0,0.5,0.0005,1527.1666120995224,1,30.0,1e-12,10
PEBBLES_XL,62415.0,1.9527800065319545,17186.0,9,50,1,5,2.0,0.5,7.0,0.0005,5.0,1.0,13225.589316666666,5247.486383193825,80,40,500,20,0.0,32.0,1.0,0.0005,1571.1922546541866,1,50.0,1e-12,10
PEBBLES_XS,39558.0,2.076259471321345,8446.5,9,66,1,2,2.0,0.5,30.0,0.001,5.0,1.0,7404.639766666666,5482.869007410138,2000,40,25,80,0.75,4.0,2.0,0.0005,1497.309035198423,1,3.0,1e-12,10
ROBOT_DISHES,9113.0,1.19194643511156,3709.0,6,175,87,5,2.0,0.3,30.0,0.0001000050003333,5.0,1.0,10018.3149,1003.66633435562,80,40,500,3,0.5,2.0,3.0,0.0005,2682.07139750093,1,2.0,1e-12,10
ROBOT_IRONING,15448.0,1.1348152189696867,9198.0,9,75,6,8,1.0,0.2,7.0,0.001,1.0,1.0,8701.570266666668,757.1732510573743,250,40,50,40,0.25,48.0,0.0,0.0005,2683.833302283325,1,12.0,1e-12,10
ROBOT_LAUNDRY,17506.5,1.3233502754513835,6597.0,9,38,1,10,1.0,0.3,15.0,0.001,1.0,1.0,9822.7617,9648.664741498687,80,40,500,10,0.25,96.0,1.0,0.0005,2642.071397030428,1,5.0,1e-12,10
ROBOT_MOPPING,24041.5,1.4304469702296154,14323.5,9,885,0,0,0.2,0.5,15.0,0.0005,15.0,1.0,11100.213233333334,36964.420147640536,80,40,10,20,0.5,24.0,0.5,0.0005,2702.249969160923,1,12.0,1e-12,10
ROBOT_VACUUMING,8460.0,1.0915330058754096,8545.5,9,282,35,10,5.0,0.3,3.0,0.0005,2.0,1.0,9166.775783333333,25208.93347857193,80,40,50,20,0.75,8.0,5.0,0.0005,2731.214255202541,1,30.0,1e-12,10
SLEEP_POD_COTTON,23969.0,1.975793986752893,6026.0,9,487,90,3,5.0,0.5,7.0,0.0001000050003333,15.0,1.0,11527.613966666666,1328.8588376448838,80,40,25,3,1.0,8.0,3.0,0.0005,2258.833296441389,1,30.0,1e-12,10
SLEEP_POD_LAMB_WOOL,22461.0,1.8410923254763571,6911.5,9,89,5,8,2.0,0.2,1.0,5e-05,5.0,1.0,10701.441716666666,11452.08548152136,500,40,250,5,0.25,16.0,8.0,0.0005,2248.8999629453187,1,20.0,1e-12,10
SLEEP_POD_NYLON,14483.0,1.3347169901409337,5656.0,9,14,2,10,5.0,0.3,7.0,0.0002,2.0,1.0,9636.472566666667,9286.160352811927,120,40,10,20,0.5,8.0,1.0,0.0005,2207.0555177974957,1,30.0,1e-12,10
SLEEP_POD_POLYESTER,20558.0,1.9553357775391926,6262.5,9,759,1,2,5.0,0.05,1.0,0.0005,10.0,1.0,11840.56095,14019.888361066487,750,40,25,40,1.0,2.0,3.0,0.0005,2271.277741087989,1,5.0,1e-12,10
SLEEP_POD_SUEDE,27351.0,1.8098179016343456,7407.0,9,29,3,8,2.0,0.2,7.0,5e-05,5.0,1.0,11397.420433333333,12990.119253416418,2000,40,100,20,0.0,32.0,0.5,0.0005,2242.699962842153,1,20.0,1e-12,10
SNACKPACK_CHOCOLATE,4657.0,2.002679510081547,1249.0,5,270,836,5,0.01,0.1,7.0,5e-05,15.0,1.0,9843.37165,29067.589632007108,80,40,50,5,0.25,1.0,5.0,0.0005,1176.2058115037323,1,0.5,1e-12,10
SNACKPACK_PISTACHIO,4985.0,1.548246759354511,1351.0,9,39,651,2,0.01,0.05,30.0,0.001,5.0,1.0,9495.843916666669,901.7105168969534,120,40,100,3,1.0,2.0,2.0,0.0005,1177.3749292212115,1,3.0,1e-12,10
SNACKPACK_RASPBERRY,13530.0,3.1439120613910667,2489.0,8,417,567,2,0.1,0.2,3.0,0.0002,10.0,1.0,10077.812066666667,101.56229605105229,80,40,500,10,0.0,8.0,8.0,0.0005,1178.441105755622,1,5.0,1e-12,10
SNACKPACK_STRAWBERRY,10098.0,1.847286590299688,2706.0,9,188,470,1,0.01,0.05,30.0,0.0001000050003333,5.0,1.0,10706.6085,1146.3146557227226,120,40,50,20,1.0,12.0,5.0,0.0005,1184.1665962937006,1,3.0,1e-12,10
SNACKPACK_VANILLA,6913.0,2.5019461016902786,1443.5,6,382,866,10,0.35,0.2,3.0,5e-05,10.0,1.0,10097.302466666666,1019.5551710335276,120,40,50,10,0.25,1.0,3.0,0.0005,1179.2646352168958,1,1.0,1e-12,10
TRANSLATOR_ASTRO_BLACK,13898.0,1.1649646612057973,7371.0,9,106,2,3,5.0,0.1,15.0,0.001,5.0,1.0,9385.219166666666,880.8233880636735,120,40,250,5,0.25,96.0,0.5,0.0005,2212.3888512222006,1,20.0,1e-12,10
TRANSLATOR_ECLIPSE_CHARCOAL,14879.5,1.4754630499763015,6273.5,9,709,2,1,5.0,0.1,3.0,0.0002,10.0,1.0,9813.741883333334,9630.95297526909,120,40,25,80,0.0,16.0,0.0,0.0005,2216.833295742152,1,12.0,1e-12,10
TRANSLATOR_GRAPHITE_MIST,22374.5,2.1884240744370924,6258.0,9,470,7,10,2.0,0.1,7.0,0.001,2.0,1.0,10084.639683333333,101.69995754266142,750,40,25,10,0.25,2.0,1.0,0.0005,2219.2777402275383,1,5.0,1e-12,10
TRANSLATOR_SPACE_GRAY,12741.0,1.058541914487209,7038.0,9,462,12,5,5.0,0.1,7.0,5e-05,5.0,1.0,9431.901883333334,8896.07731368269,120,40,10,10,1.0,96.0,0.0,0.0005,2216.388851290168,1,20.0,1e-12,10
TRANSLATOR_VOID_BLUE,16188.0,1.927943901711428,4786.5,8,15,666,8,0.1,0.2,3.0,5e-05,15.0,1.0,10858.579333333333,11790.874513829378,120,40,25,80,0.5,1.0,2.0,0.0005,2245.0555184369873,1,30.0,1e-12,10
UV_VISOR_AMBER,28886.0,2.6685376693969984,4707.0,9,25,6,5,1.0,0.3,15.0,0.0005,2.0,1.0,7911.69625,625.9493755226407,1250,40,100,20,0.5,32.0,1.0,0.0005,1516.8332783944766,1,2.0,1e-12,10
UV_VISOR_MAGENTA,15039.0,1.1072930189455488,7702.5,9,428,6,3,2.0,0.5,3.0,0.0001000050003333,1.0,1.0,11111.7929,37041.58243574712,500,40,10,40,1.0,32.0,0.0,0.0005,1549.9285176627923,1,12.0,1e-12,10
UV_VISOR_ORANGE,10707.0,2.513405448307811,3269.0,6,6,4,2,2.0,0.05,3.0,0.001,1.0,1.0,10426.506216666668,10871.203188618865,1250,40,500,5,0.5,48.0,0.0,0.0005,1549.0384077414076,1,30.0,1e-12,10
UV_VISOR_RED,12273.5,1.1094624398164548,9648.0,9,74,21,8,1.0,0.1,1.0,0.0002,10.0,1.0,11063.293583333334,3671.8939473307355,1250,40,50,20,0.0,8.0,3.0,0.0005,1553.349946343768,1,20.0,1e-12,10
UV_VISOR_YELLOW,19620.0,1.6827126509034633,8259.5,9,620,3,1,2.0,0.3,3.0,0.001,1.0,1.0,10957.46075,1200.6594608779058,120,40,10,20,0.5,8.0,5.0,0.0005,1542.7307152137446,1,8.0,1e-12,10
""".strip()


# ============================================================
# Parser CSV
# ============================================================

DEFAULTS = {
    "POS_LIMIT": 10.0,
    "BASE_SIZE": 1.0,
    "QUOTE_WIDTH_MULT": 1.0,

    "W": 0.1,
    "MICRO_BALANCE_TOL": 7.0,

    "KAPPA": 0.00010000500033334732,
    "HORIZON": 5.0,
    "DT": 1.0,

    "EPS": 1e-12,

    "MU_PRICE_FIXE": 10000.0,
    "VAR_PRICE_FIXE": 1000.0,

    "OLS_WINDOW": 250.0,
    "OLS_MIN_WINDOW": 40.0,

    "VAR_WINDOW": 100.0,
    "VAR_MIN_WINDOW": 10.0,

    "TREND_LAMBDA": 0.25,

    "ETA_INV": 16.0,
    "THETA_SIZE": 3.0,

    "GAMMA": 0.0005,
    "AS_K": 1500.0,
    "MIN_TICK_SPREAD": 1.0,
    "TAKER_EDGE_TICKS": 1.0,
}


INT_FIELDS = {
    "POS_LIMIT",
    "BASE_SIZE",
    "OLS_WINDOW",
    "OLS_MIN_WINDOW",
    "VAR_WINDOW",
    "VAR_MIN_WINDOW",
    "MIN_TICK_SPREAD",
}


def parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return float(value)


def load_params_from_csv(csv_text: str) -> dict[str, dict[str, float | int]]:
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    out: dict[str, dict[str, float | int]] = {}

    for row in reader:
        product = str(row.get("product", "")).strip()

        if product == "":
            continue

        cfg: dict[str, float | int] = {}

        for key, default in DEFAULTS.items():
            value = parse_float(row.get(key), default)

            if key in INT_FIELDS:
                cfg[key] = int(round(value))
            else:
                cfg[key] = float(value)

        out[product] = cfg

    return out


PRODUCT_PARAMS = load_params_from_csv(PARAMS_CSV)


# ============================================================
# Utility functions
# ============================================================

def clamp_list(xs: list[float], max_len: int) -> list[float]:
    if len(xs) > max_len:
        return xs[-max_len:]
    return xs


def micro_price_protected(
    depth: OrderDepth,
    w: float,
    micro_balance_tol: float,
    eps: float,
) -> float | None:
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
        if abs(diff[i]) <= micro_balance_tol:
            mi.append(i)

    if mi == []:
        return None

    num = 0.0
    den = 0.0

    for i in range(len(mi) - 1, -1, -1):
        weight = math.exp(-w * (len(mi) - i))
        num += (difu[mi[i]][0][0] + difu[mi[i]][1][0]) * 0.5 * weight
        den += weight

    return num / max(den, eps)


def rolling_ols_log(
    xs: list[float],
    horizon: float,
    trend_lambda: float,
    ols_min_window: int,
    mu_log_fixe: float,
    eps: float,
) -> tuple[float, float, float, float]:
    n = len(xs)

    if n < ols_min_window:
        mu_0 = xs[-1] if n > 0 else mu_log_fixe
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

    beta = sxy / max(sxx, eps)
    alpha = y_mean - beta * x_mean

    current_x = n - 1

    mu_0_raw = alpha + beta * current_x
    mu_h_raw = alpha + beta * (current_x + horizon)

    mu_0 = mu_0_raw
    mu_h = mu_0_raw + trend_lambda * (mu_h_raw - mu_0_raw)

    r2 = (sxy * sxy) / max(sxx * syy, eps)

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


def load_state(raw: str) -> dict:
    if not raw:
        return {}

    try:
        data = json.loads(raw)

        if isinstance(data, dict):
            return data

        return {}
    except Exception:
        return {}


# ============================================================
# Trading logic for one product
# ============================================================

def run_one_product(
    product: str,
    depth: OrderDepth,
    pos: int,
    st: dict,
    cfg: dict[str, float | int],
) -> tuple[list[Order], dict]:
    orders: list[Order] = []

    pos_limit = int(cfg["POS_LIMIT"])
    base_size = int(cfg["BASE_SIZE"])
    quote_width_mult = float(cfg["QUOTE_WIDTH_MULT"])

    w = float(cfg["W"])
    micro_balance_tol = float(cfg["MICRO_BALANCE_TOL"])

    kappa = float(cfg["KAPPA"])
    horizon = float(cfg["HORIZON"])
    dt = float(cfg["DT"])
    eps = float(cfg["EPS"])

    mu_price_fixe = float(cfg["MU_PRICE_FIXE"])
    mu_log_fixe = math.log(max(mu_price_fixe, eps))

    var_price_fixe = float(cfg["VAR_PRICE_FIXE"])
    var_log_fixe = var_price_fixe / max(mu_price_fixe * mu_price_fixe, eps)

    ols_window = int(cfg["OLS_WINDOW"])
    ols_min_window = int(cfg["OLS_MIN_WINDOW"])

    var_window = int(cfg["VAR_WINDOW"])
    var_min_window = int(cfg["VAR_MIN_WINDOW"])

    trend_lambda = float(cfg["TREND_LAMBDA"])

    eta_inv = float(cfg["ETA_INV"])
    theta_size = float(cfg["THETA_SIZE"])

    gamma = float(cfg["GAMMA"])
    as_k = float(cfg["AS_K"])
    min_tick_spread = int(cfg["MIN_TICK_SPREAD"])
    taker_edge_ticks = float(cfg["TAKER_EDGE_TICKS"])

    phi_dt = math.exp(-kappa * dt)
    phi_h = math.exp(-kappa * horizon)

    denom = max(1.0 - math.exp(-2.0 * kappa * dt), eps)
    ou_var_h_mult = 1.0 - math.exp(-2.0 * kappa * horizon)

    as_base_delta_log = (1.0 / gamma) * math.log(1.0 + gamma / as_k)

    if not depth or not depth.buy_orders or not depth.sell_orders:
        return orders, st

    # =========================
    # 1. Best bid / best ask
    # =========================
    b_bid = max(depth.buy_orders)
    b_ask = min(depth.sell_orders)

    bid_vol = int(depth.buy_orders[b_bid])
    ask_vol = int(-depth.sell_orders[b_ask])

    spread = b_ask - b_bid
    mid = (b_bid + b_ask) / 2.0

    # =========================
    # 2. Microprice protected
    # =========================
    micro = micro_price_protected(
        depth=depth,
        w=w,
        micro_balance_tol=micro_balance_tol,
        eps=eps,
    )

    if micro is None:
        prev_micro = st.get("prev_micro", None)
        micro = mid if prev_micro is None else float(prev_micro)

    micro = max(float(micro), eps)
    x = math.log(micro)

    # =========================
    # 3. Rolling log-microprice history
    # =========================
    x_hist = [float(v) for v in st.get("x_hist", [])]
    x_hist.append(x)
    x_hist = clamp_list(x_hist, ols_window)

    # =========================
    # 4. Dynamic OLS mean in log-price
    # =========================
    mu_0, mu_h, trend_beta, trend_r2 = rolling_ols_log(
        xs=x_hist,
        horizon=horizon,
        trend_lambda=trend_lambda,
        ols_min_window=ols_min_window,
        mu_log_fixe=mu_log_fixe,
        eps=eps,
    )

    # =========================
    # 5. Dynamic OU residuals in log-price
    # =========================
    eps_hist = [float(v) for v in st.get("eps_hist", [])]

    prev_x = st.get("prev_x", None)
    prev_mu_0 = st.get("prev_mu_0", None)
    prev_mu_1 = st.get("prev_mu_1", None)

    if prev_x is not None and prev_mu_0 is not None and prev_mu_1 is not None:
        prev_x = float(prev_x)
        prev_mu_0 = float(prev_mu_0)
        prev_mu_1 = float(prev_mu_1)

        expected_x = prev_mu_1 + phi_dt * (prev_x - prev_mu_0)
        eps_ou = x - expected_x

        eps_hist.append(float(eps_ou))
        eps_hist = clamp_list(eps_hist, var_window)

    var_eps_raw = rolling_sample_variance(eps_hist)

    if var_eps_raw is None:
        var_eps_raw = var_log_fixe * denom

    w_var = min(1.0, len(eps_hist) / var_min_window)

    var_eps = (1.0 - w_var) * (var_log_fixe * denom) + w_var * max(var_eps_raw, eps)

    var_inf = var_eps / denom
    sigma_inf = math.sqrt(max(var_inf, eps))

    # =========================
    # 6. Fair price OU in log-price
    # =========================
    fair_log = mu_h + phi_h * (x - mu_0)
    fair = math.exp(fair_log)

    # =========================
    # 7. Target inventory
    # =========================
    z = (x - mu_0) / sigma_inf
    q_star = -pos_limit * math.tanh(eta_inv * z)

    # =========================
    # 8. OU conditional variance at horizon
    # =========================
    var_h = var_inf * ou_var_h_mult

    # =========================
    # 9. Taker orders
    # Takers stay at BBO:
    # buy at best ask, sell at best bid.
    # =========================
    planned_pos = pos

    buy_capacity = pos_limit - planned_pos

    if fair > b_ask + taker_edge_ticks and planned_pos < q_star and buy_capacity > 0:
        desired_buy = int(math.floor(q_star - planned_pos))

        qty = min(
            desired_buy,
            buy_capacity,
            ask_vol,
        )

        if qty > 0:
            orders.append(Order(product, b_ask, qty))
            planned_pos += qty

    sell_capacity = pos_limit + planned_pos

    if fair < b_bid - taker_edge_ticks and planned_pos > q_star and sell_capacity > 0:
        desired_sell = int(math.floor(planned_pos - q_star))

        qty = min(
            desired_sell,
            sell_capacity,
            bid_vol,
        )

        if qty > 0:
            orders.append(Order(product, b_bid, -qty))
            planned_pos -= qty

    # =========================
    # 10. Reservation price in log-price
    # =========================
    reservation_log = fair_log - gamma * var_h * (planned_pos - q_star)

    # =========================
    # 11. A-S half-spread in log-price
    # =========================
    delta_log = as_base_delta_log + 0.5 * gamma * var_h
    delta_log *= quote_width_mult
    delta_log = max(delta_log, eps)

    raw_bid = int(math.floor(math.exp(reservation_log - delta_log)))
    raw_ask = int(math.ceil(math.exp(reservation_log + delta_log)))

    if raw_ask - raw_bid < min_tick_spread:
        center = math.exp(reservation_log)
        raw_bid = int(math.floor(center - min_tick_spread / 2.0))
        raw_ask = int(math.ceil(center + min_tick_spread / 2.0))

    # =========================
    # 12. Maker quotes
    # Maker priority rule:
    # - Buy maker only at best_bid + 1
    # - Sell maker only at best_ask - 1
    # - No maker at the existing BBO.
    # =========================
    maker_bid: int | None = None
    maker_ask: int | None = None

    if spread >= 3:
        priority_bid = b_bid + 1
        priority_ask = b_ask - 1

        if raw_bid >= priority_bid:
            maker_bid = priority_bid

        if raw_ask <= priority_ask:
            maker_ask = priority_ask

    # =========================
    # 13. Maker sizing
    # =========================
    inv_gap = q_star - planned_pos
    normalized_gap = inv_gap / pos_limit

    bid_size_float = base_size * max(
        0.0,
        1.0 + theta_size * normalized_gap,
    )

    ask_size_float = base_size * max(
        0.0,
        1.0 - theta_size * normalized_gap,
    )

    bid_size = int(round(bid_size_float))
    ask_size = int(round(ask_size_float))

    buy_capacity = pos_limit - planned_pos
    sell_capacity = pos_limit + planned_pos

    buy_qty = max(0, min(bid_size, buy_capacity))
    sell_qty = max(0, min(ask_size, sell_capacity))

    if maker_bid is not None and buy_qty > 0:
        orders.append(Order(product, maker_bid, buy_qty))

    if maker_ask is not None and sell_qty > 0:
        orders.append(Order(product, maker_ask, -sell_qty))

    # =========================
    # 14. Save product state
    # =========================
    mu_1 = mu_0 + trend_lambda * trend_beta * dt

    new_state = {
        "x_hist": x_hist,
        "eps_hist": eps_hist,

        "prev_micro": micro,
        "prev_x": x,
        "prev_mu_0": mu_0,
        "prev_mu_1": mu_1,

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

    return orders, new_state


# ============================================================
# Trader
# ============================================================

class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        all_state = load_state(state.traderData)

        result: dict[str, list[Order]] = {}
        new_all_state: dict[str, dict] = {}

        for product, cfg in PRODUCT_PARAMS.items():
            depth = state.order_depths.get(product)

            if depth is None:
                continue

            pos = state.position.get(product, 0)
            product_state = all_state.get(product, {})

            if not isinstance(product_state, dict):
                product_state = {}

            orders, new_product_state = run_one_product(
                product=product,
                depth=depth,
                pos=pos,
                st=product_state,
                cfg=cfg,
            )

            result[product] = orders
            new_all_state[product] = new_product_state

        return result, 0, json.dumps(new_all_state)