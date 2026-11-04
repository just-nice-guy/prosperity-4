from __future__ import annotations

from dataclasses import dataclass
from math import floor, gcd
from typing import Optional, Any
import json


try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    try:
        from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
    except ImportError:
        class Order:
            def __init__(self, symbol: str, price: int, quantity: int):
                self.symbol = symbol
                self.price = price
                self.quantity = quantity

            def __repr__(self):
                return f"Order({self.symbol}, {self.price}, {self.quantity})"

        class OrderDepth:
            def __init__(self, buy_orders=None, sell_orders=None):
                self.buy_orders = buy_orders or {}
                self.sell_orders = sell_orders or {}

            def __repr__(self):
                return f"OrderDepth(buy_orders={self.buy_orders}, sell_orders={self.sell_orders})"

        class TradingState:
            def __init__(
                self,
                order_depths,
                position=None,
                own_trades=None,
                traderData="",
                timestamp=0,
            ):
                self.order_depths = order_depths
                self.position = position or {}
                self.own_trades = own_trades or {}
                self.traderData = traderData
                self.timestamp = timestamp


# =============================================================================
# Paramètres
# =============================================================================

DEBUG = False

SPOT_SYMBOL = "VELVETFRUIT_EXTRACT"
OPTION_PREFIX = "VEV_"

ENABLE_TAKER_TAKER_FALLBACK = True

# False = tous les triplets K1<K2<K3 sont testés.
# True = seulement les butterflies adjacents, plus rapide mais non exhaustif.
BUTTERFLY_ADJACENT_ONLY = False

DEFAULT_POS_LIMIT_SPOT = 200
DEFAULT_POS_LIMIT_OPTION = 300

POSITION_LIMITS: dict[str, int] = {
    "VELVETFRUIT_EXTRACT": DEFAULT_POS_LIMIT_SPOT,
    "VEV_4000": DEFAULT_POS_LIMIT_OPTION,
    "VEV_4500": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5000": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5100": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5200": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5300": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5400": DEFAULT_POS_LIMIT_OPTION,
    "VEV_5500": DEFAULT_POS_LIMIT_OPTION,
    "VEV_6000": DEFAULT_POS_LIMIT_OPTION,
    "VEV_6500": DEFAULT_POS_LIMIT_OPTION,
}

# Edge minimal pour accepter un maker-taker.
MIN_MAKER_EDGE = 3

# Edge minimal pour accepter un taker-taker immédiat.
MIN_TAKER_EDGE = 1

# Limite uniquement pour éviter que traderData devienne trop gros.
MAX_PROCESSED_TRADE_KEYS = 500


def dprint(*args) -> None:
    if DEBUG:
        print(*args)


# =============================================================================
# Structures internes
# =============================================================================

@dataclass(frozen=True)
class Quote:
    symbol: str
    product: str
    strike: Optional[int]
    bid: Optional[int]
    bid_qty: int
    ask: Optional[int]
    ask_qty: int


@dataclass(frozen=True)
class Leg:
    symbol: str
    action: str          # "BUY" ou "SELL"
    price: int           # prix taker par défaut
    unit_qty: int        # quantité entière par cycle


@dataclass(frozen=True)
class Arb:
    name: str
    legs: tuple[Leg, ...]
    cash_adj: int        # cash-flow implicite par cycle
    edge: int            # cash-flow initial par cycle


# =============================================================================
# Lecture du carnet
# =============================================================================

def best_bid(depth: OrderDepth) -> tuple[Optional[int], int]:
    if not depth.buy_orders:
        return None, 0

    px = max(depth.buy_orders)
    qty = abs(int(depth.buy_orders[px]))
    return int(px), qty


def best_ask(depth: OrderDepth) -> tuple[Optional[int], int]:
    if not depth.sell_orders:
        return None, 0

    px = min(depth.sell_orders)
    qty = abs(int(depth.sell_orders[px]))
    return int(px), qty


