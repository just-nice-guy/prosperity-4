from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from prosperity4bt.core.limits import enforce_limits
from prosperity4bt.domain.datamodel import Order


class LimitTests(unittest.TestCase):
    def test_accepts_orders_inside_limit(self) -> None:
        result = enforce_limits(
            symbol="EMERALDS",
            current_positions={"EMERALDS": 10},
            orders=[Order("EMERALDS", 10000, 20), Order("EMERALDS", 10002, -15)],
            limits={"EMERALDS": 80},
        )
        self.assertEqual(len(result.accepted_orders), 2)
        self.assertEqual(result.rejected_orders, [])

    def test_clamps_buy_order_to_remaining_capacity(self) -> None:
        # pos=70, limit=80, capacity=10. Order qty=11 → clamped to 10.
        result = enforce_limits(
            symbol="EMERALDS",
            current_positions={"EMERALDS": 70},
            orders=[Order("EMERALDS", 10000, 11)],
            limits={"EMERALDS": 80},
        )
        self.assertEqual(len(result.accepted_orders), 1)
        self.assertEqual(result.accepted_orders[0].quantity, 10)

    def test_rejects_buy_order_when_at_limit(self) -> None:
        # pos=80, limit=80, capacity=0. Order fully rejected.
        result = enforce_limits(
            symbol="EMERALDS",
            current_positions={"EMERALDS": 80},
            orders=[Order("EMERALDS", 10000, 5)],
            limits={"EMERALDS": 80},
        )
        self.assertEqual(result.accepted_orders, [])
        self.assertEqual(len(result.rejected_orders), 1)

    def test_clamps_buys_best_price_first(self) -> None:
        # pos=70, capacity=10. Two buys at different prices: best (highest)
        # gets first dibs on capacity.
        result = enforce_limits(
            symbol="EMERALDS",
            current_positions={"EMERALDS": 70},
            orders=[Order("EMERALDS", 10000, 8), Order("EMERALDS", 10005, 8)],
            limits={"EMERALDS": 80},
        )
        # Higher-priced (10005) gets full 8, lower-priced (10000) gets 2.
        accepted_by_price = {o.price: o.quantity for o in result.accepted_orders}
        self.assertEqual(accepted_by_price[10005], 8)
        self.assertEqual(accepted_by_price[10000], 2)

    def test_clamps_sell_order_to_remaining_capacity(self) -> None:
        # pos=-70, limit=80, sell capacity=10. Order qty=-15 → clamped to -10.
        result = enforce_limits(
            symbol="EMERALDS",
            current_positions={"EMERALDS": -70},
            orders=[Order("EMERALDS", 10000, -15)],
            limits={"EMERALDS": 80},
        )
        self.assertEqual(len(result.accepted_orders), 1)
        self.assertEqual(result.accepted_orders[0].quantity, -10)


if __name__ == "__main__":
    unittest.main()
