from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from prosperity4bt.core.market_trade_matching import build_market_trade_state, match_against_market_trades
from prosperity4bt.domain.datamodel import Order, Trade


class MarketTradeMatchingTests(unittest.TestCase):
    def test_no_fill_when_price_not_strictly_better(self) -> None:
        """When our bid equals the best market bid, we should NOT fill (tied with market-maker)."""
        market_state = build_market_trade_state(
            {"EMERALDS": [Trade(symbol="EMERALDS", price=10000, quantity=3, timestamp=10)]}
        )
        result = match_against_market_trades(
            order=Order("EMERALDS", 10000, 3),
            market_state=market_state["EMERALDS"],
            timestamp=10,
            best_market_bid=10000,
        )
        self.assertEqual(result.trades, [])
        self.assertEqual(result.remaining_quantity, 3)

    def test_fill_when_price_strictly_better(self) -> None:
        """When our bid is strictly better than best market bid, and trade crosses, we fill at our price."""
        market_state = build_market_trade_state(
            {"EMERALDS": [Trade(symbol="EMERALDS", price=9999, quantity=3, timestamp=10)]}
        )
        result = match_against_market_trades(
            order=Order("EMERALDS", 10001, 3),
            market_state=market_state["EMERALDS"],
            timestamp=10,
            best_market_bid=10000,
        )
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].price, 10001)  # filled at our price
        self.assertEqual(result.trades[0].quantity, 3)
        self.assertEqual(result.remaining_quantity, 0)

    def test_no_market_state_returns_empty(self) -> None:
        result = match_against_market_trades(
            order=Order("EMERALDS", 10000, 3),
            market_state=None,
            timestamp=10,
        )
        self.assertEqual(result.trades, [])
        self.assertEqual(result.remaining_quantity, 3)


if __name__ == "__main__":
    unittest.main()