def parse_quotes(order_depths: dict[str, OrderDepth]) -> tuple[Optional[Quote], list[Quote]]:
    spot: Optional[Quote] = None
    options: list[Quote] = []

    for symbol, depth in order_depths.items():
        bid, bid_qty = best_bid(depth)
        ask, ask_qty = best_ask(depth)

        if symbol == SPOT_SYMBOL:
            spot = Quote(
                symbol=symbol,
                product="SPOT",
                strike=None,
                bid=bid,
                bid_qty=bid_qty,
                ask=ask,
                ask_qty=ask_qty,
            )

        elif symbol.startswith(OPTION_PREFIX):
            raw = symbol[len(OPTION_PREFIX):]

            if raw.isdigit():
                options.append(
                    Quote(
                        symbol=symbol,
                        product="OPTION",
                        strike=int(raw),
                        bid=bid,
                        bid_qty=bid_qty,
                        ask=ask,
                        ask_qty=ask_qty,
                    )
                )

    options.sort(key=lambda q: int(q.strike))
    return spot, options


def can_buy(q: Quote) -> bool:
    return q.ask is not None and q.ask_qty > 0


def can_sell(q: Quote) -> bool:
    return q.bid is not None and q.bid_qty > 0


def quotes_by_symbol(spot: Optional[Quote], options: list[Quote]) -> dict[str, Quote]:
    out: dict[str, Quote] = {}

    if spot is not None:
        out[spot.symbol] = spot

    for q in options:
        out[q.symbol] = q

    return out


# =============================================================================
# Limites de position
# =============================================================================

def get_position_limit(symbol: str) -> int:
    if symbol in POSITION_LIMITS:
        return int(POSITION_LIMITS[symbol])

    if symbol == SPOT_SYMBOL:
        return int(DEFAULT_POS_LIMIT_SPOT)

    if symbol.startswith(OPTION_PREFIX):
        return int(DEFAULT_POS_LIMIT_OPTION)

    return int(DEFAULT_POS_LIMIT_OPTION)


# =============================================================================
# Cash-flow et quantités
# =============================================================================

def signed_qty(action: str, qty_abs: int) -> int:
    if action == "BUY":
        return int(qty_abs)

    if action == "SELL":
        return -int(qty_abs)

    raise ValueError(f"Action inconnue: {action}")


def leg_cashflow(action: str, price: int, qty: int) -> int:
    if action == "BUY":
        return -price * qty

    if action == "SELL":
        return price * qty

    raise ValueError(f"Action inconnue: {action}")


def compute_edge(legs: tuple[Leg, ...], cash_adj: int = 0) -> int:
    total = int(cash_adj)

    for leg in legs:
        total += leg_cashflow(
            action=leg.action,
            price=leg.price,
            qty=leg.unit_qty,
        )

    return int(total)


def reduce_three(a: int, b: int, c: int) -> tuple[int, int, int]:
    g = gcd(gcd(abs(a), abs(b)), abs(c))

    if g == 0:
        return a, b, c

    return a // g, b // g, c // g


def make_arb(name: str, legs: tuple[Leg, ...], cash_adj: int = 0) -> Arb:
    return Arb(
        name=name,
        legs=legs,
        cash_adj=int(cash_adj),
        edge=compute_edge(legs, cash_adj),
    )


# =============================================================================
# Génération exhaustive des structures d'arbitrage
# =============================================================================

