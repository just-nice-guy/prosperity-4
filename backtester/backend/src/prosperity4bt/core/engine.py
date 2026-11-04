from __future__ import annotations

import datetime as dt
import random
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from prosperity4bt.core.clocks import group_by_timestamp, sorted_timestamps
from prosperity4bt.core.conversions import apply_conversions
from prosperity4bt.core.limits import effective_limits, enforce_limits
from prosperity4bt.core.market_trade_matching import (
    build_market_trade_state,
    match_against_market_trades,
    match_invisible_taker,
    remaining_trades,
)
from prosperity4bt.core.order_matching import match_order_against_book
from prosperity4bt.core.pnl import apply_fill, mark_to_market
from prosperity4bt.core.state_builder import build_state
from prosperity4bt.data.catalog import DatasetCatalog
from prosperity4bt.data.loaders_observations import ObservationSnapshot, load_observations
from prosperity4bt.data.loaders_prices import PriceSnapshot, load_prices
from prosperity4bt.data.loaders_trades import load_trades
from prosperity4bt.domain.datamodel import Order, Trade
from prosperity4bt.logging.event_logger import EventLogger
from prosperity4bt.runners.sandbox_runner import invoke_trader


@dataclass(frozen=True)
class DayRequest:
    round_num: int
    day_num: int


@dataclass(frozen=True)
class EngineConfig:
    trader_path: str
    round_days: list[DayRequest]
    data_roots: list[str] = field(default_factory=list)
    limit_overrides: dict[str, int] = field(default_factory=dict)
    time_limit_ms: int = 900
    matching_mode: str = "prosperity"
    fill_probability: float = 0.005
    activity_boost: float = 0.003
    sigma: float = 0.0
    random_seed: int | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    fill_skip_prob: float = 0.0
    adverse_selection: float = 0.0
    min_fill_fraction: float = 0.5
    max_fill_fraction: float = 1.0
    edge_fill_boost: float = 0.0
    # Per-day tick ranges for CPCV fold filtering.
    # Key: "round_num:day_num", Value: list of (start_idx, end_idx) index
    # ranges into the day's sorted timestamps.  None = process all ticks.
    day_tick_ranges: dict[str, list[tuple[int, int]]] | None = None


@dataclass(frozen=True)
class EngineResult:
    run_id: str
    status: str
    started_at: str
    finished_at: str
    total_ticks: int
    total_orders: int
    total_fills: int
    final_pnl: float
    cash_by_product: dict[str, float]
    mark_to_market_by_product: dict[str, float]
    final_positions: dict[str, int]
    dataset_summaries: list[dict[str, object]]
    activity_rows: list[dict[str, object]]
    own_trade_rows: list[dict[str, object]]
    market_trade_rows: list[dict[str, object]]
    events: list[dict[str, object]]
    decision_trace: list[dict[str, object]]
    sandbox_log: str
    config_snapshot: dict[str, object]


def engine_config_from_dict(payload: dict[str, object]) -> EngineConfig:
    round_days = [
        DayRequest(round_num=int(item["round_num"]), day_num=int(item["day_num"]))
        for item in payload.get("round_days", [])
    ]
    raw_seed = payload.get("random_seed")
    raw_tick_ranges = payload.get("day_tick_ranges")
    day_tick_ranges: dict[str, list[tuple[int, int]]] | None = None
    if raw_tick_ranges is not None:
        day_tick_ranges = {
            str(k): [(int(pair[0]), int(pair[1])) for pair in v]
            for k, v in raw_tick_ranges.items()
        }
    return EngineConfig(
        trader_path=str(payload["trader_path"]),
        round_days=round_days,
        data_roots=[str(item) for item in payload.get("data_roots", [])],
        limit_overrides={str(key): int(value) for key, value in payload.get("limit_overrides", {}).items()},
        time_limit_ms=int(payload.get("time_limit_ms", 900)),
        matching_mode=str(payload.get("matching_mode", "prosperity")),
        fill_probability=float(payload.get("fill_probability", 0.005)),
        activity_boost=float(payload.get("activity_boost", 0.003)),
        sigma=float(payload.get("sigma", 0.0)),
        random_seed=int(raw_seed) if raw_seed is not None else None,
        run_id=str(payload.get("run_id") or uuid.uuid4().hex[:12]),
        fill_skip_prob=float(payload.get("fill_skip_prob", 0.0)),
        adverse_selection=float(payload.get("adverse_selection", 0.0)),
        min_fill_fraction=float(payload.get("min_fill_fraction", 0.5)),
        max_fill_fraction=float(payload.get("max_fill_fraction", 1.0)),
        edge_fill_boost=float(payload.get("edge_fill_boost", 0.0)),
        day_tick_ranges=day_tick_ranges,
    )


