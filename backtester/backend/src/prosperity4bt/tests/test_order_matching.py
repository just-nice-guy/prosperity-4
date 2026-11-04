from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from prosperity4bt.core.order_matching import match_order_against_book
from prosperity4bt.domain.datamodel import Order, OrderDepth


class OrderMatchingTests(unittest.TestCase):
    def test_buy_matches_best_ask_levels(self) -> None:
        depth = OrderDepth(buy_orders={}, sell_orders={10001: -5, 10002: -7})
        result = match_order_against_book(Order("EMERALDS", 10002, 8), depth, timestamp=100)
        self.assertEqual(sum(trade.quantity for trade in result.trades), 8)
        self.assertEqual(result.remaining_quantity, 0)
        self.assertEqual(result.updated_depth.sell_orders[10002], -4)

    def test_sell_matches_best_bids(self) -> None:
        depth = OrderDepth(buy_orders={9999: 4, 9998: 5}, sell_orders={})
        result = match_order_against_book(Order("EMERALDS", 9998, -6), depth, timestamp=100)
        self.assertEqual(sum(trade.quantity for trade in result.trades), 6)
        self.assertEqual(result.remaining_quantity, 0)
        self.assertEqual(result.updated_depth.buy_orders[9998], 3)


if __name__ == "__main__":
    unittest.main()