def generate_candidate_arbs(
    spot: Optional[Quote],
    options: list[Quote],
) -> list[Arb]:
    arbs: list[Arb] = []

    quotes: list[Quote] = []

    if spot is not None:
        quotes.append(spot)

    quotes.extend(options)

    # 1. Même instrument, bid > ask.
    for q in quotes:
        if can_buy(q) and can_sell(q):
            assert q.ask is not None
            assert q.bid is not None

            arbs.append(
                make_arb(
                    "crossed_same_instrument",
                    (
                        Leg(q.symbol, "BUY", q.ask, 1),
                        Leg(q.symbol, "SELL", q.bid, 1),
                    ),
                )
            )

    # 2. Prix d'achat négatif.
    for q in quotes:
        if can_buy(q):
            assert q.ask is not None

            arbs.append(
                make_arb(
                    "negative_ask",
                    (
                        Leg(q.symbol, "BUY", q.ask, 1),
                    ),
                )
            )

    # 3. Borne supérieure call <= spot.
    if spot is not None and can_buy(spot):
        assert spot.ask is not None

        for opt in options:
            if not can_sell(opt):
                continue

            assert opt.bid is not None

            arbs.append(
                make_arb(
                    "call_upper_bound_by_spot",
                    (
                        Leg(opt.symbol, "SELL", opt.bid, 1),
                        Leg(spot.symbol, "BUY", spot.ask, 1),
                    ),
                )
            )

    # 4. Borne intrinsèque C(K) >= S - K.
    if spot is not None and can_sell(spot):
        assert spot.bid is not None

        for opt in options:
            if not can_buy(opt) or opt.strike is None:
                continue

            assert opt.ask is not None

            k = int(opt.strike)

            arbs.append(
                make_arb(
                    "call_intrinsic_lower_bound",
                    (
                        Leg(opt.symbol, "BUY", opt.ask, 1),
                        Leg(spot.symbol, "SELL", spot.bid, 1),
                    ),
                    cash_adj=-k,
                )
            )

    n = len(options)

    # 5. Monotonie / vertical spread positif.
    for i in range(n):
        low = options[i]

        if not can_buy(low) or low.strike is None:
            continue

        assert low.ask is not None

        for j in range(i + 1, n):
            high = options[j]

            if not can_sell(high) or high.strike is None:
                continue

            assert high.bid is not None

            if int(low.strike) >= int(high.strike):
                continue

            arbs.append(
                make_arb(
                    "monotonicity_vertical_spread",
                    (
                        Leg(low.symbol, "BUY", low.ask, 1),
                        Leg(high.symbol, "SELL", high.bid, 1),
                    ),
                )
            )

    # 6. Vertical spread borné par K2-K1.
    for i in range(n):
        low = options[i]

        if not can_sell(low) or low.strike is None:
            continue

        assert low.bid is not None

        for j in range(i + 1, n):
            high = options[j]

            if not can_buy(high) or high.strike is None:
                continue

            assert high.ask is not None

            k1 = int(low.strike)
            k2 = int(high.strike)

            if k1 >= k2:
                continue

            width = k2 - k1

            arbs.append(
                make_arb(
                    "vertical_spread_upper_bound",
                    (
                        Leg(low.symbol, "SELL", low.bid, 1),
                        Leg(high.symbol, "BUY", high.ask, 1),
                    ),
                    cash_adj=-width,
                )
            )

    # 7. Convexité / butterfly.
    if BUTTERFLY_ADJACENT_ONLY:
        triplets = [
            (i, i + 1, i + 2)
            for i in range(max(0, n - 2))
        ]
    else:
        triplets = [
            (i, j, k)
            for i in range(n)
            for j in range(i + 1, n)
            for k in range(j + 1, n)
        ]

    for i, j, k in triplets:
        left = options[i]
        mid = options[j]
        right = options[k]

        if (
            not can_buy(left)
            or not can_sell(mid)
            or not can_buy(right)
            or left.strike is None
            or mid.strike is None
            or right.strike is None
        ):
            continue

        assert left.ask is not None
        assert mid.bid is not None
        assert right.ask is not None

        k1 = int(left.strike)
        k2 = int(mid.strike)
        k3 = int(right.strike)

        if not (k1 < k2 < k3):
            continue

        q_left = k3 - k2
        q_mid = k3 - k1
        q_right = k2 - k1

        q_left, q_mid, q_right = reduce_three(q_left, q_mid, q_right)

        arbs.append(
            make_arb(
                "convexity_butterfly",
                (
                    Leg(left.symbol, "BUY", left.ask, q_left),
                    Leg(mid.symbol, "SELL", mid.bid, q_mid),
                    Leg(right.symbol, "BUY", right.ask, q_right),
                ),
            )
        )

    arbs.sort(key=lambda a: a.edge, reverse=True)
    return arbs


# =============================================================================
# Prix maker
# =============================================================================

def maker_price_for_leg(leg: Leg, q: Quote) -> Optional[int]:
    if q.bid is None or q.ask is None:
        return None

    if leg.action == "BUY":
        px = int(q.bid) + 1

        if px >= int(q.ask):
            return None

        return px

    if leg.action == "SELL":
        px = int(q.ask) - 1

        if px <= int(q.bid):
            return None

        return px

    return None


def edge_with_maker(arb: Arb, maker_idx: int, maker_price: int) -> int:
    total = int(arb.cash_adj)

    for i, leg in enumerate(arb.legs):
        price = maker_price if i == maker_idx else leg.price

        total += leg_cashflow(
            action=leg.action,
            price=price,
            qty=leg.unit_qty,
        )

    return int(total)


def arb_key(arb: Arb, maker_idx: int) -> str:
    parts = [arb.name, f"m={maker_idx}", f"cash={arb.cash_adj}"]

    for leg in arb.legs:
        parts.append(f"{leg.action}:{leg.symbol}:{leg.unit_qty}")

    return "|".join(parts)