def run_engine(config: EngineConfig, trader) -> EngineResult:
    started_at = dt.datetime.now(dt.UTC).isoformat()
    catalog = DatasetCatalog([Path(item) for item in config.data_roots] if config.data_roots else None)
    limits = effective_limits(config.limit_overrides)
    logger = EventLogger()

    total_ticks = 0
    total_orders = 0
    total_fills = 0
    activity_rows: list[dict[str, object]] = []
    own_trade_rows: list[dict[str, object]] = []
    market_trade_rows: list[dict[str, object]] = []
    dataset_summaries: list[dict[str, object]] = []

    running_cash: dict[str, float] = {}
    running_positions: dict[str, int] = {}
    running_trader_data = ""
    last_mark_to_market: dict[str, float] = {}
    last_total_pnl = 0.0
    trader_instance = trader.__class__()

    for day_request in config.round_days:
        day_key = f"{day_request.round_num}:{day_request.day_num}"
        tick_ranges_for_day = (
            config.day_tick_ranges.get(day_key) if config.day_tick_ranges else None
        )
        day_result = _run_single_day(
            trader=trader_instance,
            catalog=catalog,
            day_request=day_request,
            time_limit_ms=config.time_limit_ms,
            limits=limits,
            logger=logger,
            matching_mode=config.matching_mode,
            fill_probability=config.fill_probability,
            activity_boost=config.activity_boost,
            sigma=config.sigma,
            random_seed=config.random_seed,
            run_id=config.run_id,
            fill_skip_prob=config.fill_skip_prob,
            adverse_selection=config.adverse_selection,
            min_fill_fraction=config.min_fill_fraction,
            max_fill_fraction=config.max_fill_fraction,
            edge_fill_boost=config.edge_fill_boost,
            tick_ranges=tick_ranges_for_day,
            initial_positions=running_positions,
            initial_cash_by_product=running_cash,
            initial_trader_data=running_trader_data,
        )
        total_ticks += day_result["tick_count"]
        total_orders += day_result["order_count"]
        total_fills += day_result["fill_count"]
        activity_rows.extend(day_result["activity_rows"])
        own_trade_rows.extend(day_result["own_trade_rows"])
        market_trade_rows.extend(day_result["market_trade_rows"])
        dataset_summaries.append(day_result["summary"])

        running_cash = dict(day_result["cash_by_product"])
        running_positions = dict(day_result["positions"])
        running_trader_data = str(day_result["trader_data"])
        last_mark_to_market = dict(day_result["mark_to_market_by_product"])
        last_total_pnl = float(day_result["final_pnl"])

    finished_at = dt.datetime.now(dt.UTC).isoformat()
    return EngineResult(
        run_id=config.run_id,
        status="completed",
        started_at=started_at,
        finished_at=finished_at,
        total_ticks=total_ticks,
        total_orders=total_orders,
        total_fills=total_fills,
        final_pnl=last_total_pnl,
        cash_by_product=dict(running_cash),
        mark_to_market_by_product=last_mark_to_market,
        final_positions=dict(running_positions),
        dataset_summaries=dataset_summaries,
        activity_rows=activity_rows,
        own_trade_rows=own_trade_rows,
        market_trade_rows=market_trade_rows,
        events=logger.event_dicts(),
        decision_trace=logger.decision_dicts(),
        sandbox_log="\n".join(logger.sandbox_lines),
        config_snapshot=asdict(config),
    )


