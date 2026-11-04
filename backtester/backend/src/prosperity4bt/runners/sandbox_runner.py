from __future__ import annotations

import contextlib
import io
import time
from dataclasses import dataclass

from prosperity4bt.domain.datamodel import Order, TradingState


@dataclass(frozen=True)
class TraderInvocationResult:
    orders: dict[str, list[Order]]
    conversions: int | dict[str, int]
    trader_data: str
    stdout: str
    elapsed_ms: float
    timed_out: bool


def invoke_trader(trader, state: TradingState, time_limit_ms: int) -> TraderInvocationResult:
    stdout_buffer = io.StringIO()
    start = time.perf_counter()
    with contextlib.redirect_stdout(stdout_buffer):
        raw_result = trader.run(state)
    elapsed_ms = (time.perf_counter() - start) * 1000

    if not isinstance(raw_result, tuple):
        raise TypeError("Trader.run must return a tuple")
    if len(raw_result) == 2:
        raw_orders, conversions = raw_result
        trader_data = ""
    elif len(raw_result) == 3:
        raw_orders, conversions, trader_data = raw_result
    else:
        raise ValueError("Trader.run must return (orders, conversions) or (orders, conversions, traderData)")

    normalized_orders: dict[str, list[Order]] = {}
    for symbol, orders in (raw_orders or {}).items():
        normalized_orders[symbol] = [order for order in orders if isinstance(order, Order)]

    return TraderInvocationResult(
        orders=normalized_orders,
        conversions=conversions or 0,
        trader_data=str(trader_data or ""),
        stdout=stdout_buffer.getvalue(),
        elapsed_ms=elapsed_ms,
        timed_out=elapsed_ms > time_limit_ms,
    )