# =============================================================================
# Mémoire JSON
# =============================================================================

def empty_memory() -> dict[str, Any]:
    return {
        "pending_makers": [],
        "open_hedges": [],
        "processed_trade_keys": [],
        "next_id": 1,
    }


def load_memory(raw: str) -> dict[str, Any]:
    if not raw:
        return empty_memory()

    try:
        data = json.loads(raw)
    except Exception:
        return empty_memory()

    if not isinstance(data, dict):
        return empty_memory()

    data.setdefault("pending_makers", [])
    data.setdefault("open_hedges", [])
    data.setdefault("processed_trade_keys", [])
    data.setdefault("next_id", 1)

    return data


def dump_memory(mem: dict[str, Any]) -> str:
    keys = mem.get("processed_trade_keys", [])

    if len(keys) > MAX_PROCESSED_TRADE_KEYS:
        mem["processed_trade_keys"] = keys[-MAX_PROCESSED_TRADE_KEYS:]

    return json.dumps(mem, separators=(",", ":"))


def leg_to_json(leg: Leg) -> dict[str, Any]:
    return {
        "s": leg.symbol,
        "a": leg.action,
        "p": int(leg.price),
        "q": int(leg.unit_qty),
    }


def leg_from_json(x: dict[str, Any]) -> Leg:
    return Leg(
        symbol=str(x["s"]),
        action=str(x["a"]),
        price=int(x["p"]),
        unit_qty=int(x["q"]),
    )


# =============================================================================
# own_trades
# =============================================================================

def trade_key(symbol: str, trade: Any) -> str:
    return (
        f"{symbol}|"
        f"{getattr(trade, 'timestamp', None)}|"
        f"{getattr(trade, 'price', None)}|"
        f"{getattr(trade, 'quantity', None)}|"
        f"{getattr(trade, 'buyer', None)}|"
        f"{getattr(trade, 'seller', None)}"
    )


def infer_own_side_from_trade(trade: Any) -> Optional[str]:
    buyer = str(getattr(trade, "buyer", ""))
    seller = str(getattr(trade, "seller", ""))

    if buyer == "SUBMISSION" or "SUBMISSION" in buyer:
        return "BUY"

    if seller == "SUBMISSION" or "SUBMISSION" in seller:
        return "SELL"

    return None


def filled_qty_for_pending(
    pending: dict[str, Any],
    state: TradingState,
    processed: set[str],
) -> tuple[int, list[str]]:
    symbol = str(pending["ms"])
    action = str(pending["ma"])
    price = int(pending["mp"])

    own_trades = getattr(state, "own_trades", {}) or {}
    trades = own_trades.get(symbol, [])

    qty = 0
    new_keys: list[str] = []

    for trade in trades:
        key = trade_key(symbol, trade)

        if key in processed:
            continue

        side = infer_own_side_from_trade(trade)

        if side != action:
            continue

        trade_price = int(getattr(trade, "price", 0))
        trade_qty = abs(int(getattr(trade, "quantity", 0)))

        if trade_price == price and trade_qty > 0:
            qty += trade_qty
            new_keys.append(key)

    return qty, new_keys


# =============================================================================
# Position, liquidité, ordres
# =============================================================================

def add_order(
    orders: dict[str, list[Order]],
    symbol: str,
    price: int,
    qty: int,
) -> None:
    if qty == 0:
        return

    orders.setdefault(symbol, []).append(Order(symbol, int(price), int(qty)))


def position_room_cycles(
    symbol: str,
    action: str,
    unit_qty: int,
    position: dict[str, int],
    planned_delta: dict[str, int],
) -> int:
    pos = int(position.get(symbol, 0)) + int(planned_delta.get(symbol, 0))
    limit = get_position_limit(symbol)

    delta = signed_qty(action, unit_qty)

    if delta > 0:
        return max(0, floor((limit - pos) / delta))

    return max(0, floor((pos + limit) / abs(delta)))


def consume_position(
    symbol: str,
    action: str,
    qty_abs: int,
    planned_delta: dict[str, int],
) -> None:
    planned_delta[symbol] = planned_delta.get(symbol, 0) + signed_qty(action, qty_abs)