def _run_single_day(
    trader,
    catalog: DatasetCatalog,
    day_request: DayRequest,
    time_limit_ms: int,
    limits: dict[str, int],
    logger: EventLogger,
    matching_mode: str = "prosperity",
    fill_probability: float = 0.005,
    activity_boost: float = 0.003,
    sigma: float = 0.0,
    random_seed: int | None = None,
    run_id: str = "",
    fill_skip_prob: float = 0.0,
    adverse_selection: float = 0.0,
    min_fill_fraction: float = 0.5,
    max_fill_fraction: float = 1.0,
    edge_fill_boost: float = 0.0,
    tick_ranges: list[tuple[int, int]] | None = None,
    initial_positions: dict[str, int] | None = None,
    initial_cash_by_product: dict[str, float] | None = None,
    initial_trader_data: str = "",
) -> dict[str, object]:
    files = catalog.resolve(day_request.round_num, day_request.day_num)
    prices = load_prices(files.prices_file)
    market_trades = load_trades(files.trades_file)
    observations = load_observations(files.observations_file)

    price_groups: dict[int, dict[str, PriceSnapshot]] = defaultdict(dict)
    for snapshot in prices:
        price_groups[snapshot.timestamp][snapshot.product] = snapshot

    market_trades_by_timestamp: dict[int, dict[str, list[Trade]]] = defaultdict(lambda: defaultdict(list))
    for trade in market_trades:
        market_trades_by_timestamp[trade.timestamp][trade.symbol].append(trade)

    observation_groups: dict[int, dict[str, ObservationSnapshot]] = defaultdict(dict)
    for observation in observations:
        observation_groups[observation.timestamp][observation.product] = observation

    # ── Apply tick-range filter (CPCV fold slicing) ──────────────────
    if tick_ranges is not None:
        all_ts = sorted_timestamps(price_groups)
        allowed_indices: set[int] = set()
        for start, end in tick_ranges:
            for i in range(start, min(end, len(all_ts))):
                allowed_indices.add(i)
        allowed_ts = {all_ts[i] for i in allowed_indices}
        price_groups = {ts: prods for ts, prods in price_groups.items() if ts in allowed_ts}

    # Deterministic RNG (seeded from explicit seed or run_id + day for reproducibility)
    seed_base = random_seed if random_seed is not None else f"{run_id}:{day_request.round_num}:{day_request.day_num}"
    rng = random.Random(seed_base)

    previous_own_trades: dict[str, list[Trade]] = {}
    previous_market_trades: dict[str, list[Trade]] = {}
    positions: dict[str, int] = dict(initial_positions or {})
    cash_by_product: dict[str, float] = dict(initial_cash_by_product or {})
    trader_data = initial_trader_data
    order_count = 0
    fill_count = 0
    activity_rows: list[dict[str, object]] = []
    own_trade_rows: list[dict[str, object]] = []
    market_trade_rows: list[dict[str, object]] = []
    last_mid_prices: dict[str, float] = {}
    prev_mid_prices: dict[str, float] = {}  # for adverse selection delta

    # Products with limit == 0 are excluded from the simulation entirely
    excluded_products = {p for p, lim in limits.items() if lim == 0}

    for timestamp in sorted_timestamps(price_groups):
        snapshots_by_product = {
            p: s for p, s in price_groups[timestamp].items() if p not in excluded_products
        }
        current_market_trades = {
            symbol: list(trades)
            for symbol, trades in market_trades_by_timestamp.get(timestamp, {}).items()
        }
        current_observations = observation_groups.get(timestamp, {})
        market_trade_state = build_market_trade_state(current_market_trades)

        state = build_state(
            timestamp=timestamp,
            snapshots_by_product=snapshots_by_product,
            observations_by_product=current_observations,
            previous_own_trades=previous_own_trades,
            previous_market_trades=previous_market_trades,
            positions=positions,
            trader_data=trader_data,
        )

        invocation = invoke_trader(trader=trader, state=state, time_limit_ms=time_limit_ms)
        logger.capture_stdout(invocation.stdout)
        trader_data = invocation.trader_data
        if invocation.timed_out:
            logger.emit(
                kind="timeout_warning",
                timestamp=timestamp,
                round_num=day_request.round_num,
                day_num=day_request.day_num,
                payload={"elapsed_ms": round(invocation.elapsed_ms, 3), "time_limit_ms": time_limit_ms},
            )

        logger.decision(
            timestamp=timestamp,
            round_num=day_request.round_num,
            day_num=day_request.day_num,
            payload={
                "elapsed_ms": round(invocation.elapsed_ms, 3),
                "trader_data_size": len(trader_data),
                "positions": dict(positions),
                "orders": {symbol: [order.__dict__ for order in orders] for symbol, orders in invocation.orders.items()},
                "conversions": invocation.conversions,
            },
        )

        own_fills_this_tick: dict[str, list[Trade]] = defaultdict(list)

        for symbol, orders in invocation.orders.items():
            if symbol not in snapshots_by_product:
                logger.emit(
                    kind="unknown_symbol_order",
                    timestamp=timestamp,
                    round_num=day_request.round_num,
                    day_num=day_request.day_num,
                    symbol=symbol,
                    payload={"count": len(orders)},
                )
                continue

            order_count += len(orders)
            limit_check = enforce_limits(
                symbol=symbol,
                current_positions=positions,
                orders=orders,
                limits=limits,
            )
            if limit_check.rejected_orders:
                # Log clamped/rejected orders but still process accepted_orders
                # (enforce_limits now clamps individual orders rather than
                # rejecting the whole batch).
                logger.emit(
                    kind="limit_rejection",
                    timestamp=timestamp,
                    round_num=day_request.round_num,
                    day_num=day_request.day_num,
                    symbol=symbol,
                    payload={
                        "reason": limit_check.reason,
                        "orders": [order.__dict__ for order in limit_check.rejected_orders],
                    },
                )
            if not limit_check.accepted_orders:
                continue

            # Extract the best market-maker prices from the original snapshot
            # (before any book consumption) for the PROSPERITY matching mode.
            _snap = snapshots_by_product.get(symbol)
            _best_market_bid = _snap.bid_prices[0] if _snap and _snap.bid_prices else None
            _best_market_ask = _snap.ask_prices[0] if _snap and _snap.ask_prices else None

            working_depth = state.order_depths[symbol]
            for order in limit_check.accepted_orders:
                book_result = match_order_against_book(
                    order=order,
                    depth=working_depth,
                    timestamp=timestamp,
                )
                working_depth = book_result.updated_depth
                for fill in book_result.trades:
                    apply_fill(fill, positions, cash_by_product)
                    own_fills_this_tick[symbol].append(fill)
                    own_trade_rows.append(_trade_row(fill, day_request.round_num, day_request.day_num, "book"))
                    fill_count += 1
                    logger.emit(
                        kind="fill_book",
                        timestamp=timestamp,
                        round_num=day_request.round_num,
                        day_num=day_request.day_num,
                        symbol=symbol,
                        payload=fill.__dict__,
                    )

                if book_result.remaining_quantity != 0:
                    residual_order = Order(
                        symbol=order.symbol,
                        price=order.price,
                        quantity=book_result.remaining_quantity,
                    )

                    if matching_mode == "invisible":
                        has_activity = bool(current_market_trades.get(symbol))
                        _snap_mid = snapshots_by_product[symbol].mid_price if symbol in snapshots_by_product else 0.0
                        _prev_mid = prev_mid_prices.get(symbol, _snap_mid)
                        market_result = match_invisible_taker(
                            order=residual_order,
                            timestamp=timestamp,
                            best_market_bid=_best_market_bid,
                            best_market_ask=_best_market_ask,
                            has_market_activity=has_activity,
                            rng=rng,
                            base_fill_prob=fill_probability,
                            activity_boost=activity_boost,
                            sigma=sigma,
                            fill_skip_prob=fill_skip_prob,
                            adverse_selection=adverse_selection,
                            mid_price_delta=_snap_mid - _prev_mid,
                            min_fill_fraction=min_fill_fraction,
                            max_fill_fraction=max_fill_fraction,
                            edge_fill_boost=edge_fill_boost,
                        )
                    else:
                        market_result = match_against_market_trades(
                            order=residual_order,
                            market_state=market_trade_state.get(symbol),
                            timestamp=timestamp,
                            best_market_bid=_best_market_bid,
                            best_market_ask=_best_market_ask,
                        )

                    fill_source = "invisible_taker" if matching_mode == "invisible" else "market"
                    for fill in market_result.trades:
                        apply_fill(fill, positions, cash_by_product)
                        own_fills_this_tick[symbol].append(fill)
                        own_trade_rows.append(_trade_row(fill, day_request.round_num, day_request.day_num, fill_source))
                        fill_count += 1
                        logger.emit(
                            kind="fill_invisible_taker" if matching_mode == "invisible" else "fill_market_trade",
                            timestamp=timestamp,
                            round_num=day_request.round_num,
                            day_num=day_request.day_num,
                            symbol=symbol,
                            payload=fill.__dict__,
                        )

                    if market_result.remaining_quantity != 0:
                        logger.emit(
                            kind="resting_order_expired",
                            timestamp=timestamp,
                            round_num=day_request.round_num,
                            day_num=day_request.day_num,
                            symbol=symbol,
                            payload={
                                "order": order.__dict__,
                                "remaining_quantity": market_result.remaining_quantity,
                            },
                        )

        _apply_requested_conversions(
            conversions=invocation.conversions,
            state=state,
            positions=positions,
            cash_by_product=cash_by_product,
            timestamp=timestamp,
            round_num=day_request.round_num,
            day_num=day_request.day_num,
            logger=logger,
        )

        for symbol, trades in current_market_trades.items():
            if symbol in excluded_products:
                continue
            for trade in trades:
                market_trade_rows.append(_trade_row(trade, day_request.round_num, day_request.day_num, "historical"))

        current_mid_prices = {product: snapshot.mid_price for product, snapshot in snapshots_by_product.items()}
        prev_mid_prices.update(last_mid_prices)
        last_mid_prices.update(current_mid_prices)
        pnl_snapshot = mark_to_market(positions=positions, cash_by_product=cash_by_product, mid_prices=current_mid_prices)
        for product, snapshot in snapshots_by_product.items():
            _bp = snapshot.bid_prices
            _bv = snapshot.bid_volumes
            _ap = snapshot.ask_prices
            _av = snapshot.ask_volumes
            activity_rows.append(
                {
                    "round_num": day_request.round_num,
                    "day_num": day_request.day_num,
                    "timestamp": timestamp,
                    "product": product,
                    "bid_price_1": _bp[0] if len(_bp) > 0 else None,
                    "bid_price_2": _bp[1] if len(_bp) > 1 else None,
                    "bid_price_3": _bp[2] if len(_bp) > 2 else None,
                    "bid_volume_1": _bv[0] if len(_bv) > 0 else None,
                    "bid_volume_2": _bv[1] if len(_bv) > 1 else None,
                    "bid_volume_3": _bv[2] if len(_bv) > 2 else None,
                    "ask_price_1": _ap[0] if len(_ap) > 0 else None,
                    "ask_price_2": _ap[1] if len(_ap) > 1 else None,
                    "ask_price_3": _ap[2] if len(_ap) > 2 else None,
                    "ask_volume_1": _av[0] if len(_av) > 0 else None,
                    "ask_volume_2": _av[1] if len(_av) > 1 else None,
                    "ask_volume_3": _av[2] if len(_av) > 2 else None,
                    "mid_price": snapshot.mid_price,
                    "position": positions.get(product, 0),
                    "cash": round(cash_by_product.get(product, 0.0), 4),
                    "pnl": round(pnl_snapshot.mark_to_market_by_product.get(product, 0.0), 4),
                }
            )

        previous_own_trades = {symbol: list(trades) for symbol, trades in own_fills_this_tick.items()}
        # Pass consumed market trades to next tick (kevin-fu1 model):
        # trade.quantity = min(buy_quantity, sell_quantity) after our fills.
        previous_market_trades = remaining_trades(market_trade_state)

    day_pnl = mark_to_market(positions=positions, cash_by_product=cash_by_product, mid_prices=last_mid_prices)
    return {
        "tick_count": len(price_groups),
        "order_count": order_count,
        "fill_count": fill_count,
        "positions": dict(positions),
        "cash_by_product": dict(cash_by_product),
        "mark_to_market_by_product": dict(day_pnl.mark_to_market_by_product),
        "final_pnl": day_pnl.total,
        "trader_data": trader_data,
        "last_mid_prices": last_mid_prices,
        "activity_rows": activity_rows,
        "own_trade_rows": own_trade_rows,
        "market_trade_rows": market_trade_rows,
        "summary": {
            "round_num": day_request.round_num,
            "day_num": day_request.day_num,
            "tick_count": len(price_groups),
            "order_count": order_count,
            "fill_count": fill_count,
            "final_positions": dict(positions),
            "final_pnl": round(day_pnl.total, 4),
        },
    }


