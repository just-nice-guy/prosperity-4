from __future__ import annotations

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

PRODUCT   = "ASH_COATED_OSMIUM"

class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        return {PRODUCT: []}, 0, ""