def taker_price_available(
    q: Quote,
    action: str,
    used_liq: dict[tuple[str, str], int],
) -> tuple[Optional[int], int]:
    used = used_liq.get((q.symbol, action), 0)

    if action == "BUY":
        if q.ask is None:
            return None, 0

        return int(q.ask), max(0, int(q.ask_qty) - used)

    if action == "SELL":
        if q.bid is None:
            return None, 0

        return int(q.bid), max(0, int(q.bid_qty) - used)

    return None, 0


def consume_liquidity(
    symbol: str,
    action: str,
    qty_abs: int,
    used_liq: dict[tuple[str, str], int],
) -> None:
    key = (symbol, action)
    used_liq[key] = used_liq.get(key, 0) + qty_abs


# =============================================================================
# Pending maker -> hedges
# =============================================================================

def process_pending_fills(mem: dict[str, Any], state: TradingState) -> None:
    pending = mem.get("pending_makers", [])
    processed = set(mem.get("processed_trade_keys", []))

    new_pending: list[dict[str, Any]] = []
    hedges = list(mem.get("open_hedges", []))
    new_keys: list[str] = []

    for p in pending:
        maker_unit = int(p["mu"])
        remaining_cycles = int(p["rc"])
        buffer_qty = int(p.get("buf", 0))

        fill_qty, keys = filled_qty_for_pending(
            pending=p,
            state=state,
            processed=processed,
        )

        total_fill = buffer_qty + fill_qty
        cycles_filled = min(remaining_cycles, total_fill // maker_unit)

        if cycles_filled <= 0:
            p["buf"] = total_fill
            new_pending.append(p)
            new_keys.extend(keys)
            continue

        legs = [leg_from_json(x) for x in p["legs"]]
        maker_idx = int(p["mi"])

        for i, leg in enumerate(legs):
            if i == maker_idx:
                continue

            qty_abs = int(leg.unit_qty) * cycles_filled

            if qty_abs > 0:
                hedges.append(
                    {
                        "s": leg.symbol,
                        "a": leg.action,
                        "q": qty_abs,
                        "src": int(p["id"]),
                    }
                )

        remaining_cycles -= cycles_filled
        leftover = total_fill - cycles_filled * maker_unit

        new_keys.extend(keys)

        dprint("MAKER FILL:", p["id"], p["name"], "cycles", cycles_filled)

        if remaining_cycles > 0:
            p["rc"] = remaining_cycles
            p["buf"] = leftover
            new_pending.append(p)

    mem["pending_makers"] = new_pending
    mem["open_hedges"] = hedges

    old_keys = list(mem.get("processed_trade_keys", []))
    old_keys.extend(new_keys)
    mem["processed_trade_keys"] = old_keys[-MAX_PROCESSED_TRADE_KEYS:]


# =============================================================================
# Exécution des hedges taker
# =============================================================================

def execute_hedges(
    mem: dict[str, Any],
    qmap: dict[str, Quote],
    position: dict[str, int],
    orders: dict[str, list[Order]],
    planned_delta: dict[str, int],
    used_liq: dict[tuple[str, str], int],
) -> None:
    remaining_hedges: list[dict[str, Any]] = []

    for hedge in mem.get("open_hedges", []):
        symbol = str(hedge["s"])
        action = str(hedge["a"])
        qty_left = int(hedge["q"])

        if qty_left <= 0:
            continue

        quote = qmap.get(symbol)

        if quote is None:
            remaining_hedges.append(hedge)
            continue

        price, available = taker_price_available(
            q=quote,
            action=action,
            used_liq=used_liq,
        )

        if price is None or available <= 0:
            remaining_hedges.append(hedge)
            continue

        max_by_position = position_room_cycles(
            symbol=symbol,
            action=action,
            unit_qty=1,
            position=position,
            planned_delta=planned_delta,
        )

        executable = min(qty_left, available, max_by_position)

        if executable <= 0:
            remaining_hedges.append(hedge)
            continue

        add_order(
            orders=orders,
            symbol=symbol,
            price=price,
            qty=signed_qty(action, executable),
        )

        consume_position(
            symbol=symbol,
            action=action,
            qty_abs=executable,
            planned_delta=planned_delta,
        )

        consume_liquidity(
            symbol=symbol,
            action=action,
            qty_abs=executable,
            used_liq=used_liq,
        )

        qty_left -= executable

        dprint("HEDGE:", symbol, action, executable, "@", price)

        if qty_left > 0:
            hedge["q"] = qty_left
            remaining_hedges.append(hedge)

    mem["open_hedges"] = remaining_hedges


# =============================================================================
# Repost makers existants
# =============================================================================

def repost_pending_makers(
    mem: dict[str, Any],
    qmap: dict[str, Quote],
    position: dict[str, int],
    orders: dict[str, list[Order]],
    planned_delta: dict[str, int],
) -> None:
    new_pending: list[dict[str, Any]] = []

    for p in mem.get("pending_makers", []):
        symbol = str(p["ms"])
        action = str(p["ma"])
        maker_idx = int(p["mi"])
        remaining_cycles = int(p["rc"])
        maker_unit = int(p["mu"])

        if remaining_cycles <= 0:
            continue

        quote = qmap.get(symbol)

        if quote is None:
            continue

        legs = tuple(leg_from_json(x) for x in p["legs"])

        arb = Arb(
            name=str(p["name"]),
            legs=legs,
            cash_adj=int(p["cash"]),
            edge=compute_edge(legs, int(p["cash"])),
        )

        maker_leg = legs[maker_idx]
        maker_px = maker_price_for_leg(maker_leg, quote)

        if maker_px is None:
            continue

        edge = edge_with_maker(
            arb=arb,
            maker_idx=maker_idx,
            maker_price=maker_px,
        )

        if edge < MIN_MAKER_EDGE:
            continue

        max_pos_cycles = position_room_cycles(
            symbol=symbol,
            action=action,
            unit_qty=maker_unit,
            position=position,
            planned_delta=planned_delta,
        )

        cycles = min(remaining_cycles, max_pos_cycles)

        if cycles <= 0:
            continue

        qty_abs = maker_unit * cycles

        add_order(
            orders=orders,
            symbol=symbol,
            price=maker_px,
            qty=signed_qty(action, qty_abs),
        )

        consume_position(
            symbol=symbol,
            action=action,
            qty_abs=qty_abs,
            planned_delta=planned_delta,
        )

        p["mp"] = maker_px
        p["rc"] = cycles

        new_pending.append(p)

    mem["pending_makers"] = new_pending


# =============================================================================
# Création des nouveaux makers
# =============================================================================

def existing_keys(mem: dict[str, Any]) -> set[str]:
    return {str(x.get("key", "")) for x in mem.get("pending_makers", [])}


def create_maker_intents(
    mem: dict[str, Any],
    candidates: list[Arb],
    qmap: dict[str, Quote],
    position: dict[str, int],
    orders: dict[str, list[Order]],
    planned_delta: dict[str, int],
) -> None:
    pending = list(mem.get("pending_makers", []))
    keys = existing_keys(mem)

    opportunities: list[tuple[int, Arb, int, int]] = []

    for arb in candidates:
        for maker_idx, leg in enumerate(arb.legs):
            quote = qmap.get(leg.symbol)

            if quote is None:
                continue

            maker_px = maker_price_for_leg(leg, quote)

            if maker_px is None:
                continue

            edge = edge_with_maker(
                arb=arb,
                maker_idx=maker_idx,
                maker_price=maker_px,
            )

            if edge >= MIN_MAKER_EDGE:
                opportunities.append((edge, arb, maker_idx, maker_px))

    opportunities.sort(key=lambda x: x[0], reverse=True)

    for edge, arb, maker_idx, maker_px in opportunities:
        key = arb_key(arb, maker_idx)

        if key in keys:
            continue

        maker_leg = arb.legs[maker_idx]

        max_pos_cycles = position_room_cycles(
            symbol=maker_leg.symbol,
            action=maker_leg.action,
            unit_qty=maker_leg.unit_qty,
            position=position,
            planned_delta=planned_delta,
        )

        if max_pos_cycles <= 0:
            continue

        cycles = max_pos_cycles
        qty_abs = maker_leg.unit_qty * cycles

        if qty_abs <= 0:
            continue

        add_order(
            orders=orders,
            symbol=maker_leg.symbol,
            price=maker_px,
            qty=signed_qty(maker_leg.action, qty_abs),
        )

        consume_position(
            symbol=maker_leg.symbol,
            action=maker_leg.action,
            qty_abs=qty_abs,
            planned_delta=planned_delta,
        )

        new_id = int(mem.get("next_id", 1))
        mem["next_id"] = new_id + 1

        pending_obj = {
            "id": new_id,
            "key": key,
            "name": arb.name,
            "mi": maker_idx,
            "ms": maker_leg.symbol,
            "ma": maker_leg.action,
            "mp": maker_px,
            "mu": maker_leg.unit_qty,
            "rc": cycles,
            "buf": 0,
            "cash": arb.cash_adj,
            "legs": [leg_to_json(x) for x in arb.legs],
        }

        pending.append(pending_obj)
        keys.add(key)

        dprint(
            "NEW MAKER:",
            arb.name,
            "edge",
            edge,
            "order",
            maker_leg.symbol,
            maker_px,
            signed_qty(maker_leg.action, qty_abs),
        )

    mem["pending_makers"] = pending


# =============================================================================
# Taker-taker immédiat
# =============================================================================

def execute_taker_taker(
    arbs: list[Arb],
    qmap: dict[str, Quote],
    position: dict[str, int],
    orders: dict[str, list[Order]],
    planned_delta: dict[str, int],
    used_liq: dict[tuple[str, str], int],
) -> None:
    if not ENABLE_TAKER_TAKER_FALLBACK:
        return

    for arb in arbs:
        if arb.edge < MIN_TAKER_EDGE:
            continue

        limits: list[int] = []
        ok = True

        for leg in arb.legs:
            quote = qmap.get(leg.symbol)

            if quote is None:
                ok = False
                break

            _, available = taker_price_available(
                q=quote,
                action=leg.action,
                used_liq=used_liq,
            )

            if available <= 0:
                ok = False
                break

            limits.append(available // leg.unit_qty)

            limits.append(
                position_room_cycles(
                    symbol=leg.symbol,
                    action=leg.action,
                    unit_qty=leg.unit_qty,
                    position=position,
                    planned_delta=planned_delta,
                )
            )

        if not ok or not limits:
            continue

        cycles = min(limits)

        if cycles <= 0:
            continue

        for leg in arb.legs:
            quote = qmap[leg.symbol]

            price, available = taker_price_available(
                q=quote,
                action=leg.action,
                used_liq=used_liq,
            )

            if price is None or available <= 0:
                continue

            qty_abs = min(leg.unit_qty * cycles, available)

            if qty_abs <= 0:
                continue

            add_order(
                orders=orders,
                symbol=leg.symbol,
                price=price,
                qty=signed_qty(leg.action, qty_abs),
            )

            consume_position(
                symbol=leg.symbol,
                action=leg.action,
                qty_abs=qty_abs,
                planned_delta=planned_delta,
            )

            consume_liquidity(
                symbol=leg.symbol,
                action=leg.action,
                qty_abs=qty_abs,
                used_liq=used_liq,
            )

        dprint("TAKER ARB:", arb.name, "edge", arb.edge, "cycles", cycles)


# =============================================================================
# Strategy
# =============================================================================

class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders: dict[str, list[Order]] = {}

        mem = load_memory(getattr(state, "traderData", ""))

        spot, options = parse_quotes(state.order_depths)

        if spot is None or not options:
            return {}, 0, dump_memory(mem)

        qmap = quotes_by_symbol(spot, options)

        planned_delta: dict[str, int] = {}
        used_liq: dict[tuple[str, str], int] = {}

        # 1. Vérifier les fills maker précédents.
        process_pending_fills(mem, state)

        # 2. Hedger immédiatement les makers remplis.
        execute_hedges(
            mem=mem,
            qmap=qmap,
            position=state.position,
            orders=orders,
            planned_delta=planned_delta,
            used_liq=used_liq,
        )

        # 3. Générer toutes les structures d'arbitrage.
        candidates = generate_candidate_arbs(spot, options)

        # 4. Exécuter d'abord les arbitrages taker-taker certains.
        execute_taker_taker(
            arbs=candidates,
            qmap=qmap,
            position=state.position,
            orders=orders,
            planned_delta=planned_delta,
            used_liq=used_liq,
        )

        # 5. Reposter les makers existants encore valides.
        repost_pending_makers(
            mem=mem,
            qmap=qmap,
            position=state.position,
            orders=orders,
            planned_delta=planned_delta,
        )

        # 6. Poster les nouveaux makers possibles avec edge >= MIN_MAKER_EDGE.
        create_maker_intents(
            mem=mem,
            candidates=candidates,
            qmap=qmap,
            position=state.position,
            orders=orders,
            planned_delta=planned_delta,
        )

        return orders, 0, dump_memory(mem)