def _trade_row(trade: Trade, round_num: int, day_num: int, source: str) -> dict[str, object]:
    return {
        "round_num": round_num,
        "day_num": day_num,
        "timestamp": trade.timestamp,
        "symbol": trade.symbol,
        "currency": "XIRECS",
        "price": trade.price,
        "quantity": trade.quantity,
        "buyer": trade.buyer or "",
        "seller": trade.seller or "",
        "source": source,
    }


def _apply_requested_conversions(
    conversions: int | dict[str, int],
    state,
    positions: dict[str, int],
    cash_by_product: dict[str, float],
    timestamp: int,
    round_num: int,
    day_num: int,
    logger: EventLogger,
) -> None:
    if isinstance(conversions, int):
        if conversions == 0 or not state.observations.conversionObservations:
            return
        product = next(iter(state.observations.conversionObservations))
        result = apply_conversions(
            product=product,
            requested=conversions,
            positions=positions,
            cash_by_product=cash_by_product,
            observations=state.observations,
        )
        logger.emit(
            kind="conversion",
            timestamp=timestamp,
            round_num=round_num,
            day_num=day_num,
            symbol=product,
            payload=result.__dict__,
        )
        return

    for product, requested in conversions.items():
        result = apply_conversions(
            product=product,
            requested=int(requested),
            positions=positions,
            cash_by_product=cash_by_product,
            observations=state.observations,
        )
        if result.applied == 0 and requested == 0:
            continue
        logger.emit(
            kind="conversion",
            timestamp=timestamp,
            round_num=round_num,
            day_num=day_num,
            symbol=product,
            payload=result.__dict__,
        )
